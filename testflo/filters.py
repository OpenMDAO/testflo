from __future__ import print_function

import os


class TimeFilter(object):
    """This iterator saves to the specified output file only those tests
    that complete successfully in max_time seconds or less.  This output
    file can later be fed into testflo to limit the tests to those in the
    file.
    """
    def __init__(self, max_time, outfile='quicktests.in'):
        self.outfile = outfile
        self.max_time = max_time

    def get_iter(self, input_iter):
        with open(self.outfile, 'w') as f:
            for result in input_iter:
                if result.status == 'OK' and result.elapsed() <= self.max_time:
                    print(result.spec, file=f)
                yield result


class FailFilter(object):
    """This iterator saves to the specified output file only those tests
    that fail.  This output file can later be fed into testflo to limit the
    tests to those in the file.

    Specs written to the file are sorted to make it easier to compare test runs.
    """
    def __init__(self, outfile):
        self.outfile = outfile

    def get_iter(self, input_iter):
        try:
            os.remove(self.outfile)
        except OSError:
            pass

        for result in input_iter:
            if result.status == 'FAIL' and not result.expected_fail:
                with open(self.outfile, 'a') as f:
                    if result.nprocs > 1:
                        spec = f"{result.spec}  # mpi, nprocs={result.nprocs}"
                    else:
                        spec = result.spec
                    print(spec, file=f)
            yield result
