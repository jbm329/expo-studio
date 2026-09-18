from __future__ import annotations

from types import SimpleNamespace

import pytest
from PyQt6.QtWidgets import QTabWidget, QWidget

from expo_jbm329.workbench.controllers.editor_panel_controller import (
    EditorPanelController,
)
from expo_jbm329.workbench.controllers.editor_tab_manager import EditorTabManager


class DummyDialogService:
    def __init__(self) -> None:
        self.prompts = []

    def prompt_text(self, *args, **kwargs):
        self.prompts.append((args, kwargs))
        return "Renamed", True

    def prompt_yes_no(self, *args, **kwargs):
        return True


class DummyIconService:
    def get(self, name):
        return SimpleNamespace()


class DummyThemeService:
    def __init__(self) -> None:
        self.theme_changed = SimpleNamespace(connect=lambda cb: None)

    def resolve_theme(self):
        return SimpleNamespace()


class DummyEditorWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.tab_id = None
        self.editor_controller = SimpleNamespace(
            suppress_change=lambda: None,
            set_on_change=lambda cb: None,
            resume_change=lambda: None,
        )
        self._sql = ""
        self._highlighter = None
        self._autocomplete_engine = SimpleNamespace(set_schema=lambda schema: None)
        self._autocomplete = SimpleNamespace(set_dialect=lambda dialect: None)
        self._editor = SimpleNamespace()

    def apply_tab_state(self, tab):
        self.tab_state = tab

    def get_document(self):
        return SimpleNamespace()

    def set_highlighter(self, highlighter):
        self._highlighter = highlighter

    def get_editor(self):
        return self._editor

    def set_autocomplete_engine(self, engine):
        self._autocomplete_engine = engine

    def set_autocomplete(self, autocomplete):
        self._autocomplete = autocomplete

    def get_sql_text(self):
        return self._sql

    def set_sql_text(self, text):
        self._sql = text

    def focus_editor(self):
        pass

    def get_autocomplete_engine(self):
        return self._autocomplete_engine

    def get_autocomplete(self):
        return self._autocomplete


@pytest.fixture
def controller(monkeypatch):
    monkeypatch.setattr(
        "expo_jbm329.workbench.controllers.editor_panel_controller.EditorWidget",
        DummyEditorWidget,
    )
    monkeypatch.setattr(
        "expo_jbm329.workbench.controllers.editor_panel_controller.SqlHighlighter",
        lambda doc, theme: SimpleNamespace(rehighlight=lambda: None, set_theme=lambda theme: None),
    )
    monkeypatch.setattr(
        "expo_jbm329.workbench.controllers.editor_panel_controller.SqlAutocompleteController",
        lambda **kwargs: SimpleNamespace(install=lambda: None),
    )
    monkeypatch.setattr(
        "expo_jbm329.workbench.controllers.editor_panel_controller.SqlLintController",
        lambda **kwargs: SimpleNamespace(install=lambda: None, schedule_lint=lambda: None, dispose=lambda: None, deleteLater=lambda: None, clear_diagnostics=lambda: None),
    )
    monkeypatch.setattr(
        "expo_jbm329.workbench.controllers.editor_panel_controller.EditorTabContextMenu",
        lambda **kwargs: SimpleNamespace(),
    )
    tab_manager = EditorTabManager()
    tab_widget = QTabWidget()
    ctrl = EditorPanelController(
        tab_manager=tab_manager,
        tab_widget=tab_widget,
        icon_service=DummyIconService(),
        highlighter_theme_service=DummyThemeService(),
        get_cache_for=lambda conn: {},
        build_schema_dict=lambda schema: schema,
        dialogs=DummyDialogService(),
        parent=QWidget(),
    )
    return ctrl, tab_manager, tab_widget


def test_create_tab_and_get_active_sql(controller):
    ctrl, tab_manager, _ = controller
    tab = ctrl.create_tab(base_title="MyQuery")

    assert tab_manager.get_active_tab() == tab
    assert ctrl.get_active_tab() == tab


def test_bind_and_update_tab(controller):
    ctrl, tab_manager, _ = controller
    tab = ctrl.create_tab(base_title="MyQuery")

    ctrl.rename_tab(tab.tab_id, "Renamed")
    assert tab_manager.get_tab(tab.tab_id).base_title == "Renamed"


def test_active_tab_text_helpers(controller):
    ctrl, _, _ = controller
    ctrl.create_tab(base_title="MyQuery")
    widget = ctrl.get_active_editor_widget()
    widget.set_sql_text("SELECT 1")

    assert ctrl.get_active_tab_text() == "SELECT 1"
    ctrl.set_active_tab_text("SELECT 2")
    assert widget.get_sql_text() == "SELECT 2"

