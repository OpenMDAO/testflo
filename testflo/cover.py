"""
Methods to provide code coverage using coverage.py.
"""
import os
import sys
import webbrowser

try:
    import coverage
    from coverage.collector import Collector
except ImportError:
    coverage = None


def setup_coverage(options):
    """
    Programmatically initializes coverage for the current process.
    Ensures absolute paths for temp-dir safety and avoids double-init.
    """
    if not (options.coverage or options.coveragehtml):
        return None

    # Prevent double-initialization
    if Collector._collectors:
        return None

    cover_dir = options.cover_dir or os.getcwd()
    data_file = os.path.join(cover_dir, '.coverage')
    cfg_file = os.path.join(cover_dir, '.coveragerc')

    cov = coverage.Coverage(
        config_file=cfg_file,
        data_file=data_file,
        data_suffix=True,
        branch=options.cover_branch,
    )

    cov.config.ignore_errors = True

    if sys.version_info >= (3, 13):
        cov.set_option("run:core", "sysmon")

    if options.coverpkgs:
        cov.set_option("run:source", options.coverpkgs)
    if options.cover_omits:
        omits = cov.get_option("run:omit")
        if omits:
            omits.extend(options.cover_omits)
        else:
            omits = options.cover_omits
        cov.set_option("run:omit", omits)

    cov.set_option("run:disable_warnings", ["module-not-imported", "no-data-collected",
                   "couldnt-parse"])
    cov.set_option("report:ignore_errors", True)
    cov.set_option("report:sort", "-cover")
    cov.set_option("report:exclude_lines", [
        "pragma: no cover",
        "if __name__ == .__main__.:",
        "raise NotImplementedError",
        "def __repr__",
    ])

    return cov


def finalize_coverage(options, cov):
    """
    Combines all parallel coverage files and generates an HTML report.
    """
    if cov is None:
        return

    cov.save()

    data_dir = options.cover_dir

    # Combine all coverage files found in the data_dir
    try:
        cov.combine(data_paths=[data_dir])
    except coverage.exceptions.CoverageException as e:
        print(f"Combining coverage files failed: {e}", file=sys.stderr)
        return

    if options.coverage:
        print("\n--- Coverage Summary ---")
        cov.report(ignore_errors=True, skip_empty=True)

    if options.coveragehtml:
        html_dir = os.path.join(data_dir, 'htmlcov')
        cov.html_report(directory=html_dir, ignore_errors=True, skip_empty=True,
                        show_contexts=options.dyn_contexts)
        index_file = os.path.join(html_dir, 'index.html')
        if sys.platform == 'darwin':
            os.system('open %s' % index_file)
        else:
            webbrowser.get().open(index_file)

        print(f"\nHTML report generated at: {index_file}")

    return cov