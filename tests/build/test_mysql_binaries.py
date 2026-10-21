from __future__ import annotations

from pathlib import Path

import pytest

from expo_jbm329.build import mysql_binaries
from expo_jbm329.build.mysql_binaries import OPENSSL_DLLS, collect_mysql_connector_openssl_binaries


class _FakeDistribution:
    def __init__(self, site_packages: Path, files: tuple[Path, ...]) -> None:
        self._site_packages = site_packages
        self.files = files

    def locate_file(self, file: str | Path) -> Path:
        return self._site_packages / file


def test_collects_connector_owned_root_openssl_dlls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site_packages = tmp_path / "site-packages"
    root_files = tuple(Path(name) for name in OPENSSL_DLLS)
    vendor_files = tuple(Path("mysql") / "vendor" / name for name in OPENSSL_DLLS)
    for file in (*root_files, *vendor_files):
        path = site_packages / file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"dll")

    connector = _FakeDistribution(site_packages, root_files + vendor_files)
    monkeypatch.setattr(mysql_binaries, "distribution", lambda _name: connector)

    binaries = collect_mysql_connector_openssl_binaries()

    assert binaries == [(str(site_packages / name), ".") for name in OPENSSL_DLLS]


def test_missing_root_openssl_dll_fails_with_actionable_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site_packages = tmp_path / "site-packages"
    crypto = site_packages / OPENSSL_DLLS[0]
    crypto.parent.mkdir(parents=True)
    crypto.write_bytes(b"dll")
    vendor_ssl = Path("mysql") / "vendor" / OPENSSL_DLLS[1]
    (site_packages / vendor_ssl).parent.mkdir(parents=True)
    (site_packages / vendor_ssl).write_bytes(b"dll")
    connector = _FakeDistribution(site_packages, (Path(OPENSSL_DLLS[0]), vendor_ssl))
    monkeypatch.setattr(mysql_binaries, "distribution", lambda _name: connector)

    with pytest.raises(FileNotFoundError, match=OPENSSL_DLLS[1]):
        collect_mysql_connector_openssl_binaries()
