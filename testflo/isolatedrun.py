
"""
This is meant to be executed as a subprocess of testflo.

"""

if __name__ == '__main__':

    import sys
    import os
    import traceback

    from testflo.test import Test
    from testflo.qman import get_client_queue
    from testflo.options import get_options
    from testflo.cover import setup_coverage

    queue = get_client_queue()
    os.environ['TESTFLO_QUEUE'] = ''

    options = get_options()
    test = None

    if options.coverage or options.coveragehtml:
        cov = setup_coverage(options)
    else:
        cov = None

    try:
        test = Test(sys.argv[1], options)
        test.nocapture = True # so we don't lose stdout
        test.run(cov=cov)
    except:
        test.status = 'FAIL'
        test.err_msg = traceback.format_exc()
    finally:
        sys.stdout.flush()
        sys.stderr.flush()

        queue.put(test)

        if cov is not None:
            cov.save()
