"""
Method and class for running tests under MPI.
"""

import sys
import os
import traceback
import time
import subprocess
import json
from tempfile import TemporaryFile

from testflo.runner import parse_test_path, exit_codes
from testflo.isolated import IsolatedTestRunner, run_isolated
from testflo.result import TestResult


def run_mpi(testspec, nprocs, args):
    """This runs the test using mpirun in a subprocess,
    then returns the TestResult object.
    """

    ferr = None
    info = {}

    try:
        start = time.time()

        ferr = TemporaryFile(mode='w+t')

        from distutils import spawn
        mpirun_exe = None
        if spawn.find_executable("mpirun") is not None:
            mpirun_exe = "mpirun"
        elif spawn.find_executable("mpiexec") is not None:
            mpirun_exe = "mpiexec"

        if mpirun_exe is None:
            raise Exception("mpirun or mpiexec was not found in the system path.")

        cmd = [mpirun_exe, '-n', str(nprocs),
               sys.executable,
               os.path.join(os.path.dirname(__file__), 'mpirun.py'),
               testspec]
        cmd = cmd+args
        p = subprocess.Popen(cmd, stderr=ferr, env=os.environ)
        p.wait()
        end = time.time()

        for status, val in exit_codes.items():
            if val == p.returncode:
                break
        else:
            status = 'FAIL'

        ferr.seek(0)
        with ferr:
            s = ferr.read()
        if s and s.startswith('{'):
            info = json.loads(s)

        result = TestResult(testspec, start, end, status,
                            info.get('err_msg', ''), info.get('rdata', {}))

    except:
        # we generally shouldn't get here, but just in case,
        # handle it so that the main process doesn't hang at the
        # end when it tries to join all of the concurrent processes.
        result = TestResult(testspec, 0., 0., 'FAIL',
                            traceback.format_exc())

    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        if ferr:
            ferr.close()

    return result


class IsolatedMPITestRunner(IsolatedTestRunner):
    def run_isolated_tests(self, input_iter):
        """Run test concurrently."""

        for testspec in input_iter:
            if isinstance(testspec, TestResult):
                # test already failed during discovery, probably an
                # import failure
                yield testspec
            else:
                fname, mod, testcase, method = parse_test_path(testspec)
                self.testcase = testcase

                if testcase and hasattr(testcase, 'N_PROCS'):
                    yield run_mpi(testspec, testcase.N_PROCS, self.args)
                else:
                    yield run_isolated(testspec, self.args)
