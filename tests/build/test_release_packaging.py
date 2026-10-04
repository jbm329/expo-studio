from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

import pytest

from expo_jbm329.build import (
    build_utils,
    package_linux,
    package_macos,
    package_windows,
    package_zip_archive,
    release,
    stage,
    version,
)

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


@pytest.mark.parametrize(
    ("platform", "expected"),
    [("windows", "win64"), ("linux", "linux"), ("macos", "macos")],
)
def test_build_info_platform_matches_artifact_label(platform: str, expected: str) -> None:
    metadata = replace(version.build_metadata(), platform=platform)

    text = stage.build_build_info(metadata)

    assert f"Platform: {expected}\n" in text
    assert version.get_artifact_platform(platform) == expected


def test_staging_writes_build_info(tmp_path: Path) -> None:
    metadata = replace(version.build_metadata(), platform="windows")

    path = stage._write_build_info(tmp_path, metadata)

    assert path == tmp_path / "BUILD-INFO.txt"
    assert "Platform: win64\n" in path.read_text(encoding="utf-8")
    assert not (tmp_path / "RELEASE-NOTES.txt").exists()


def test_packagers_require_build_info(tmp_path: Path) -> None:
    paths = replace(package_windows._paths(), staging_dir=tmp_path)
    required_paths = [
        package_zip_archive._required_paths(tmp_path),
        package_linux._required_paths(tmp_path, "linux"),
        package_macos._required_paths(tmp_path, "macos"),
        package_windows._required_paths(paths),
    ]

    for required in required_paths:
        assert tmp_path / version.get_build_info_file() in required
        assert tmp_path / "RELEASE-NOTES.txt" not in required


def test_installer_offers_optional_installed_notice_viewing(tmp_path: Path) -> None:
    app_id_path = tmp_path / "installer.appid"
    app_id_path.write_text("{00000000-0000-0000-0000-000000000001}\n", encoding="utf-8")
    paths = replace(
        package_windows._paths(),
        staging_dir=tmp_path / "staging",
        build_dir=tmp_path / "installer",
        generated_script_path=tmp_path / "installer" / "installer.iss",
        app_id_path=app_id_path,
    )

    script_path = package_windows.render_inno_script(
        paths, version.build_metadata(), output_base_filename="test-installer"
    )
    script = script_path.read_text(encoding="utf-8")

    assert "InfoAfterFile=" not in script
    assert "RELEASE-NOTES" not in script
    assert (
        f'Source: "{package_windows._windows_path(paths.staging_dir / version.BUILD_INFO_FILE)}"; DestDir: "{{app}}"'
    ) in script
    assert (
        f'Source: "{package_windows._windows_path(paths.staging_dir / version.THIRD_PARTY_NOTICES_FILE)}"; '
        'DestDir: "{app}"'
    ) in script
    assert "english.thirdpartylicenses=View third-party licenses" in script
    assert "swedish.thirdpartylicenses=Visa tredjepartslicenser" in script
    notice_run = next(line for line in script.splitlines() if 'Description: "{cm:thirdpartylicenses}"' in line)
    assert f'Filename: "{{app}}\\{version.THIRD_PARTY_NOTICES_FILE}"' in notice_run
    for flag in ("shellexec", "nowait", "postinstall", "unchecked", "skipifsilent", "runasoriginaluser"):
        assert flag in notice_run.split("Flags: ", 1)[1].split()
    assert 'Description: "{cm:launch}"' in script
    assert "LicenseFile=" in script
