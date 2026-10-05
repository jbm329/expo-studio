from __future__ import annotations

import os
import runpy
from pathlib import Path

from expo_jbm329.app import bootstrap


def test_restore_clean_environment_restores_ld_library_path_when_frozen_linux(monkeypatch) -> None:
    monkeypatch.setattr(bootstrap.sys, "frozen", True, raising=False)
    monkeypatch.setattr(bootstrap.sys, "platform", "linux")
    monkeypatch.setenv("LD_LIBRARY_PATH", "/tmp/_internal")
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/usr/local/lib:/usr/lib")

    bootstrap.restore_clean_environment()

    assert os.environ["LD_LIBRARY_PATH"] == "/usr/local/lib:/usr/lib"


def test_restore_clean_environment_unsets_qt_and_ld_variables_when_orig_not_set(monkeypatch) -> None:
    monkeypatch.setattr(bootstrap.sys, "frozen", True, raising=False)
    monkeypatch.setattr(bootstrap.sys, "platform", "linux")
    monkeypatch.setenv("LD_LIBRARY_PATH", "/tmp/_internal")
    monkeypatch.delenv("LD_LIBRARY_PATH_ORIG", raising=False)
    monkeypatch.delenv("LD_LIBRARY_PATHORIG", raising=False)

    monkeypatch.setenv("QT_PLUGIN_PATH", "/tmp/_internal/PyQt6/Qt6/plugins")
    monkeypatch.setenv("QT_QPA_PLATFORM_PLUGIN_PATH", "/tmp/_internal/PyQt6/Qt6/plugins/platforms")
    monkeypatch.setenv("QML_IMPORT_PATH", "/tmp/_internal/PyQt6/Qt6/qml")
    monkeypatch.setenv("QML2_IMPORT_PATH", "/tmp/_internal/PyQt6/Qt6/qml")
    monkeypatch.delenv("QT_PLUGIN_PATH_ORIG", raising=False)
    monkeypatch.delenv("QT_QPA_PLATFORM_PLUGIN_PATH_ORIG", raising=False)
    monkeypatch.delenv("QML_IMPORT_PATH_ORIG", raising=False)
    monkeypatch.delenv("QML2_IMPORT_PATH_ORIG", raising=False)

    bootstrap.restore_clean_environment()

    assert "LD_LIBRARY_PATH" not in os.environ
    assert "QT_PLUGIN_PATH" not in os.environ
    assert "QT_QPA_PLATFORM_PLUGIN_PATH" not in os.environ
    assert "QML_IMPORT_PATH" not in os.environ
    assert "QML2_IMPORT_PATH" not in os.environ


def test_restore_clean_environment_restores_qt_variables_from_orig(monkeypatch) -> None:
    monkeypatch.setattr(bootstrap.sys, "frozen", True, raising=False)
    monkeypatch.setattr(bootstrap.sys, "platform", "linux")
    monkeypatch.setenv("LD_LIBRARY_PATH", "/tmp/_internal")
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/usr/lib64")
    monkeypatch.setenv("QT_PLUGIN_PATH", "/tmp/_internal/PyQt6/Qt6/plugins")
    monkeypatch.setenv("QT_PLUGIN_PATH_ORIG", "/usr/lib64/qt6/plugins")
    monkeypatch.setenv("QML2_IMPORT_PATH", "/tmp/_internal/PyQt6/Qt6/qml")
    monkeypatch.setenv("QML2_IMPORT_PATH_ORIG", "/usr/lib64/qt6/qml")

    bootstrap.restore_clean_environment()

    assert os.environ["LD_LIBRARY_PATH"] == "/usr/lib64"
    assert os.environ["QT_PLUGIN_PATH"] == "/usr/lib64/qt6/plugins"
    assert os.environ["QML2_IMPORT_PATH"] == "/usr/lib64/qt6/qml"


def test_restore_clean_environment_restores_ld_library_pathorig_fallback(monkeypatch) -> None:
    monkeypatch.setattr(bootstrap.sys, "frozen", True, raising=False)
    monkeypatch.setattr(bootstrap.sys, "platform", "linux")
    monkeypatch.setenv("LD_LIBRARY_PATH", "/tmp/_internal")
    monkeypatch.delenv("LD_LIBRARY_PATH_ORIG", raising=False)
    monkeypatch.setenv("LD_LIBRARY_PATHORIG", "/custom/lib")

    bootstrap.restore_clean_environment()

    assert os.environ["LD_LIBRARY_PATH"] == "/custom/lib"


def test_restore_clean_environment_noop_when_not_frozen(monkeypatch) -> None:
    monkeypatch.delattr(bootstrap.sys, "frozen", raising=False)
    monkeypatch.setattr(bootstrap.sys, "platform", "linux")
    monkeypatch.setenv("LD_LIBRARY_PATH", "/custom/dev/path")
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/should/not/be/used")
    monkeypatch.setenv("QT_PLUGIN_PATH", "/custom/dev/plugins")
    monkeypatch.setenv("QT_PLUGIN_PATH_ORIG", "/should/not/be/used/plugins")

    bootstrap.restore_clean_environment()

    assert os.environ["LD_LIBRARY_PATH"] == "/custom/dev/path"
    assert os.environ["QT_PLUGIN_PATH"] == "/custom/dev/plugins"


def test_restore_clean_environment_noop_on_windows(monkeypatch) -> None:
    monkeypatch.setattr(bootstrap.sys, "frozen", True, raising=False)
    monkeypatch.setattr(bootstrap.sys, "platform", "win32")
    monkeypatch.setenv("LD_LIBRARY_PATH", "/custom/dev/path")
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/should/not/be/used")
    monkeypatch.setenv("QT_PLUGIN_PATH", "/custom/dev/plugins")
    monkeypatch.setenv("QT_PLUGIN_PATH_ORIG", "/should/not/be/used/plugins")

    bootstrap.restore_clean_environment()

    assert os.environ["LD_LIBRARY_PATH"] == "/custom/dev/path"
    assert os.environ["QT_PLUGIN_PATH"] == "/custom/dev/plugins"


def test_rthook_restore_environ_script(monkeypatch) -> None:
    hook_path = Path(__file__).parents[1] / "hooks" / "rthook_restore_environ.py"
    assert hook_path.is_file()

    monkeypatch.setattr("sys.frozen", True, raising=False)
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setenv("LD_LIBRARY_PATH", "/tmp/_internal")
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/original/lib")
    monkeypatch.setenv("QT_PLUGIN_PATH", "/tmp/_internal/PyQt6/Qt6/plugins")
    monkeypatch.delenv("QT_PLUGIN_PATH_ORIG", raising=False)

    runpy.run_path(str(hook_path))

    assert os.environ["LD_LIBRARY_PATH"] == "/original/lib"
    assert "QT_PLUGIN_PATH" not in os.environ
