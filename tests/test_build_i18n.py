import subprocess
from unittest.mock import MagicMock

import pytest

from expo_jbm329.build import build_i18n


@pytest.fixture
def check_call(monkeypatch, tmp_path):
    mock = MagicMock()
    monkeypatch.setattr(build_i18n.subprocess, "check_call", mock)
    monkeypatch.setattr(build_i18n, "TS_FILES", [tmp_path / "app_en.ts", tmp_path / "app_sv.ts"])
    monkeypatch.setattr(build_i18n, "ensure_locales_dir", lambda: None)
    return mock


def test_main_does_not_remove_obsolete(check_call):
    build_i18n.main()

    assert check_call.call_count == 2
    for call in check_call.call_args_list:
        assert "--no-obsolete" not in call.args[0]


def test_main_clean_removes_obsolete(check_call):
    build_i18n.main_clean()

    assert check_call.call_count == 2
    for call in check_call.call_args_list:
        assert "--no-obsolete" in call.args[0]


def test_main_clean_exits_on_failure(check_call):
    check_call.side_effect = subprocess.CalledProcessError(1, "pylupdate6")

    with pytest.raises(SystemExit) as exc_info:
        build_i18n.main_clean()

    assert exc_info.value.code == 1
