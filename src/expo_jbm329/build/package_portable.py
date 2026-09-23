"""Create portable release archives from staged artifacts."""

from __future__ import annotations

import sys
import zipfile
from typing import TYPE_CHECKING

from expo_jbm329.build.build_utils import detect_platform, release_dir, staging_dir
from expo_jbm329.build.version import get_documentation_files, get_release_name, get_release_notes_file

if TYPE_CHECKING:
    from pathlib import Path


def _archive_name() -> str:
    """Return the portable ZIP archive name."""
    return get_release_name(platform=detect_platform(), package_type="portable", extension="zip")


def _required_paths(stage_dir: Path) -> list[Path]:
    """Return required staged files and directories for portable packaging."""
    return [
        stage_dir / "expo",
        *(stage_dir / file_name for file_name in get_documentation_files()),
        stage_dir / get_release_notes_file(),
    ]


def _validate_inputs(stage_dir: Path) -> bool:
    """Validate required staged files and directories."""
    missing = [path for path in _required_paths(stage_dir) if not path.exists()]
    if not missing:
        return True

    print("[package-portable] Missing required staged files or directories:", file=sys.stderr)
    for path in missing:
        print(f" - {path}", file=sys.stderr)
    return False


def _write_staging_zip(stage_dir: Path, archive_path: Path) -> None:
    """Write the staging directory contents to a ZIP archive."""
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(stage_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(stage_dir))


def package_portable_zip() -> int:
    """Create a portable ZIP archive from staged release artifacts.

    Returns:
        Exit code where 0 indicates success and non-zero indicates failure.
    """
    stage_dir = staging_dir()
    archive_path = release_dir() / _archive_name()

    print(f"[package-portable] staging={stage_dir}")
    print(f"[package-portable] archive={archive_path}")

    if not _validate_inputs(stage_dir):
        return 1

    archive_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        _write_staging_zip(stage_dir=stage_dir, archive_path=archive_path)
    except OSError as exc:
        print(f"[package-portable] Failed to create portable archive: {exc}", file=sys.stderr)
        return 1

    if not archive_path.is_file():
        print(f"[package-portable] Archive was not created: {archive_path}", file=sys.stderr)
        return 1

    print(f"[package-portable] SUCCESS: {archive_path}")
    return 0
