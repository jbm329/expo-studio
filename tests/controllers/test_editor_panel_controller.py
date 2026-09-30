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


class DummyHighlighter:
    def __init__(self, doc, *, theme, dialect=None):
        self.dialect = dialect
        self.schema_names = None

    def rehighlight(self):
        pass

    def set_theme(self, theme):
        pass

    def set_dialect(self, dialect):
        self.dialect = dialect

    def set_schema_names(self, objects, columns):
        self.schema_names = (set(objects), set(columns))


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

    def get_highlighter(self):
        return self._highlighter

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
        DummyHighlighter,
    )
    monkeypatch.setattr(
        "expo_jbm329.workbench.controllers.editor_panel_controller.SqlAutocompleteController",
        lambda **kwargs: SimpleNamespace(install=lambda: None, set_dialect=lambda dialect: None),
    )
    monkeypatch.setattr(
        "expo_jbm329.workbench.controllers.editor_panel_controller.SqlLintController",
        lambda **kwargs: SimpleNamespace(
            install=lambda: None,
            schedule_lint=lambda: None,
            dispose=lambda: None,
            deleteLater=lambda: None,
            clear_diagnostics=lambda: None,
            set_dialect=lambda dialect: None,
            set_schema=lambda schema: None,
        ),
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


def _make_ctrl(get_cache_for, build_schema_dict=lambda schema: schema):
    return EditorPanelController(
        tab_manager=EditorTabManager(),
        tab_widget=QTabWidget(),
        icon_service=DummyIconService(),
        highlighter_theme_service=DummyThemeService(),
        get_cache_for=get_cache_for,
        build_schema_dict=build_schema_dict,
        get_connection_engine=lambda conn: "sqlite",
        dialogs=DummyDialogService(),
        parent=QWidget(),
    )


def test_highlighter_created_with_connection_dialect(controller):
    ctrl = _make_ctrl(lambda conn: None)
    ctrl.create_tab(connection_name="db", base_title="Q")
    assert ctrl.get_active_editor_widget().get_highlighter().dialect == "sqlite"


def test_update_autocomplete_makes_highlighter_schema_aware(controller):
    entry = SimpleNamespace(db_name="db", tables=[], views=[], columns={}, loaded_at=None)
    ctrl = _make_ctrl(
        lambda conn: entry,
        build_schema_dict=lambda cache: {"by_schema": {"main": {"Order": ["Id"], "Table": []}}},
    )
    ctrl.create_tab(connection_name="db", base_title="Q")
    ctrl.update_autocomplete_for_active_tab()

    highlighter = ctrl.get_active_editor_widget().get_highlighter()
    assert highlighter.dialect == "sqlite"
    assert highlighter.schema_names == ({"main", "Order", "Table"}, {"Id"})


def test_update_autocomplete_without_connection_resets_highlighter(controller):
    ctrl, _, _ = controller
    ctrl.create_tab(base_title="Q")
    highlighter = ctrl.get_active_editor_widget().get_highlighter()
    highlighter.dialect = "tsql"
    ctrl.update_autocomplete_for_active_tab()

    assert highlighter.dialect is None
    assert highlighter.schema_names == (set(), set())
