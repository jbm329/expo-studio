# tests/test_file_panel_controller.py
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from expo_jbm329.workbench.controllers.file_panel_controller import FilePanelController
from tests.stubs import (
    DummyResults,
    DummyFileJobs,
    DummyDataIO,
    DummyStatusLogger,
    make_dialog_services,
)

class DummyTree:
    """Stub for QTreeView."""
    def __init__(self):
        self.doubleClicked = MagicMock()
        self.customContextMenuRequested = MagicMock()
        self._policy = None

    def setContextMenuPolicy(self, policy):
        self._policy = policy

    def indexAt(self, pos):
        return SimpleNamespace(isValid=lambda: False)

    def viewport(self):
        return SimpleNamespace(update=lambda: None, mapToGlobal=lambda p: p)
    
    def setRootIndex(self, index):
        pass

class DummyModel:
    """Stub for QFileSystemModel."""
    def __init__(self, path: str = ""):
        self._path = path
        self.remove_calls = 0
        self.remove_result = True

    def filePath(self, index):
        return self._path

    def set_file(self, path: str):
        self._path = path

    def remove(self, index):
        self.remove_calls += 1
        return self.remove_result
    
    def setIconProvider(self, provider):
        pass

    def index(self, path: str):
        return SimpleNamespace(isValid=lambda: True)

def make_ctrl(
    *,
    model_path: str,
    dialogs=None,
):
    parent = object()
    files_tree = DummyTree()
    files_model = DummyModel(model_path)
    results = DummyResults()
    status_logger = DummyStatusLogger()
    file_jobs = DummyFileJobs()
    data_io = DummyDataIO()
    fmt_time = lambda s: f"{s:.1f}s"
    fmt_int = lambda i: f"{i:,}"
    fmt_path = lambda p: str(p)
    file_icon_provider = object()
    
    if dialogs is None:
        dialogs, _ = make_dialog_services()

    ctrl = FilePanelController(
        parent_widget=parent,
        files_tree=files_tree,
        files_model=files_model,
        results=results,
        set_status=status_logger.set_status,
        file_jobs=file_jobs,
        data_io=data_io,
        fmt_time=fmt_time,
        fmt_int=fmt_int,
        fmt_path=fmt_path,
        file_icon_provider=file_icon_provider,
        dialogs=dialogs,
    )
    return ctrl, files_model, results, file_jobs, status_logger, dialogs

# --------------------------------
# Double-click: data/sql/html/unknown
# --------------------------------

def test_double_click_data_triggers_open_data_file(qt_app):
    ctrl, model, results, file_jobs, status, dlg = make_ctrl(model_path="C:/tmp/data.csv")
    ctrl._on_file_double_clicked(SimpleNamespace())

    assert "C:/tmp/data.csv" in file_jobs.open_data_calls

def test_double_click_sql_opens_sql_file(qt_app):
    ctrl, model, results, file_jobs, status, dlg = make_ctrl(model_path="C:/tmp/query.sql")
    ctrl._on_file_double_clicked(SimpleNamespace())

    assert Path("C:/tmp/query.sql") in file_jobs.open_sql_calls

def test_double_click_html_opens_html_file(qt_app):
    ctrl, model, results, file_jobs, status, dlg = make_ctrl(model_path="C:/tmp/page.html")
    ctrl._on_file_double_clicked(SimpleNamespace())

    assert Path("C:/tmp/page.html") in file_jobs.open_html_calls

def test_double_click_unknown_shows_info(qt_app):
    ctrl, model, results, file_jobs, status, dlg = make_ctrl(model_path="C:/tmp/file.unknown")
    dlg.info = MagicMock()
    
    ctrl._on_file_double_clicked(SimpleNamespace())

    dlg.info.assert_called_once()
    assert "Okänt format" in dlg.info.call_args[1]["title"]

# --------------------------------
# Rename file
# --------------------------------

def test_rename_file_missing_file_shows_info(qt_app, tmp_path):
    p = tmp_path / "nope.csv"
    ctrl, model, results, file_jobs, status, dlg = make_ctrl(model_path=str(p))
    
    ctrl._rename_file(SimpleNamespace())
    assert any("Filen finns inte längre." in msg for msg, _ in status.messages)

def test_rename_file_success(qt_app, tmp_path, monkeypatch):
    p = tmp_path / "data.csv"
    p.write_text("x")

    ctrl, model, results, file_jobs, status, dlg = make_ctrl(model_path=str(p))
    file_jobs.rename_return = (True, None)
    
    # Use dlg.prompt_text to mock the user input
    dlg.prompt_text = MagicMock(return_value=("new.csv", True))

    ctrl._rename_file(SimpleNamespace())
    assert (Path(p), "new.csv") in file_jobs.rename_calls

def test_rename_file_failure_shows_critical(qt_app, tmp_path, monkeypatch):
    p = tmp_path / "data.csv"
    p.write_text("x")

    ctrl, model, results, file_jobs, status, dlg = make_ctrl(model_path=str(p))
    file_jobs.rename_return = (False, "Nope")
    
    dlg.prompt_text = MagicMock(return_value=("new.csv", True))
    dlg.critical = MagicMock()

    ctrl._rename_file(SimpleNamespace())
    dlg.critical.assert_called_once()
    assert "Fel vid byte av filnamn" in dlg.critical.call_args[1]["title"]

# --------------------------------
# Delete file
# --------------------------------

def test_delete_file_missing_shows_info(qt_app, tmp_path):
    p = tmp_path / "gone.csv"
    ctrl, model, results, file_jobs, status, dlg = make_ctrl(model_path=str(p))

    ctrl._delete_file(SimpleNamespace())
    assert any("Filen finns inte längre." in msg for msg, _ in status.messages)

def test_delete_file_confirm_no_does_nothing(qt_app, tmp_path):
    p = tmp_path / "keep.csv"
    p.write_text("x")
    
    from gui.dialogs.service.dialog_service import NullDialogService
    dlg = NullDialogService(default_confirm_delete=False)
    
    ctrl, model, results, file_jobs, status, dlg = make_ctrl(model_path=str(p), dialogs=dlg)

    ctrl._delete_file(SimpleNamespace())

    assert results.closed_titles == []
    assert model.remove_calls == 0

def test_delete_file_confirm_yes_remove_true(qt_app, tmp_path):
    p = tmp_path / "del.csv"
    p.write_text("x")
    
    from gui.dialogs.service.dialog_service import NullDialogService
    dlg = NullDialogService(default_confirm_delete=True)
    
    ctrl, model, results, file_jobs, status, dlg = make_ctrl(model_path=str(p), dialogs=dlg)

    ctrl._delete_file(SimpleNamespace())

    assert model.remove_calls == 1
    assert any("Fil raderad:" in msg for msg, _ in status.messages)
    assert "del.csv" in results.closed_titles

def test_delete_file_remove_false_unlink_true(qt_app, tmp_path, monkeypatch):
    p = tmp_path / "del2.csv"
    p.write_text("x")
    
    from gui.dialogs.service.dialog_service import NullDialogService
    dlg = NullDialogService(default_confirm_delete=True)
    
    ctrl, model, results, file_jobs, status, dlg = make_ctrl(model_path=str(p), dialogs=dlg)
    model.remove_result = False

    ctrl._delete_file(SimpleNamespace())

    assert model.remove_calls == 1
    assert not p.exists()
    assert any("Fil raderad:" in msg for msg, _ in status.messages)

def test_delete_file_remove_false_unlink_permission_error(qt_app, tmp_path, monkeypatch):
    p = tmp_path / "locked.csv"
    p.write_text("x")
    
    from gui.dialogs.service.dialog_service import NullDialogService
    dlg = NullDialogService(default_confirm_delete=True)
    dlg.warn = MagicMock()
    
    ctrl, model, results, file_jobs, status, dlg = make_ctrl(model_path=str(p), dialogs=dlg)
    model.remove_result = False

    def fake_unlink(self):
        if self == p:
            raise PermissionError("locked")
    
    monkeypatch.setattr(Path, "unlink", fake_unlink)

    ctrl._delete_file(SimpleNamespace())

    dlg.warn.assert_called_once()
    assert "Ta bort fil" in dlg.warn.call_args[1]["title"]

def test_update_icons(qt_app):
    ctrl, model, results, file_jobs, status, dlg = make_ctrl(model_path="C:/tmp/data.csv")
    
    # Mock setIconProvider to verify it's called
    model.setIconProvider = MagicMock()
    
    ctrl.update_icons()
    
    model.setIconProvider.assert_called_once_with(ctrl._file_icon_provider)

def test_reload_settings_updates_root_index(qt_app, monkeypatch):
    ctrl, model, results, file_jobs, status, dlg = make_ctrl(model_path="C:/tmp/data.csv")
    
    monkeypatch.setattr("expo_jbm329.utils.path_manager.get_documents_dir", lambda s: Path("C:/new_root"))
    
    # Mock setRootIndex to verify it's called
    from unittest.mock import MagicMock
    ctrl._files_tree.setRootIndex = MagicMock()
    
    ctrl.reload_settings({"some": "settings"})
    
    ctrl._files_tree.setRootIndex.assert_called_once()
