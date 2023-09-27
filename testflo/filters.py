from __future__ import print_function

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
        fails = []
        for result in input_iter:
            if result.status == 'FAIL' and not result.expected_fail:
                fails.append(result.spec)
            yield result

        if fails:
            with open(self.outfile, 'w') as f:
                for spec in sorted(fails):
                    print(spec, file=f)
