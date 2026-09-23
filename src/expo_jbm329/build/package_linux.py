"""Create Linux portable release archives from staged artifacts."""

from __future__ import annotations

import os
import sys
import tarfile
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from expo_jbm329.build.build_utils import detect_platform, release_dir, staging_dir
from expo_jbm329.build.stage import DOCUMENTATION_FILES, RELEASE_NOTES_FILE, build_metadata

if TYPE_CHECKING:
    from pathlib import Path


EXECUTABLE_NAME = "expo"


def _archive_base_name() -> str:
    """Return the Linux portable archive base name without extension."""
    release_metadata = build_metadata()
    date_str = datetime.now(UTC).astimezone().strftime("%Y-%m-%d")
    return f"{release_metadata.app_slug}-{release_metadata.version}-linux-portable-{date_str}"


def _archive_path() -> Path:
    """Return the Linux portable archive output path."""
    return release_dir() / f"{_archive_base_name()}.tar.gz"


def _required_paths(stage_dir: Path) -> list[Path]:
    """Return required staged files and directories for Linux packaging."""
    return [
        stage_dir / "expo",
        stage_dir / "expo" / EXECUTABLE_NAME,
        *(stage_dir / file_name for file_name in DOCUMENTATION_FILES),
        stage_dir / RELEASE_NOTES_FILE,
    ]


def _validate_inputs(stage_dir: Path) -> bool:
    """Validate required staged files, directories, and executable permissions."""
    missing = [path for path in _required_paths(stage_dir) if not path.exists()]
    if missing:
        print("[package-linux] Missing required staged files or directories:", file=sys.stderr)
        for path in missing:
            print(f" - {path}", file=sys.stderr)
        return False

    executable_path = stage_dir / "expo" / EXECUTABLE_NAME
    if not executable_path.is_file():
        print(f"[package-linux] Expected executable is not a file: {executable_path}", file=sys.stderr)
        return False

    if not os.access(executable_path, os.X_OK):
        print(f"[package-linux] Expected executable is not executable: {executable_path}", file=sys.stderr)
        return False

    return True


def _write_staging_tarball(stage_dir: Path, archive_path: Path, archive_root_name: str) -> None:
    """Write the staging directory contents to a gzipped tar archive."""
    with tarfile.open(archive_path, "w:gz", dereference=False) as archive:
        for path in sorted(stage_dir.iterdir()):
            archive.add(path, arcname=f"{archive_root_name}/{path.name}", recursive=True)


def package_linux_tarball() -> int:
    """Create a Linux portable tar.gz archive from staged release artifacts.

    Returns:
        Exit code where 0 indicates success and non-zero indicates failure.
    """
    platform_name = detect_platform()
    if platform_name != "linux":
        print(f"[package-linux] Linux packaging cannot run on platform: {platform_name}", file=sys.stderr)
        return 1

    stage_dir = staging_dir()
    archive_base_name = _archive_base_name()
    archive_path = release_dir() / f"{archive_base_name}.tar.gz"

    print(f"[package-linux] staging={stage_dir}")
    print(f"[package-linux] archive={archive_path}")

    if not _validate_inputs(stage_dir):
        return 1

    archive_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        _write_staging_tarball(
            stage_dir=stage_dir,
            archive_path=archive_path,
            archive_root_name=archive_base_name,
        )
    except (OSError, tarfile.TarError) as exc:
        print(f"[package-linux] Failed to create Linux archive: {exc}", file=sys.stderr)
        return 1

    if not archive_path.is_file():
        print(f"[package-linux] Archive was not created: {archive_path}", file=sys.stderr)
        return 1

    print(f"[package-linux] SUCCESS: {archive_path}")
    return 0
