from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from PyQt6.QtWidgets import QWidget

from expo_jbm329.utils.dialog_state import DialogState
from expo_jbm329.workbench.controllers.document_controller import DocumentController
from expo_jbm329.workbench.controllers.editor_tab_manager import EditorTab

if TYPE_CHECKING:
    from pathlib import Path


class DummyDialogService:
    def __init__(self) -> None:
        self.info_calls = []
        self.critical_calls = []

    def info(self, parent, title, text):
        self.info_calls.append((parent, title, text))

    def critical(self, parent, title, text):
        self.critical_calls.append((parent, title, text))


class DummyFileDialogs:
    def __init__(self) -> None:
        self.open_req = None
        self.save_req = None
        self.open_result = ("", "")
        self.save_result = ("", "")

    def get_open_filename(self, parent, req):
        self.open_req = req
        return self.open_result

    def get_save_filename(self, parent, req):
        self.save_req = req
        return self.save_result


def make_controller(tmp_path: Path):
    dialogs = DummyDialogService()
    file_dialogs = DummyFileDialogs()
    status = MagicMock()
    get_active_tab = MagicMock(return_value=None)
    clear_dirty = MagicMock()
    set_file_path = MagicMock()
    update_tab_ui = MagicMock()
    get_editor_text = MagicMock(return_value="SELECT 1")
    create_tab = MagicMock(
        return_value=EditorTab(tab_id="tab-1", base_title="query.sql")
    )
    insert_sql_into_tab = MagicMock()
    open_data_file = MagicMock()
    dialog_state = DialogState()
    ctrl = DocumentController(
        parent=QWidget(),
        file_dialogs=file_dialogs,
        dialogs=dialogs,
        set_status=status,
        get_active_tab=get_active_tab,
        clear_dirty=clear_dirty,
        set_file_path=set_file_path,
        update_tab_ui=update_tab_ui,
        get_editor_text=get_editor_text,
        create_tab=create_tab,
        insert_sql_into_tab=insert_sql_into_tab,
        open_data_file=open_data_file,
        dialog_state=dialog_state,
    )
    ctrl.reload_settings({"documents_dir": str(tmp_path)})
    return ctrl, {
        "dialogs": dialogs,
        "file_dialogs": file_dialogs,
        "status": status,
        "get_active_tab": get_active_tab,
        "clear_dirty": clear_dirty,
        "set_file_path": set_file_path,
        "update_tab_ui": update_tab_ui,
        "get_editor_text": get_editor_text,
        "create_tab": create_tab,
        "insert_sql_into_tab": insert_sql_into_tab,
        "open_data_file": open_data_file,
        "dialog_state": dialog_state,
    }


def test_open_any_dispatches_by_file_type(tmp_path: Path):
    ctrl, mocks = make_controller(tmp_path)
    sql_path = tmp_path / "query.sql"
    sql_path.write_text("SELECT 1", encoding="utf-8")

    ctrl.open_any(sql_path)

    mocks["create_tab"].assert_called_once()
    mocks["insert_sql_into_tab"].assert_called_once()
    mocks["set_file_path"].assert_called_once()
    mocks["clear_dirty"].assert_called_once()
    mocks["update_tab_ui"].assert_called_once()


def test_open_any_unsupported_shows_info(tmp_path: Path):
    ctrl, mocks = make_controller(tmp_path)

    ctrl.open_any(tmp_path / "file.xyz")

    assert mocks["dialogs"].info_calls
    mocks["status"].assert_called_once()


def test_save_sql_as_writes_file_and_updates_tab(tmp_path: Path):
    ctrl, mocks = make_controller(tmp_path)
    tab = EditorTab(tab_id="tab-1", base_title="query.sql")
    mocks["get_active_tab"].return_value = tab
    save_path = tmp_path / "saved.sql"
    mocks["file_dialogs"].save_result = (str(save_path), "")

    ctrl.save_sql_as()

    assert save_path.read_text(encoding="utf-8") == "SELECT 1"
    mocks["set_file_path"].assert_called_once_with("tab-1", str(save_path))
    mocks["clear_dirty"].assert_called_once_with("tab-1")
    mocks["update_tab_ui"].assert_called_once_with(tab)


def test_open_html_file_returns_browser_result(tmp_path: Path, monkeypatch):
    ctrl, mocks = make_controller(tmp_path)
    html_path = tmp_path / "page.html"
    html_path.write_text("<html></html>", encoding="utf-8")
    monkeypatch.setattr(
        "webbrowser.open",
        lambda uri: True,
    )

    assert ctrl.open_html_file(path=html_path) is True
    assert mocks["status"].called

