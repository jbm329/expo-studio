from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from expo_jbm329.workbench.controllers.file_panel_controller import FilePanelController


class DummySignal:
    def __init__(self):
        self.callbacks = []

    def connect(self, cb, *args, **kwargs):
        self.callbacks.append(cb)


class DummyIndex:
    def __init__(self, path: str | None, valid: bool = True):
        self._path = path
        self._valid = valid

    def isValid(self):
        return self._valid


class DummyTree:
    def __init__(self, index: DummyIndex | None = None):
        self.doubleClicked = DummySignal()
        self.customContextMenuRequested = DummySignal()
        self._index = index or DummyIndex(None, False)
        self._root_index = None
        self._policy = None
        self._viewport = SimpleNamespace(update=lambda: None, mapToGlobal=lambda p: p)

    def setContextMenuPolicy(self, policy):
        self._policy = policy

    def indexAt(self, pos):
        return self._index

    def viewport(self):
        return self._viewport

    def setRootIndex(self, index):
        self._root_index = index


class DummyModel:
    def __init__(self, path: str):
        self._path = path
        self.remove_calls = 0
        self.remove_result = True
        self.icon_provider = None

    def filePath(self, index):
        return self._path

    def index(self, path: str):
        return SimpleNamespace(path=path)

    def remove(self, index):
        self.remove_calls += 1
        return self.remove_result

    def setIconProvider(self, provider):
        self.icon_provider = provider


class DummyDialogs:
    def __init__(self):
        self.info = MagicMock()
        self.critical = MagicMock()
        self.warn = MagicMock()
        self.prompt_text = MagicMock(return_value=("new.csv", True))
        self.confirm_delete = MagicMock(return_value=True)


def make_ctrl(path: str, dialogs: DummyDialogs | None = None):
    files_tree = DummyTree(DummyIndex(path, True))
    files_model = DummyModel(path)
    open_any = MagicMock()
    close_result_tabs = MagicMock()
    rename_file = MagicMock(return_value=(True, None))
    status_messages: list[tuple[str, int | None]] = []
    file_icon_provider = object()
    dialogs = dialogs or DummyDialogs()

    ctrl = FilePanelController(
        parent_widget=object(),
        files_tree=files_tree,
        files_model=files_model,
        open_any=open_any,
        close_result_tabs=close_result_tabs,
        rename_file=rename_file,
        set_status=lambda msg, timeout: status_messages.append((msg, timeout)),
        file_icon_provider=file_icon_provider,
        dialogs=dialogs,
    )
    return ctrl, files_tree, files_model, open_any, close_result_tabs, rename_file, dialogs, status_messages


def test_double_click_data_triggers_open_any(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text("x", encoding="utf-8")
    ctrl, _, _, open_any, *_ = make_ctrl(str(path))

    ctrl._on_file_double_clicked(SimpleNamespace())

    open_any.assert_called_once_with(Path(str(path)))


def test_double_click_directory_is_ignored(tmp_path):
    folder = tmp_path / "folder"
    folder.mkdir()
    ctrl, tree, model, open_any, *_ = make_ctrl(str(folder))

    ctrl._on_file_double_clicked(SimpleNamespace())

    assert not open_any.called


def test_rename_missing_file_shows_info(tmp_path):
    path = tmp_path / "missing.csv"
    ctrl, _, _, _, _, _, dialogs, status_messages = make_ctrl(str(path))

    ctrl._rename(SimpleNamespace())

    assert dialogs.info.called
    assert status_messages


def test_rename_success(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text("x", encoding="utf-8")
    ctrl, _, _, _, _, rename_file, dialogs, _ = make_ctrl(str(path))

    ctrl._rename(SimpleNamespace())

    rename_file.assert_called_once()
    dialogs.critical.assert_not_called()


def test_rename_failure_shows_critical(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text("x", encoding="utf-8")
    ctrl, _, _, _, _, rename_file, dialogs, status_messages = make_ctrl(str(path))
    rename_file.return_value = (False, "Nope")

    ctrl._rename(SimpleNamespace())

    dialogs.critical.assert_called_once()
    assert status_messages


def test_delete_missing_file_shows_info(tmp_path):
    path = tmp_path / "gone.csv"
    ctrl, _, _, _, close_result_tabs, _, dialogs, status_messages = make_ctrl(str(path))

    ctrl._delete_file(SimpleNamespace())

    assert dialogs.info.called
    assert not close_result_tabs.called
    assert status_messages


def test_delete_confirm_no_does_nothing(tmp_path):
    path = tmp_path / "keep.csv"
    path.write_text("x", encoding="utf-8")
    dialogs = DummyDialogs()
    dialogs.confirm_delete.return_value = False
    ctrl, _, model, _, close_result_tabs, _, dialogs, _ = make_ctrl(str(path), dialogs=dialogs)

    ctrl._delete_file(SimpleNamespace())

    assert model.remove_calls == 0
    assert not close_result_tabs.called


def test_delete_confirm_yes_removes_and_closes_tabs(tmp_path):
    path = tmp_path / "del.csv"
    path.write_text("x", encoding="utf-8")
    ctrl, _, model, _, close_result_tabs, _, dialogs, status_messages = make_ctrl(str(path))

    ctrl._delete_file(SimpleNamespace())

    assert model.remove_calls == 1
    close_result_tabs.assert_called_once_with("del.csv")
    assert status_messages


def test_update_icons_sets_icon_provider():
    ctrl, _, model, *_ = make_ctrl("C:\\tmp\\data.csv")

    ctrl.update_icons()

    assert model.icon_provider is ctrl._file_icon_provider


def test_reload_settings_updates_root_index(monkeypatch):
    ctrl, tree, model, *_ = make_ctrl("C:\\tmp\\data.csv")
    new_root = Path("C:/new_root")
    monkeypatch.setattr("expo_jbm329.utils.path_manager.get_documents_dir", lambda settings: new_root)

    ctrl.reload_settings({"some": "settings"})

    assert tree._root_index.path == str(new_root)
