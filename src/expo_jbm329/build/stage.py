"""Stage built onedir artifacts for release packaging."""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from expo_jbm329.build.build_utils import (
    dist_dir,
    prepare_clean_directory,
    project_root,
    pyinstaller_work_dir,
    staging_dir,
)
from expo_jbm329.build.notices.cli import run_third_party_notices
from expo_jbm329.build.notices.pyinstaller_toc import COLLECT_TOC_FILE
from expo_jbm329.build.version import (
    ReleaseMetadata,
    build_metadata,
    get_artifact_platform,
    get_build_info_file,
    get_documentation_files,
    get_source_code_url,
    get_third_party_notice_files,
)

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True)
class StagePaths:
    """Filesystem paths used by the staging step."""

    root: Path
    dist_expo_dir: Path
    staging_dir: Path
    work_dir: Path


def build_build_info(release_metadata: ReleaseMetadata, build_type: str = "onedir") -> str:
    """Return build information text for staged release artifacts.

    Args:
        release_metadata: Metadata to include in the generated build information.
        build_type: Build type represented by the staged artifacts.

    Returns:
        Build information text.
    """
    now = datetime.now(UTC).astimezone()
    return (
        f"{release_metadata.app_name}\n"
        f"Version: {release_metadata.version}\n\n"
        f"Build date: {now.isoformat(timespec='seconds')}\n"
        f"Platform: {get_artifact_platform(release_metadata.platform)}\n"
        f"Build type: {build_type}\n\n"
        f"License: {release_metadata.license}\n"
        f"Source code: {get_source_code_url()}\n\n"
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
        work_dir=pyinstaller_work_dir(),
    )


def _required_source_files(root: Path) -> dict[str, Path]:
    """Return source documentation files required for staging."""
    return {file_name: root / file_name for file_name in get_documentation_files()}


def _validate_sources(paths: StagePaths, documentation_files: dict[str, Path]) -> bool:
    """Validate that all required source artifacts exist before staging."""
    missing: list[Path] = []

    if not paths.dist_expo_dir.is_dir():
        missing.append(paths.dist_expo_dir)

    # Third-party notices are derived from the PyInstaller TOC files of the same build.
    collect_toc = paths.work_dir / COLLECT_TOC_FILE
    if not collect_toc.is_file():
        missing.append(collect_toc)

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


def _write_build_info(target_dir: Path, release_metadata: ReleaseMetadata) -> Path:
    """Generate build information in the staging directory."""
    build_info_path = target_dir / get_build_info_file()
    build_info_path.write_text(
        build_build_info(release_metadata=release_metadata),
        encoding="utf-8",
    )
    return build_info_path


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
        path
        for path in (
            paths.staging_dir / file_name for file_name in (*get_documentation_files(), *get_third_party_notice_files())
        )
        if not path.is_file()
    )

    build_info_path = paths.staging_dir / get_build_info_file()
    if not build_info_path.is_file():
        missing.append(build_info_path)

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
    print(f"[stage] work_dir={paths.work_dir}")
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
        _write_build_info(target_dir=paths.staging_dir, release_metadata=build_metadata())
    except (OSError, shutil.Error) as exc:
        print(f"[stage] Failed to stage artifacts: {exc}", file=sys.stderr)
        return 1

    if not run_third_party_notices(
        onedir_dir=paths.staging_dir / "expo",
        work_dir=paths.work_dir,
        output_dir=paths.staging_dir,
        log_prefix="[stage]",
    ):
        print("[stage] Third-party notice validation failed.", file=sys.stderr)
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
