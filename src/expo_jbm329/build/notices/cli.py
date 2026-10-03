"""Command-line entry points for third-party notice generation."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from expo_jbm329.build.build_utils import dist_dir, project_root, pyinstaller_work_dir
from expo_jbm329.build.notices.license_overrides import (
    OVERRIDES_DIRECTORY_NAME,
    OVERRIDES_FILE_NAME,
    LicenseOverrideError,
)
from expo_jbm329.build.notices.pyinstaller_toc import TocFormatError
from expo_jbm329.build.notices.service import create_default_config, generate_third_party_notices

if TYPE_CHECKING:
    from pathlib import Path

    from expo_jbm329.build.notices.models import NoticeReport

DEFAULT_OUTPUT_DIRECTORY = ("build", "third-party-notices")


def _license_status_line(report: NoticeReport) -> str:
    """Return a one-line summary of whether all components have complete license information."""
    components_needing_action = sorted(
        {issue.component for issue in report.errors if issue.component is not None},
        key=str.casefold,
    )
    if not report.has_errors:
        return f"License check: OK, all {len(report.components)} third-party components are resolved"
    if not components_needing_action:
        return "License check: FAILED, see errors above"
    return (
        f"License check: FAILED, {len(components_needing_action)} component(s) need action: "
        f"{', '.join(components_needing_action)} (see {OVERRIDES_DIRECTORY_NAME}/{OVERRIDES_FILE_NAME})"
    )


def print_report(report: NoticeReport, log_prefix: str) -> None:
    """Print a summary of a notice report with all warnings and errors.

    Args:
        report: Analysis result.
        log_prefix: Prefix for printed lines, for example ``[stage]``.
    """
    print(
        f"{log_prefix} Third-party components: {len(report.components)}, "
        f"first-party files: {report.first_party_file_count}, "
        f"warnings: {len(report.warnings)}, errors: {len(report.errors)}"
    )
    for issue in report.warnings:
        print(f"{log_prefix} WARNING: {issue.message}")
    for issue in report.errors:
        print(f"{log_prefix} ERROR: {issue.message}", file=sys.stderr)
    status_stream = sys.stderr if report.has_errors else sys.stdout
    print(f"{log_prefix} {_license_status_line(report)}", file=status_stream)


def run_third_party_notices(onedir_dir: Path, work_dir: Path, output_dir: Path, log_prefix: str) -> bool:
    """Analyse a onedir build, write notice documents and print the result.

    Args:
        onedir_dir: Onedir output directory to analyse.
        work_dir: PyInstaller work directory of the same build.
        output_dir: Directory to write the notice documents to.
        log_prefix: Prefix for printed lines.

    Returns:
        True if the analysis found no errors, otherwise False.
    """
    try:
        config = create_default_config(dist_dir=onedir_dir, work_dir=work_dir)
        report = generate_third_party_notices(config, output_dir)
    except (OSError, TocFormatError, LicenseOverrideError) as exc:
        print(f"{log_prefix} Failed to generate third-party notices: {exc}", file=sys.stderr)
        return False

    print_report(report, log_prefix)
    print(f"{log_prefix} Third-party notices written to {output_dir}")
    return not report.has_errors


def main() -> None:
    """Analyse ``dist/expo`` and write notice documents to ``build/third-party-notices``."""
    output_dir = project_root().joinpath(*DEFAULT_OUTPUT_DIRECTORY)
    succeeded = run_third_party_notices(
        onedir_dir=dist_dir() / "expo",
        work_dir=pyinstaller_work_dir(),
        output_dir=output_dir,
        log_prefix="[notices]",
    )
    raise SystemExit(0 if succeeded else 1)
