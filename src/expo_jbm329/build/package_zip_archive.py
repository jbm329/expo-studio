"""Create a ZIP archive from staged release artifacts."""

from __future__ import annotations

import sys
import zipfile
from typing import TYPE_CHECKING

from expo_jbm329.build.build_utils import detect_platform, ensure_release_artifacts_dir, staging_dir
from expo_jbm329.build.version import create_sha256, get_documentation_files, get_release_name, get_release_notes_file

if TYPE_CHECKING:
    from pathlib import Path


def _archive_name() -> str:
    """Return the ZIP archive name."""
    return get_release_name(platform=detect_platform(), extension="zip")


def _required_paths(stage_dir: Path) -> list[Path]:
    """Return required staged files and directories for ZIP packaging."""
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

    print("[package-zip] Missing required staged files or directories:", file=sys.stderr)
    for path in missing:
        print(f" - {path}", file=sys.stderr)
    return False


def _write_staging_zip(stage_dir: Path, archive_path: Path) -> None:
    """Write the staging directory contents to a ZIP archive."""
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(stage_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(stage_dir))


def _create_checksum(artifact_path: Path) -> bool:
    """Create and verify a checksum file for an artifact."""
    try:
        checksum_path = create_sha256(artifact_path)
    except OSError as exc:
        print(f"[package-zip] Failed to create checksum: {exc}", file=sys.stderr)
        return False

    if not checksum_path.is_file():
        print(f"[package-zip] Checksum file was not created: {checksum_path}", file=sys.stderr)
        return False

    print(f"[package-zip] SHA256: {checksum_path}")
    return True


def package_zip() -> int:
    """Create a ZIP archive from staged release artifacts.

    Returns:
        Exit code where 0 indicates success and non-zero indicates failure.
    """
    stage_dir = staging_dir()

    print(f"[package-zip] staging={stage_dir}")

    if not _validate_inputs(stage_dir):
        return 1

    try:
        archive_path = ensure_release_artifacts_dir() / _archive_name()
    except OSError as exc:
        print(f"[package-zip] Failed to create artifacts directory: {exc}", file=sys.stderr)
        return 1

    print(f"[package-zip] archive={archive_path}")

    try:
        _write_staging_zip(stage_dir=stage_dir, archive_path=archive_path)
    except OSError as exc:
        print(f"[package-zip] Failed to create ZIP archive: {exc}", file=sys.stderr)
        return 1

    if not archive_path.is_file():
        print(f"[package-zip] Archive was not created: {archive_path}", file=sys.stderr)
        return 1

    if not _create_checksum(archive_path):
        return 1

    print(f"[package-zip] SUCCESS: {archive_path}")
    return 0
