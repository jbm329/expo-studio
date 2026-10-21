from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
import pytest
from PyQt6.QtCore import QCoreApplication, QTranslator
from PyQt6.QtWidgets import QWidget

from expo_jbm329.build.build_utils import locales_dir
from expo_jbm329.services.job_result import JobResult
from expo_jbm329.services.rest.models import RestRequestConfig
from expo_jbm329.workbench.controllers import rest_controller
from expo_jbm329.workbench.controllers.rest_controller import RestController


class DummyJobMgr:
    def get_job_id(self, job):
        return "job-1"


class DummyAsyncOps:
    def __init__(self):
        self.job_mgr = DummyJobMgr()
        self.calls = []
        self.job = object()

    def run_target_overlay_operation(self, **kwargs):
        self.calls.append(kwargs)
        self.last_kwargs = kwargs
        return self.job


class DummyResults:
    def __init__(self):
        self.pending = []
        self.fulfill_calls = []
        self.remove_calls = []
        self.bind_calls = []

    def create_pending_tab(self, **kwargs):
        handle = type("H", (), {"tab_id": "pending-1", "view": QWidget()})()
        self.pending.append(kwargs)
        return handle

    def fulfill_pending_tab(self, tab_id, df):
        self.fulfill_calls.append((tab_id, df))

    def remove_pending_tab(self, tab_id):
        self.remove_calls.append(tab_id)

    def bind_job_to_tab(self, tab_id, job_id):
        self.bind_calls.append((tab_id, job_id))


def make_controller():
    return RestController(
        parent_widget=QWidget(),
        async_ops=DummyAsyncOps(),
        results=DummyResults(),
        display_dataframe=MagicMock(),
        set_status=MagicMock(),
        dialogs=MagicMock(),
    )


def test_load_from_api_wires_async_job():
    ctrl = make_controller()
    cfg = RestRequestConfig(name="Example", url="https://example.com", json_body=None)

    ctrl.load_from_api(config=cfg)

    assert ctrl._async_ops.calls
    assert ctrl._results.pending
    assert ctrl._results.bind_calls == [("pending-1", "job-1")]


def test_on_rest_loaded_successful_payload():
    ctrl = make_controller()
    payload = JobResult(ok=True, cancelled=False, elapsed=1.5, data=pd.DataFrame({"a": [1]}))

    ctrl._on_rest_loaded(payload, "Example", pending_tab_id="pending-1")

    assert ctrl._results.fulfill_calls


@pytest.mark.parametrize(
    ("language", "template"),
    [
        ("en", "A connection named '{name}' already exists."),
        ("sv", "Det finns redan en anslutning med namnet '{name}'."),
    ],
)
def test_duplicate_preset_name_uses_translated_named_formatting(monkeypatch, language, template):
    ctrl = make_controller()
    name = "Copy {literal} %1"
    ctrl._dialogs.prompt_text.return_value = (name, True)
    monkeypatch.setattr(rest_controller.rest_registry, "get", lambda _name: object())
    monkeypatch.setattr(rest_controller.rest_registry, "exists", lambda candidate: candidate == name)
    translator = QTranslator()
    assert translator.load(str(locales_dir() / f"app_{language}.qm"))
    assert QCoreApplication.installTranslator(translator)
    try:
        assert ctrl.copy_preset("Example") is None
        assert ctrl._dialogs.warn.call_args.kwargs["text"] == template.format(name=name)
    finally:
        QCoreApplication.removeTranslator(translator)
