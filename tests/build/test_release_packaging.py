from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from expo_jbm329.build import build_utils, package_windows, release, version

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.parametrize(
    ("package_version", "platform", "expected"),
    [
        ("1.0.0", "windows", "ExpoStudio-1.0.0-win64.zip"),
        ("1.0.0", "linux", "ExpoStudio-1.0.0-linux.tar.gz"),
        ("1.0.0", "macos", "ExpoStudio-1.0.0-macos.tar.gz"),
        ("1.0.0a1", "windows", "ExpoStudio-1.0.0-a1-win64.zip"),
        ("1.0.0b2", "linux", "ExpoStudio-1.0.0-b2-linux.tar.gz"),
        ("1.0.0rc1", "macos", "ExpoStudio-1.0.0-rc1-macos.tar.gz"),
        ("1.0.0rc1", "linux", "ExpoStudio-1.0.0-rc1-linux.tar.gz"),
    ],
)
def test_release_archive_names_are_date_free(
    monkeypatch: pytest.MonkeyPatch,
    package_version: str,
    platform: str,
    expected: str,
) -> None:
    monkeypatch.setattr(version, "get_version", lambda: package_version)

    extension = "zip" if platform == "windows" else "tar.gz"

    assert version.get_release_name(platform=platform, extension=extension) == expected


@pytest.mark.parametrize(
    ("package_version", "expected"),
    [
        ("1.0.0", "ExpoStudio-1.0.0-win64-setup.exe"),
        ("1.0.0rc1", "ExpoStudio-1.0.0-rc1-win64-setup.exe"),
    ],
)
def test_windows_installer_name_uses_setup_suffix(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    package_version: str,
    expected: str,
) -> None:
    monkeypatch.setattr(version, "get_version", lambda: package_version)

    output_base_filename = package_windows._installer_output_base_filename()
    installer_path = package_windows._installer_artifact_path(tmp_path, output_base_filename)

    assert installer_path.name == expected


def test_windows_release_runs_installer_then_zip(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(release, "package_windows_installer", lambda: calls.append("setup") or 0)
    monkeypatch.setattr(release, "package_zip", lambda: calls.append("zip") or 0)

    assert release._run_windows_packaging() == 0
    assert calls == ["setup", "zip"]


def test_release_artifacts_directory_is_centralized_and_created(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    release_root = tmp_path / "release"
    monkeypatch.setattr(build_utils, "release_dir", lambda: release_root)

    artifacts_dir = build_utils.release_artifacts_dir()
    assert artifacts_dir == release_root / "artifacts"
    assert not artifacts_dir.exists()

    assert build_utils.ensure_release_artifacts_dir() == artifacts_dir
    assert artifacts_dir.is_dir()
