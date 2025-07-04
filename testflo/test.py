from __future__ import print_function

import os
import sys
import shutil
import time
import warnings
import traceback
from inspect import isclass
import subprocess
from contextlib import contextmanager, nullcontext

from types import FunctionType
from io import StringIO

from unittest import TestCase, SkipTest
from unittest.case import _UnexpectedSuccess

from testflo.cover import start_coverage, stop_coverage

from testflo.util import get_module, ismethod, get_memory_usage, \
                         get_testpath, _options2args, _testing_path
from testflo.utresult import UnitTestResult
from testflo.devnull import DevNull


mpirun_exe = None
if shutil.which("mpirun") is not None:
    mpirun_exe = "mpirun"
elif shutil.which("mpiexec") is not None:
    mpirun_exe = "mpiexec"


def add_queue_to_env(queue):
    """Store enough info in the env to be able to create a proxy to
    the queue in a subprocess.
    """
    addr = queue._token.address
    os.environ['TESTFLO_QUEUE'] = "%s:%s:%s" % (addr[0], addr[1],
                                                queue._token.id)


class FakeComm(object):
    def __init__(self):
        self.rank = 0
        self.size = 1


@contextmanager
def testcontext(test):
    global _testing_path
    old_sys_path = sys.path

    os.environ['TESTFLO_SPEC'] = test.spec

    _testing_path[0] = test.test_dir
    sys.path = _testing_path

    try:
        yield
    except Exception:
        test.status = 'FAIL'
        test.err_msg = traceback.format_exc()
    finally:
        sys.path = old_sys_path
        if 'TESTFLO_SPEC' in os.environ:
            del os.environ['TESTFLO_SPEC']


class Test(object):
    """Contains the path to the test function/method, status
    of the test (if finished), error and stdout messages (if any),
    start/end times and resource usage data.
    """

    def __init__(self, testspec, options):
        self.spec = testspec
        self.options = options

        testpath, rest = get_testpath(testspec)
        self.test_dir = os.path.dirname(testpath)

        self.status = None
        self.err_msg = ''
        self.mpi = False

        self.memory_usage = 0
        self.nprocs = 0
        self.isolated = False
        self.start_time = 0
        self.end_time = 0
        self.modpath = None
        self.tcasename = None
        self.funcname = None
        self.load = (0.0, 0.0, 0.0)
        self.expected_fail = False
        self._mod_fixture_first = False
        self._mod_fixture_last = False
        self._tcase_fixture_first = False
        self._tcase_fixture_last = False

        self.deprecations = {}

        self._get_test_info()

    def __iter__(self):
        """Allows Test to be iterated over so we don't have to check later
        for Test vs. iter of Tests.
        """
        return iter((self,))

    def _get_test_info(self):
        """Get the test's module, testcase (if any), function name,
        N_PROCS (for mpi tests) and ISOLATED and set our attributes.
        """
        with testcontext(self):
            try:
                mod, self.tcasename, self.funcname = _parse_test_path(self.spec)
                self.modpath = mod.__name__
            except Exception:
                self.status = 'FAIL'
                self.err_msg = traceback.format_exc()
            else:
                if self.funcname is None:
                    self.status = 'FAIL'
                    self.err_msg = 'ERROR: test function not specified.'
                else:
                    if self.tcasename is not None:
                        testcase = getattr(mod, self.tcasename)
                        self.nprocs = getattr(testcase, 'N_PROCS', 0)
                        self.isolated = getattr(testcase, 'ISOLATED', False)

        if self.err_msg:
            self.start_time = self.end_time = time.perf_counter()

    def _run_subproc(self, cmd, queue, env):
        """
        Run a command in a subprocess.
        """
        try:
            add_queue_to_env(queue)

            if self.options.nocapture:
                stdout = subprocess.PIPE
                stderr = subprocess.STDOUT
            else:
                stdout = subprocess.DEVNULL
                stderr = subprocess.PIPE

            p = subprocess.run(cmd, stdout=stdout, stderr=stderr, env=env,
                               timeout=self.options.timeout, universal_newlines=True)

            if p.returncode != 0:
                self.status = 'FAIL'
                self.err_msg = p.stdout if self.options.nocapture else p.stderr
                result = self
            else:
                if self.options.nocapture:
                    print(p.stdout)
                result = queue.get()
        except:
            # we generally shouldn't get here, but just in case,
            # handle it so that the main process doesn't hang at the
            # end when it tries to join all of the concurrent processes.
            self.status = 'FAIL'
            self.err_msg = traceback.format_exc()
            result = self

        return result

    def _run_isolated(self, queue):
        """This runs the test in a subprocess,
        then returns the Test object.
        """

        cmd = [sys.executable,
               os.path.join(os.path.dirname(__file__), 'isolatedrun.py'),
               self.spec]

        try:
            result = self._run_subproc(cmd, queue, os.environ)
        except:
            # we generally shouldn't get here, but just in case,
            # handle it so that the main process doesn't hang at the
            # end when it tries to join all of the concurrent processes.
            self.status = 'FAIL'
            self.err_msg = traceback.format_exc()
            result = self

        for test in result:
            test.isolated = True

        return result

    def _run_mpi(self, queue):
        """This runs the test using mpirun in a subprocess,
        then returns the Test object.
        """
        try:
            if mpirun_exe is None:
                raise Exception("mpirun or mpiexec was not found in the system path.")

            cmd =  [mpirun_exe, '-n', str(self.nprocs),
                   sys.executable,
                   os.path.join(os.path.dirname(__file__), 'mpirun.py'),
                   self.spec] + _options2args()

            result = self._run_subproc(cmd, queue, os.environ)

        except:
            # we generally shouldn't get here, but just in case,
            # handle it so that the main process doesn't hang at the
            # end when it tries to join all of the concurrent processes.
            self.status = 'FAIL'
            self.err_msg = traceback.format_exc()
            result = self

        for test in result:
            test.mpi = True

        return result

    def run(self, queue=None):
        """Runs the test, assuming status is not already known."""
        if self.status is not None:
            # premature failure occurred (or dry run), just return
            return self

        MPI = None
        if self.nprocs > 0 and not self.options.nompi:
            try:
                from mpi4py import MPI
            except ImportError:
                pass
            else:
                if queue is not None:
                    return self._run_mpi(queue)
        elif self.options.isolated:
            return self._run_isolated(queue)

        with testcontext(self):
            testpath, _ = get_testpath(self.spec)
            _, mod = get_module(testpath)

            testcase = getattr(mod, self.tcasename) if self.tcasename is not None else None
            funcname, nprocs = (self.funcname, self.nprocs)

            mod_setup = mod_teardown = tcase_setup = tcase_teardown = None

            if self._mod_fixture_first:
                mod_setup = getattr(mod, 'setUpModule', None)
            if self._mod_fixture_last:
                mod_teardown = getattr(mod, 'tearDownModule', None)

            if testcase is not None:
                if self._tcase_fixture_first:
                    tcase_setup = getattr(testcase, 'setUpClass', None)
                if self._tcase_fixture_last:
                    tcase_teardown = getattr(testcase, 'tearDownClass', None)

                parent = testcase(methodName=funcname)
                # if we get here and nprocs > 0, we need
                # to set .comm in our TestCase instance.
                if nprocs > 0:
                    if MPI is not None and not self.options.nompi:
                        parent.comm = MPI.COMM_WORLD
                    else:
                        parent.comm = FakeComm()
            else:
                parent = mod

            if self.options.nocapture:
                outstream = sys.stdout
            else:
                outstream = DevNull()
            errstream = StringIO()

            done = False
            expected = expected2 = expected3 = False
            subs = []

            try:
                old_err = sys.stderr
                old_out = sys.stdout
                sys.stdout = outstream
                sys.stderr = errstream

                start_coverage()

                self.start_time = time.perf_counter()

                catch_deps = self.options.show_deprecations or self.options.deprecations_report
                raise_deps = self.options.disallow_deprecations

                with warnings.catch_warnings(record=True) if catch_deps else nullcontext() as w:

                    if raise_deps:
                        # raise deprecation warnings as exceptions
                        warnings.filterwarnings("error", category=DeprecationWarning)
                        warnings.filterwarnings("error", category=PendingDeprecationWarning)
                    elif catch_deps:
                        # catch all locations where deprecation warning is triggered
                        warnings.filterwarnings("always", category=DeprecationWarning)
                        warnings.filterwarnings("always", category=PendingDeprecationWarning)

                    # if there's a module setup, run it
                    if mod_setup:
                        status, expected = _try_call(mod_setup)
                        if status != 'OK':
                            done = True
                            mod_teardown = None # don't do teardown if setup failed

                    # handle @unittest.skip class decorator
                    if not done and hasattr(parent, '__unittest_skip__') and parent.__unittest_skip__:
                        sys.stderr.write("%s\n" % parent.__unittest_skip_why__)
                        status = 'SKIP'
                        done = True
                        tcase_setup = None
                        tcase_teardown = None

                    if testcase is None:
                        if not done:
                            status, expected2 = _try_call(getattr(parent, funcname))
                        self.err_msg = errstream.getvalue()
                    else: # use unittest code to run the test and handle subtests
                        if tcase_setup:
                            status, expected = _try_call(tcase_setup)
                            if status != 'OK':
                                done = True
                                tcase_teardown = None

                        result= UnitTestResult()
                        parent.run(result)
                        tname, data = result._tests.popitem()
                        tc, status, err, ut_subtests = data
                        stream_val = errstream.getvalue()
                        if stream_val:
                            stream_val += '\n'
                        else:
                            stream_val = ''
                        if ut_subtests:
                            end_time = time.perf_counter()
                            for sub, err in ut_subtests:
                                subtest = SubTest(sub._subDescription(), self.spec, self.options)
                                subtest.status = status
                                subtest.err_msg = stream_val + err
                                subtest.start_time = self.start_time
                                subtest.end_time = end_time
                                subtest.memory_usage = get_memory_usage()
                                subs.append(subtest)
                        else:
                            if err:
                                self.err_msg = stream_val + err

                    self.end_time = time.perf_counter()
                    self.status = status
                    self.memory_usage = get_memory_usage()
                    self.expected_fail = expected or expected2 or expected3

                    if tcase_teardown:
                        _try_call(tcase_teardown)

                    if mod_teardown:
                        _try_call(mod_teardown)

                    if sys.platform == 'win32':
                        self.load = (0.0, 0.0, 0.0)
                    else:
                        self.load = os.getloadavg()

                    if catch_deps and w:
                        deprecations = [wm for wm in w
                                        if wm.category is DeprecationWarning
                                        or wm.category is PendingDeprecationWarning]
                        for wm in deprecations:
                            msg = str(wm.message)
                            dep = self.deprecations.get(msg, set())
                            dep.add((wm.filename, wm.lineno, self.spec))
                            self.deprecations[msg] = dep

            finally:
                sys.stderr = old_err
                sys.stdout = old_out

        if subs:
            return subs
        return self

    def elapsed(self):
        return self.end_time - self.start_time

    def short_name(self):
        """Returns the testspec with only the file's basename instead
        of its full path.
        """
        testpath, rest = get_testpath(self.spec)
        fname = os.path.basename(testpath)
        return ':'.join((fname, rest))

    def __str__(self):
        if self.err_msg:
            return "%s: %s\n%s" % (self.spec, self.status, self.err_msg)
        else:
            return "%s: %s" % (self.spec, self.status)


class SubTest(Test):
    """
    Like a normal Test, but includes subtest info when being stringified.

    Attributes
    ----------
    submsg : str
        String indicating which subtests were involved.
    """

    def __init__(self, submsg, testspec, options):
        super().__init__(testspec, options)
        self.submsg = submsg

    def __str__(self):
        return "%s: %s %s\n%s" % (self.spec, self.submsg, self.status, self.err_msg)


def _parse_test_path(testspec):
    """Return a tuple of the form (module, testcase, func)
    based on the given testspec.

    The format of testspec is one of the following:
        <module>
        <module>:<testcase>
        <module>:<testcase>.<method>
        <module>:<function>

    where <module> is either the python module path or the actual
    file system path to the .py file.  A value of None in the tuple
    indicates that that part of the testspec was not present.
    """
    testpath, rest = get_testpath(testspec)
    _, mod = get_module(testpath)

    funcname = tcasename = None

    if rest:
        objname, _, funcname = rest.partition('.')
        obj = getattr(mod, objname)
        if isclass(obj) and issubclass(obj, TestCase):
            tcasename = objname
            if funcname:
                meth = getattr(obj, funcname)
                if not ismethod(meth):
                    raise TypeError("'%s' is not a method." % rest)
        elif isinstance(obj, FunctionType):
            funcname = obj.__name__
        else:
            raise TypeError("'%s' is not a TestCase or a function." %
                            objname)

    return (mod, tcasename, funcname)


def _try_call(func):
    """Calls the given method, captures stdout and stderr,
    and returns the status (OK, SKIP, FAIL).
    """
    status = 'OK'
    expected = getattr(func, '__unittest_expecting_failure__', False)

    try:
        func()
    except SkipTest as e:
        status = 'SKIP'
        sys.stderr.write(str(e))
    except _UnexpectedSuccess:
        status = 'OK'
        expected = True
    except Exception:
        status = 'FAIL'
        sys.stderr.write(traceback.format_exc())

    return status, expected
