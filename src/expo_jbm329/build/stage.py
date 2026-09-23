"""Stage built onedir artifacts for release packaging."""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, metadata
from typing import TYPE_CHECKING

from expo_jbm329.build.build_utils import (
    detect_platform,
    dist_dir,
    prepare_clean_directory,
    project_root,
    staging_dir,
)

if TYPE_CHECKING:
    from pathlib import Path


APP_NAME = "Expo Studio"
APP_SLUG = "ExpoStudio"
PACKAGE_NAME = "expo_jbm329"
SOURCE_CODE_URL = "https://github.com/jbm329/expo-studio"
DOCUMENTATION_FILES = ("LICENSE.txt", "README.md", "CHANGELOG.md")
RELEASE_NOTES_FILE = "RELEASE-NOTES.txt"


@dataclass(frozen=True)
class ReleaseMetadata:
    """Metadata used for staged release notes."""

    app_name: str
    app_slug: str
    package: str
    version: str
    license: str
    platform: str


@dataclass(frozen=True)
class StagePaths:
    """Filesystem paths used by the staging step."""

    root: Path
    dist_expo_dir: Path
    staging_dir: Path


def build_metadata() -> ReleaseMetadata:
    """Return normalized metadata used for release staging."""
    try:
        package_metadata = metadata(PACKAGE_NAME)
        version = package_metadata.get("Version", "unknown")
        license_name = (
            package_metadata.get("License-Expression") or package_metadata.get("License") or "GPL-3.0-or-later"
        )
    except PackageNotFoundError:
        version = "dev"
        license_name = "GPL-3.0-or-later"

    return ReleaseMetadata(
        app_name=APP_NAME,
        app_slug=APP_SLUG,
        package=PACKAGE_NAME,
        version=version,
        license=license_name,
        platform=detect_platform(),
    )


def build_release_notes(release_metadata: ReleaseMetadata, build_type: str = "onedir") -> str:
    """Return release notes text for staged release artifacts.

    Args:
        release_metadata: Metadata to include in the generated notes.
        build_type: Build type represented by the staged artifacts.

    Returns:
        Release notes text.
    """
    now = datetime.now(UTC).astimezone()
    return (
        f"{release_metadata.app_name}\n"
        f"Version: {release_metadata.version}\n\n"
        f"Build date: {now.isoformat(timespec='seconds')}\n"
        f"Platform: {release_metadata.platform}\n"
        f"Build type: {build_type}\n\n"
        f"License: {release_metadata.license}\n"
        f"Source code: {SOURCE_CODE_URL}\n\n"
        "This is a standalone desktop build created from the open source project.\n"
        "The application is provided as-is and developed as a personal side project.\n"
    )


def _stage_paths() -> StagePaths:
    """Return paths used by the staging step."""
    root = project_root()
    return StagePaths(
        root=root,
        dist_expo_dir=dist_dir() / "expo",
        staging_dir=staging_dir(),
    )


def _required_source_files(root: Path) -> dict[str, Path]:
    """Return source documentation files required for staging."""
    return {file_name: root / file_name for file_name in DOCUMENTATION_FILES}


def _validate_sources(paths: StagePaths, documentation_files: dict[str, Path]) -> bool:
    """Validate that all required source artifacts exist before staging."""
    missing: list[Path] = []

    if not paths.dist_expo_dir.is_dir():
        missing.append(paths.dist_expo_dir)

    missing.extend(source_path for source_path in documentation_files.values() if not source_path.is_file())

    if not missing:
        return True

    print("[stage] Missing required source files or directories:", file=sys.stderr)
    for path in missing:
        print(f" - {path}", file=sys.stderr)
    return False


def _copy_documentation_files(documentation_files: dict[str, Path], target_dir: Path) -> None:
    """Copy required documentation files into the staging directory."""
    for file_name, source_path in documentation_files.items():
        shutil.copy2(source_path, target_dir / file_name)


def _copy_dist_expo(source_dir: Path, target_dir: Path) -> None:
    """Copy the PyInstaller onedir output while preserving POSIX symlinks."""
    shutil.copytree(source_dir, target_dir, symlinks=True)


def _write_release_notes(target_dir: Path, release_metadata: ReleaseMetadata) -> Path:
    """Generate release notes in the staging directory."""
    release_notes_path = target_dir / RELEASE_NOTES_FILE
    release_notes_path.write_text(
        build_release_notes(release_metadata=release_metadata),
        encoding="utf-8",
    )
    return release_notes_path


def _missing_staged_dist_entries(source_dir: Path, target_dir: Path) -> list[Path]:
    """Return copied dist entries that are missing from the staging directory."""
    missing: list[Path] = []
    for source_path in source_dir.rglob("*"):
        target_path = target_dir / source_path.relative_to(source_dir)

        if source_path.is_symlink():
            if not target_path.is_symlink():
                missing.append(target_path)
        elif source_path.is_dir():
            if not target_path.is_dir():
                missing.append(target_path)
        elif source_path.is_file() and not target_path.is_file():
            missing.append(target_path)

    return missing


def _validate_staging_output(paths: StagePaths) -> bool:
    """Validate that all expected staged files exist."""
    staged_expo_dir = paths.staging_dir / "expo"
    missing = [staged_expo_dir] if not staged_expo_dir.is_dir() else []
    missing.extend(_missing_staged_dist_entries(source_dir=paths.dist_expo_dir, target_dir=staged_expo_dir))
    missing.extend(
        path for path in (paths.staging_dir / file_name for file_name in DOCUMENTATION_FILES) if not path.is_file()
    )

    release_notes_path = paths.staging_dir / RELEASE_NOTES_FILE
    if not release_notes_path.is_file():
        missing.append(release_notes_path)

    if not missing:
        return True

    print("[stage] Missing expected staged files or directories:", file=sys.stderr)
    for path in missing:
        print(f" - {path}", file=sys.stderr)
    return False


def stage_onedir() -> int:
    """Stage the built onedir artifact and release documentation.

    Returns:
        Exit code where 0 indicates success and non-zero indicates failure.
    """
    paths = _stage_paths()
    documentation_files = _required_source_files(paths.root)

    print(f"[stage] root={paths.root}")
    print(f"[stage] dist_expo={paths.dist_expo_dir}")
    print(f"[stage] staging={paths.staging_dir}")

    if not _validate_sources(paths=paths, documentation_files=documentation_files):
        return 1

    try:
        prepare_clean_directory(paths.staging_dir)
    except OSError as exc:
        print(f"[stage] Failed to prepare staging directory: {exc}", file=sys.stderr)
        return 1

    try:
        _copy_dist_expo(source_dir=paths.dist_expo_dir, target_dir=paths.staging_dir / "expo")
        _copy_documentation_files(documentation_files=documentation_files, target_dir=paths.staging_dir)
        _write_release_notes(target_dir=paths.staging_dir, release_metadata=build_metadata())
    except (OSError, shutil.Error) as exc:
        print(f"[stage] Failed to stage artifacts: {exc}", file=sys.stderr)
        return 1

    if not _validate_staging_output(paths):
        return 1

    print(f"[stage] SUCCESS: {paths.staging_dir}")
    return 0


def main() -> None:
    """Entry point for staging onedir release artifacts."""
    raise SystemExit(stage_onedir())


if __name__ == "__main__":
    main()
