from __future__ import annotations

import os
import subprocess
import sys
from types import SimpleNamespace
from typing import TYPE_CHECKING

from expo_jbm329.build import build

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_onedir_environment_excludes_runner_mysql_server_path(monkeypatch: pytest.MonkeyPatch) -> None:
    mysql_path = r"C:\Program Files\MySQL\MySQL Server 8.0\bin"
    retained_paths = [r"C:\Python313", r"C:\Windows\System32"]
    monkeypatch.setattr(build.os, "pathsep", ";")
    monkeypatch.setenv("PATH", ";".join([mysql_path, *retained_paths]))
    monkeypatch.setenv("EXPO_ONEFILE", "1")

    environment = build._onedir_environment()

    assert environment["PATH"].split(";") == retained_paths
    assert "EXPO_ONEFILE" not in environment


def test_mysql_connector_smoke_check_requires_bundle_openssl_files(tmp_path: Path) -> None:
    onedir = tmp_path / "dist" / "expo"
    internal = onedir / "_internal"
    internal.mkdir(parents=True)

    assert not build._verify_mysql_connector_bundle(onedir)


def test_mysql_connector_smoke_check_loads_extension_from_bundle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    onedir = tmp_path / "dist" / "expo"
    internal = onedir / "_internal"
    internal.mkdir(parents=True)
    for name in ("libcrypto-3-x64.dll", "libssl-3-x64.dll"):
        (internal / name).write_bytes(b"dll")

    calls: list[tuple[list[str], dict[str, object]]] = []

    def run(command: list[str], **kwargs: object) -> SimpleNamespace:
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(build, "_onedir_environment", lambda: {"PATH": os.environ.get("PATH", "")})
    monkeypatch.setattr(build.subprocess, "run", run)

    assert build._verify_mysql_connector_bundle(onedir)
    command, kwargs = calls[0]
    assert command[0] == sys.executable
    assert str(internal) in command
    assert kwargs["cwd"] == internal
    assert kwargs["check"] is False
    assert "extension.is_relative_to(bundle)" in command[2]


def test_mysql_connector_smoke_check_reports_load_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    onedir = tmp_path / "dist" / "expo"
    internal = onedir / "_internal"
    internal.mkdir(parents=True)
    for name in ("libcrypto-3-x64.dll", "libssl-3-x64.dll"):
        (internal / name).write_bytes(b"dll")

    monkeypatch.setattr(build, "_onedir_environment", dict)
    monkeypatch.setattr(
        build.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 1, stdout="", stderr="DLL load failed"),
    )

    assert not build._verify_mysql_connector_bundle(onedir)
    assert "DLL load failed" in capsys.readouterr().err
