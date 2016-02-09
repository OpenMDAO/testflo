"""
This is for running a test in a subprocess.
"""

import sys
import os
import traceback
import time
import subprocess
import resource
import json

from tempfile import TemporaryFile

from testflo.util import _get_parser, attr_dict
from testflo.runner import TestRunner, exit_codes
from testflo.result import TestResult
from testflo.cover import save_coverage


def run_isolated(testspec, args):
    """This runs the test in a subprocess,
    then returns the TestResult object.
    """

    ferr = None

    try:
        start = time.time()

        ferr = TemporaryFile(mode='w+t')

        cmd = [sys.executable,
               os.path.join(os.path.dirname(__file__), 'isolated.py'),
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
        if s:
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
        sys.stderr.flush()
        if ferr:
            ferr.close()

    return result


class IsolatedTestRunner(TestRunner):
    """TestRunner that runs each test in a separate process."""

    def __init__(self, options, args):
        super(IsolatedTestRunner, self).__init__(options)
        self.get_iter = self.run_isolated_tests
        self.options = options
        self.args = [a for a in args if a not in options.tests]

    def run_isolated_tests(self, input_iter):
        """Run each test isolated in a separate process."""

        # use this test runner in the subprocesses
        self.options.isolated = False
        self.options.num_procs = 1

        for testspec in input_iter:
            if isinstance(testspec, TestResult):
                # test already failed during discovery, probably an
                # import failure
                yield testspec
            else:
                yield run_isolated(testspec, self.args)


if __name__ == '__main__':

    exitcode = 0
    info = {}

    try:
        options = _get_parser().parse_args()
        runner = TestRunner(options)
        for result in runner.get_iter([options.tests[0]]):
            break

        # collect resource usage data
        info['rdata'] = attr_dict(resource.getrusage(resource.RUSAGE_SELF))

        # check for error and write error message to stderr
        if result.status != 'OK':
            info['err_msg'] = result.err_msg
            exitcode = exit_codes[result.status]

        save_coverage()

    except:
        info['err_msg'] = traceback.format_exc()
        exitcode = exit_codes['FAIL']

    finally:
        sys.stderr.write(json.dumps(info))
        sys.stderr.flush()
        sys.stdout.flush()
        sys.exit(exitcode)
