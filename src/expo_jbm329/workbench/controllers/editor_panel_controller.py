"""Editor panel controller.

This module provides EditorPanelController, which orchestrates the SQL editor
tabs UI by binding together:

- EditorTabManager (state & policy)
- QTabWidget (Qt tab UI)
- EditorWidget (per-tab editor UI)

The controller is responsible for UI orchestration only. It does not:
- execute SQL
- manage editor text logic
- decide connection policy
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Callable, Iterable

from PyQt6.QtCore import QT_TR_NOOP, QPoint
from PyQt6.QtWidgets import (
    QTabWidget,
    QWidget,
)

from expo_jbm329.db.sql_analysis import sqlglot_dialect
from expo_jbm329.gui.autocomplete.controller import SqlAutocompleteController
from expo_jbm329.gui.autocomplete.engine import SqlAutoCompleter
from expo_jbm329.gui.dialogs.service.dialog_service import DialogService
from expo_jbm329.gui.dialogs.service.qt_dialog_service import QtDialogService
from expo_jbm329.gui.linting.sql_lint_controller import SqlLintController
from expo_jbm329.gui.menus.editor_tab_context_menu import EditorTabContextMenu
from expo_jbm329.gui.widgets.editor_widget import EditorWidget
from expo_jbm329.utils.i18n_utils import tr, tr_fmt
from expo_jbm329.workbench.controllers.editor_tab_manager import (
    EditorTab,
    EditorTabManager,
    EditorTabState,
)
from expo_jbm329.workbench.highlighter.sql_highlighter import SqlHighlighter
from expo_jbm329.workbench.icon.icon_service import IconService
from expo_jbm329.workbench.theme.highlighter_theme_service import HighlighterThemeService


class EditorPanelController(QWidget):
    """Controller responsible for orchestrating SQL editor tabs UI."""

    # --- i18n markers (pylupdate6-visible) -----------------------------
    TR_CLOSE_TAB = QT_TR_NOOP("Close tab")
    TR_UNSAVED_CHANGES = QT_TR_NOOP("Unsaved changes")
    TR_UNSAVED_CHANGES_TO = QT_TR_NOOP("There are unsaved changes in {tab_name}. Close anyway?")
    TR_TAB_NAME_COPY = QT_TR_NOOP("{base_title} (copy)")
    TR_CLOSE_ALL_TABS_SUMMARY = QT_TR_NOOP(
        "You are about to close {count_tabs} tabs.\nUnsaved changes in {dirty_tabs} tabs.\nContinue?"
    )
    TR_RENAME_TAB = QT_TR_NOOP("Rename tab")
    TR_NEW_NAME = QT_TR_NOOP("New name:")

    @staticmethod
    def _tr(text: str) -> str:
        return tr("EditorPanelController", text)

    @staticmethod
    def _tr_fmt(text: str, **kwargs: str) -> str:
        return tr_fmt("EditorPanelController", text, **kwargs)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    __slots__ = (
        "_autocomplete_engine",
        "_dialogs",
        "_get_active_connection",
        "_get_connection_engine",
        "_get_connections",
        "_highlighter_theme_service",
        "_icon_service",
        "_lint_controllers",
        "_logger",
        "_on_active_tab_changed",
        "_save_sql",
        "_save_sql_as",
        "_set_status",
        "_tab_context_menu",
        "_tab_manager",
        "_tab_widget",
        "_widgets",
    )

    def __init__(
        self,
        *,
        tab_manager: EditorTabManager,
        tab_widget: QTabWidget,
        icon_service: IconService,
        highlighter_theme_service: HighlighterThemeService,
        get_cache_for: Callable[[str]],
        build_schema_dict: Callable[[dict], dict],
        get_connection_engine: Callable[[str], str | None] | None = None,
        save_sql: Callable[[], None] | None = None,
        save_sql_as: Callable[[], None] | None = None,
        set_status: Callable[[str, int | None], None] | None = None,
        dialogs: DialogService | None = None,
        parent: QWidget | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialize the editor tabs controller.

        Args:
            tab_manager: EditorTabManager instance (state & policy).
            tab_widget: QTabWidget instance for rendering tabs.
            icon_service: IconService for tab icons.
            highlighter_theme_service: HighlighterThemeService for syntax highlighting.
            get_cache_for: Callable for retrieving schema caches.
            build_schema_dict: Callable for building schema dictionaries.
            get_connection_engine: Callable for retrieving the connection engine.
            save_sql: Callable for saving SQL to a file.
            save_sql_as: Callable for saving SQL to a file with a custom name.
            set_status: Callable  for setting status messages in the UI.
            dialogs: Optional DialogService instance.
            parent: Optional parent widget.
            logger: Optional logger instance.
        """
        super().__init__(parent)

        self._tab_manager = tab_manager
        self._tab_widget = tab_widget
        self._icon_service = icon_service
        self._highlighter_theme_service = highlighter_theme_service
        self._get_cache_for = get_cache_for
        self._build_schema_dict = build_schema_dict
        self._get_connection_engine = get_connection_engine
        self._save_sql = save_sql
        self._save_sql_as = save_sql_as
        self._set_status = set_status
        self._dialogs = dialogs or QtDialogService()
        self._logger = logger if logger is not None else logging.getLogger("applogger.ui")

        self._tab_context_menu: EditorTabContextMenu | None = None

        self._get_active_connection: Callable[[], str | None] | None = None
        self._get_connections: Callable[[], Iterable[str]] | None = None

        # Mapping: tab_id -> EditorWidget
        self._widgets: dict[str, EditorWidget] = {}

        # Mapping: tab_id -> SQL lint controller
        self._lint_controllers: dict[str, SqlLintController] = {}

        # Callbacks
        self._on_active_tab_changed: list[Callable[[], None]] = []

    # ------------------------------------------------------------------
    # Late bindings
    # ------------------------------------------------------------------
    def bind_file_actions(
        self,
        *,
        save_sql: Callable[[], None],
        save_sql_as: Callable[[], None],
    ) -> None:
        """Bind file-related actions after construction.

        Args:
            save_sql: Callback to save the current SQL query.
            save_sql_as: Callback to save the current SQL query with a new filename.
        """
        self._save_sql = save_sql
        self._save_sql_as = save_sql_as
        self._try_init_tab_context_menu()

    def bind_connection_provider(
        self,
        *,
        get_active_connection: Callable[[], str | None],
        get_connections: Callable[[], Iterable[str]],
    ) -> None:
        """Bind connection-related providers after construction."""
        self._get_active_connection = get_active_connection
        self._get_connections = get_connections
        self._try_init_tab_context_menu()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def widget(self) -> QTabWidget:
        """Return the underlying QTabWidget.

        Returns:
            The QTabWidget instance.
        """
        return self._tab_widget

    def create_tab(
        self,
        *,
        connection_name: str | None = None,
        base_title: str | None = None,
    ) -> EditorTab:
        """Create and add a new SQL editor tab.

        Args:
            connection_name: Optional database connection to bind immediately.
            base_title: Optional base title for the tab. If not provided, a default title will be generated.

        Returns:
            The created EditorTab instance.
        """
        self._logger.debug(
            "EditorPanelController: creating tab (connection=%s)",
            connection_name,
        )

        tab = self._tab_manager.create_tab(connection_name=connection_name, base_title=base_title)

        self._logger.info(
            "EditorPanelController: tab created (tab_id=%s, connection=%s)",
            tab.tab_id,
            tab.connection_name,
        )

        editor_widget = EditorWidget(self._tab_widget)
        editor_widget.tab_id = tab.tab_id
        editor_widget.editor_controller.suppress_change()
        editor_widget.editor_controller.set_on_change(
            functools.partial(self._on_editor_text_changed, tab.tab_id)
        )

        editor_widget.apply_tab_state(tab)

        # --- SQL highlighter (per editor tab) ---
        doc = editor_widget.get_document()

        highlighter = SqlHighlighter(
            doc,
            theme=self._highlighter_theme_service.resolve_theme(),
        )
        editor_widget.set_highlighter(highlighter)

        # React to SQL highlighter theme changes
        self._highlighter_theme_service.theme_changed.connect(highlighter.set_theme)
        highlighter.rehighlight()

        # --- SQL autocomplete (per editor tab) ---
        autocomplete_engine = SqlAutoCompleter()
        autocomplete = SqlAutocompleteController(
            editor=editor_widget.get_editor(),
            completer=autocomplete_engine,
            debug=False,
        )
        autocomplete.install()
        editor_widget.set_autocomplete_engine(autocomplete_engine)
        editor_widget.set_autocomplete(autocomplete)

        # --- SQL linting (per editor tab) ---
        lint_controller = SqlLintController(
            editor=editor_widget.get_editor(),
            logger=self._logger,
            set_status=self._set_status,
        )
        lint_controller.install()
        self._lint_controllers[tab.tab_id] = lint_controller

        title = self._tab_manager.build_tab_title(tab)

        index = self._tab_widget.addTab(editor_widget, title)
        self._widgets[tab.tab_id] = editor_widget
        self._tab_widget.setCurrentIndex(index)

        editor_widget.editor_controller.resume_change()

        return tab

    def bind_tab_to_connection(self, tab_id: str, connection_name: str) -> None:
        """Bind a tab to a database connection and update UI.

        Args:
            tab_id: The ID of the tab to bind.
            connection_name: The name of the database connection to bind to.
        """
        self._tab_manager.bind_tab_to_connection(tab_id, connection_name)

        tab = self._tab_manager.get_tab(tab_id)
        if not tab:
            return

        if self._get_active_connection is None:
            return

        active_conn = self._get_active_connection()

        if active_conn == connection_name:
            tab.state = EditorTabState.BOUND
        else:
            tab.state = EditorTabState.DISCONNECTED

        self.update_tab(tab)
        self.notify_active_tab_changed()

    def unbind_tab(self, tab_id: str) -> None:
        """Unbind a tab from its database connection and update UI.

        Args:
            tab_id: The ID of the tab to unbind.
        """
        self._tab_manager.unbind_tab(tab_id)

        tab = self._tab_manager.get_tab(tab_id)
        if tab:
            self.update_tab(tab)
            self.notify_active_tab_changed()

    def duplicate_tab(self, tab_id: str) -> None:
        """Duplicate an editor tab.

        Args:
            tab_id: The ID of the tab to duplicate.
        """
        tab = self._tab_manager.get_tab(tab_id)
        if not tab:
            return

        new_tab = self.create_tab(
            connection_name=tab.connection_name,
            base_title=self._tr_fmt(self.TR_TAB_NAME_COPY, base_title=tab.base_title),
        )

        widget = self._widgets.get(tab_id)
        if widget:
            self.insert_sql_into_tab(new_tab, widget.get_sql_text() or "")
            self._tab_manager.mark_dirty(new_tab.tab_id)
            self.update_tab(new_tab)

    def rename_tab(self, tab_id: str, new_base_title: str) -> None:
        """Rename a tab and update its UI.

        Args:
            tab_id: The ID of the tab to rename.
            new_base_title: The new base title for the tab.
        """
        self._tab_manager.rename_tab(tab_id, new_base_title)

        tab = self._tab_manager.get_tab(tab_id)
        if tab:
            self.update_tab(tab)

    def rename_tab_by_index(self, index: int) -> None:
        """Rename an editor tab by index (e.g. on tab double-click).

        Args:
            index: The index of the tab to rename.
        """
        widget = self._tab_widget.widget(index)
        if not widget:
            return

        for tab_id, w in self._widgets.items():
            if w is widget:
                tab = self._tab_manager.get_tab(tab_id)
                if not tab:
                    return

                new_name, ok = self._dialogs.prompt_text(
                    parent=self,
                    title=self._tr(self.TR_RENAME_TAB),
                    label=self._tr(self.TR_NEW_NAME),
                    default=tab.base_title,
                )
                if not ok:
                    return

                name = new_name.strip()
                if not name or name == tab.base_title:
                    return

                self.rename_tab(tab_id, name)

    def insert_sql_into_tab(self, tab: EditorTab, sql: str) -> None:
        """Insert SQL into a specific tab (not active tab).

        Args:
            tab: The tab to insert SQL into.
            sql: The SQL to insert.
        """
        widget = self._widgets.get(tab.tab_id)
        if not widget:
            return

        ec = widget.editor_controller
        ec.suppress_change()
        ec.insert_sql(sql)
        ec.resume_change()

        self._tab_manager.mark_dirty(tab.tab_id)
        self.update_tab(tab)

        lint_controller = self._lint_controllers.get(tab.tab_id)
        if lint_controller is not None:
            lint_controller.schedule_lint()

    def get_active_sql(self, *, use_selection: bool) -> str | None:
        """Return SQL from the active editor tab.

        Args:
            use_selection: Whether to return the selected SQL or the entire content.

        Returns:
            The SQL string or None if no active tab or widget.
        """
        tab = self.get_active_tab()
        if not tab:
            return None

        widget = self._widgets.get(tab.tab_id)
        if not widget:
            return None

        return widget.editor_controller.get_sql(use_selection)

    def update_tab(self, tab: EditorTab) -> None:
        """Update UI for an existing editor tab.

        This should be called after any state change affecting the tab:
        - bind / unbind
        - disconnect / reconnect
        - language change

        Args:
            tab: The EditorTab to update.
        """
        widget = self._widgets.get(tab.tab_id)
        if not widget:
            return

        index = self._tab_widget.indexOf(widget)
        if index < 0:
            return

        widget.apply_tab_state(tab)
        title = self._tab_manager.build_tab_title(tab)
        self._tab_widget.setTabText(index, title)

    def close_tab(self, tab_id: str) -> None:
        """Close an editor tab by id, with dirty-state confirmation.

        Args:
            tab_id: Identifier of the tab to close.
        """
        tab = self._tab_manager.get_tab(tab_id)
        if not tab:
            return

        # --------------------------------------------------
        # Dirty tab → confirm
        # --------------------------------------------------
        if tab.is_dirty:
            ok = self._confirm_close_dirty_tab(tab)
            if not ok:
                return

        # --------------------------------------------------
        # Proceed with close
        # --------------------------------------------------
        widget = self._widgets.get(tab_id)
        if not widget:
            return

        index = self._tab_widget.indexOf(widget)
        if index < 0:
            return

        self._tab_widget.removeTab(index)

        lint_controller = self._lint_controllers.pop(tab_id, None)
        if lint_controller is not None:
            lint_controller.dispose()
            lint_controller.deleteLater()

        widget.deleteLater()
        self._widgets.pop(tab_id, None)

        self._logger.info(
            "EditorPanelController: tab closed (tab_id=%s)",
            tab_id,
        )

        self._tab_manager.close_tab(tab_id)

    def close_other_tabs(self, tab_id: str) -> None:
        """Close all editor tabs except the given one.

        Args:
            tab_id: The ID of the tab to keep open.
        """
        if tab_id not in self._widgets:
            return

        # Iterate over a snapshot of tab ids
        tab_ids = list(self._widgets.keys())
        for other_id in tab_ids:
            if other_id == tab_id:
                continue
            self.close_tab(other_id)

    def close_tabs_to_right(self, tab_id: str) -> None:
        """Close all editor tabs to the right of the given one.

        Args:
            tab_id: The ID of the tab to keep open.
        """
        widget = self._widgets.get(tab_id)
        if not widget:
            return

        start_index = self._tab_widget.indexOf(widget)
        if start_index < 0:
            return

        # 1. Snapshot widgets to the right, in correct order
        widgets_to_close = [
            self._tab_widget.widget(i)
            for i in range(start_index + 1, self._tab_widget.count())
            if self._tab_widget.widget(i) is not None
        ]

        # 2. Resolve tab_ids from widgets (stable snapshot)
        tab_ids_to_close: list[str] = []
        widget_to_id = {w: tid for tid, w in self._widgets.items()}

        for w in widgets_to_close:
            tid = widget_to_id.get(w)
            if tid:
                tab_ids_to_close.append(tid)

        # 3. Close after snapshot to avoid mutation issues
        for tid in tab_ids_to_close:
            self.close_tab(tid)

    def close_all_with_summary(self, keep_tab_id: str | None = None) -> None:
        """Close all editor tabs, showing a summary dialog.

        Args:
            keep_tab_id: The ID of the tab to keep open, if any.
        """
        tabs = list(self._widgets.keys())
        dirty = [
            tid
            for tid in tabs
            if self._tab_manager.get_tab(tid) and self._tab_manager.get_tab(tid).is_dirty
        ]
        count_tabs = len(tabs)
        dirty_tabs = len(dirty)
        msg = self._tr_fmt(
            self.TR_CLOSE_ALL_TABS_SUMMARY,
            count_tabs=str(count_tabs),
            dirty_tabs=str(dirty_tabs),
        )

        ok = self._dialogs.prompt_yes_no(
            self,
            title=self._tr("Close all tabs"),
            text=msg,
            default_yes=False,
        )
        if not ok:
            return

        for tid in tabs:
            self.close_tab(tid)

    def close_tab_by_index(self, index: int) -> None:
        """Close an editor tab by index.

        Args:
            index: The index of the tab to close.
        """
        widget = self._tab_widget.widget(index)
        if not widget:
            return

        # Snapshot to avoid mutation during iteration
        for tab_id, w in list(self._widgets.items()):
            if w is widget:
                self.close_tab(tab_id)
                break

    def get_active_tab_text(self) -> str | None:
        """Return full SQL text from the active editor tab.

        Returns:
            The SQL text of the active tab, or None if no active tab is found.
        """
        tab = self.get_active_tab()
        if not tab:
            return None

        widget = self._widgets.get(tab.tab_id)
        if not widget:
            return None

        return widget.get_sql_text() or None

    def set_active_tab_text(self, text: str) -> None:
        """Replace SQL text in the active editor tab.

        Args:
            text: The new SQL text to set in the active tab.
        """
        tab = self.get_active_tab()
        if not tab:
            return

        widget = self._widgets.get(tab.tab_id)
        if not widget:
            return

        widget.set_sql_text(text)
        widget.focus_editor()

        lint_controller = self._lint_controllers.get(tab.tab_id)
        if lint_controller is not None:
            lint_controller.schedule_lint()

    def on_active_tab_changed(self, callback: Callable[[], None]) -> None:
        """Register a callback for active editor-tab changes.

        Args:
            callback: The function to call when the active tab changes.
        """
        self._on_active_tab_changed.append(callback)

    def can_execute_sql(self) -> bool:
        """Return True if SQL execution is allowed for the active tab.

        Returns:
            True if SQL execution is allowed, False otherwise.
        """
        return self._tab_manager.can_execute_sql()

    def notify_active_tab_changed(self) -> None:
        """Notify listeners that the active tab has changed."""
        for cb in self._on_active_tab_changed:
            cb()

    def get_active_editor_widget(self) -> EditorWidget | None:
        """Return the active EditorWidget, if any.

        Returns:
            The active EditorWidget, or None if no active tab is found.
        """
        tab = self.get_active_tab()
        if not tab:
            return None
        return self._widgets.get(tab.tab_id)

    def new_file(self) -> None:
        """Create a new unbound editor tab.

        The tab will be editable but have no connection context,
        meaning no SQL execution or autocomplete.
        """
        self.create_tab(connection_name=None)

    def clear_active_tab(self) -> None:
        """Clear SQL content in the active editor tab."""
        tab = self.get_active_tab()
        if not tab:
            return

        widget = self._widgets.get(tab.tab_id)
        if not widget:
            return

        widget.set_sql_text("")
        widget.focus_editor()

        lint_controller = self._lint_controllers.get(tab.tab_id)
        if lint_controller is not None:
            lint_controller.clear_diagnostics()

    def get_active_tab(self) -> EditorTab | None:
        """Return the currently active editor tab.

        Returns:
            The active editor tab, or None if no tab is active.
        """
        return self._tab_manager.get_active_tab()

    def clear_dirty(self, tab_id: str) -> None:
        """Clear the dirty flag for a specific editor tab.

        Args:
            tab_id: The ID of the tab to clear the dirty flag for.
        """
        self._tab_manager.clear_dirty(tab_id)
        tab = self.get_active_tab()
        if tab and tab.tab_id == tab_id:
            self.update_tab(tab)

    def on_tab_state_changed(self) -> None:
        """Refresh UI for all editor tabs after tab state changes."""
        for tab in self._tab_manager.iter_tabs():
            self.update_tab(tab)
        self.notify_active_tab_changed()

    def activate_tab_for_connection(self, connection_name: str) -> EditorTab | None:
        """Ensure a tab exists for the connection and make it active.

        Args:
            connection_name: The name of the connection to activate.

        Returns:
            The EditorTab that was activated, or None if activation failed.
        """
        tab = None

        for t in self._tab_manager.iter_tabs():
            if t.connection_name == connection_name:
                tab = t
                break

        if tab is None:
            tab = self.create_tab(connection_name=connection_name)

        widget = self._widgets.get(tab.tab_id)
        if not widget:
            return tab

        index = self._tab_widget.indexOf(widget)
        if index < 0:
            return tab

        # Block signals
        self._tab_widget.blockSignals(True)
        try:
            self._tab_widget.setCurrentIndex(index)
        finally:
            self._tab_widget.blockSignals(False)

        self._tab_manager.set_active_tab(tab.tab_id)

        return tab

    def create_and_activate_tab(self, connection_name: str) -> EditorTab:
        """Always create a new tab for a connection and activate it."""
        tab = self.create_tab(connection_name=connection_name)

        widget = self._widgets.get(tab.tab_id)
        if not widget:
            return tab

        index = self._tab_widget.indexOf(widget)
        if index >= 0:
            self._tab_widget.setCurrentIndex(index)

        self._tab_manager.set_active_tab(tab.tab_id)
        return tab

    def ensure_tab_for_connection(self, connection_name: str) -> None:
        """Ensure there is an editor tab bound to the given connection.

        If no such tab exists, create one.

        Args:
            connection_name: The name of the connection to ensure a tab for.
        """
        for tab in self._tab_manager.iter_tabs():
            if tab.connection_name == connection_name:
                return

        # No existing tab → create one
        self.create_tab(connection_name=connection_name)

    def _resolve_autocomplete_dialect(self, connection_name: str | None) -> str | None:
        """Resolve the sqlglot dialect for a connection.

        Args:
            connection_name: Connection name bound to the active editor tab.

        Returns:
            A sqlglot dialect name, or None if no dialect can be resolved.
        """
        if not connection_name or self._get_connection_engine is None:
            return None

        try:
            engine = self._get_connection_engine(connection_name)
        except Exception:
            self._logger.debug(
                "EditorPanelController: failed to resolve autocomplete dialect (conn=%s)",
                connection_name,
                exc_info=True,
            )
            return None

        dialect = sqlglot_dialect(engine)

        self._logger.debug(
            "EditorPanelController: resolved autocomplete dialect (conn=%s, engine=%s, dialect=%s)",
            connection_name,
            engine,
            dialect,
        )

        return dialect

    def update_autocomplete_for_connection(self, connection_name: str) -> None:
        """Update autocomplete if the active tab belongs to the given connection.

        This is intended to be used as SchemaCacheManager.autocomplete_cb.
        The schema cache callback provides the connection name whose metadata
        changed, and this method rebuilds autocomplete only when the active
        editor tab is bound to that same connection.

        Args:
            connection_name: Connection whose schema cache changed.
        """
        tab = self.get_active_tab()

        if not tab:
            self._logger.debug(
                "EditorPanelController: autocomplete rebuild skipped "
                "(changed_conn=%s, reason=no active tab)",
                connection_name,
            )
            return

        if tab.connection_name != connection_name:
            self._logger.debug(
                "EditorPanelController: autocomplete rebuild skipped "
                "(changed_conn=%s, active_conn=%s)",
                connection_name,
                tab.connection_name,
            )
            return

        self._logger.debug(
            "EditorPanelController: autocomplete rebuild requested for active connection %s",
            connection_name,
        )
        self.update_autocomplete_for_active_tab()

    def update_autocomplete_for_active_tab(self) -> None:
        """Update SQL autocomplete for the active editor tab."""
        widget = self.get_active_editor_widget()
        if not widget:
            return

        engine = widget.get_autocomplete_engine()
        autocomplete = widget.get_autocomplete()
        tab = self.get_active_tab()

        # No tab or no connection → empty schema and no dialect.
        if not tab or not tab.connection_name:
            engine.set_schema({})
            autocomplete.set_dialect(None)

            if tab is not None:
                lint_controller = self._lint_controllers.get(tab.tab_id)
                if lint_controller is not None:
                    lint_controller.set_dialect(None)
            return

        dialect = self._resolve_autocomplete_dialect(tab.connection_name)
        autocomplete.set_dialect(dialect)

        lint_controller = self._lint_controllers.get(tab.tab_id)
        if lint_controller is not None:
            lint_controller.set_dialect(dialect)

        entry = self._get_cache_for(tab.connection_name)
        if not entry:
            engine.set_schema({})
            if lint_controller is not None:
                lint_controller.set_schema({})
            return

        schema_dict = self._build_schema_dict({
            "db_name": entry.db_name,
            "tables": entry.tables,
            "views": entry.views,
            "columns": entry.columns,
            "loaded_at": entry.loaded_at,
        })

        by_schema = schema_dict.get("by_schema", {})
        object_count = 0
        non_empty_column_tables = 0

        if isinstance(by_schema, dict):
            for tables in by_schema.values():
                if not isinstance(tables, dict):
                    continue

                object_count += len(tables)

                for columns in tables.values():
                    if columns:
                        non_empty_column_tables += 1

        self._logger.debug(
            "EditorPanelController: autocomplete and lint schema rebuilt "
            "(conn=%s, dialect=%s, schemas=%s, objects=%s, non_empty_column_tables=%s)",
            tab.connection_name,
            dialect,
            list(by_schema.keys()) if isinstance(by_schema, dict) else [],
            object_count,
            non_empty_column_tables,
        )

        engine.set_schema(schema_dict)
        if lint_controller is not None:
            lint_controller.set_schema(schema_dict)

    def on_tab_context_menu_requested(self, pos: QPoint) -> None:
        """Handle context menu request on the tab bar.

        Args:
            pos: The position of the context menu request in the tab bar.
        """
        if self._tab_context_menu is None:
            return

        tab_bar = self._tab_widget.tabBar()
        if tab_bar is None:
            return
        index = tab_bar.tabAt(pos)
        if index < 0:
            return

        widget = self._tab_widget.widget(index)
        if not widget:
            return

        # Resolve tab_id from widget
        for tab_id, w in self._widgets.items():
            if w is widget:
                self._tab_context_menu.show(
                    tab_id=tab_id,
                    global_pos=tab_bar.mapToGlobal(pos),
                )
                return

    def on_current_tab_changed(self, index: int) -> None:
        """Handle active tab change from the UI.

        Args:
            index: The index of the new active tab.
        """
        if index < 0:
            return

        widget = self._tab_widget.widget(index)
        if not widget:
            return

        for tab_id, w in self._widgets.items():
            if w is widget:
                self._tab_manager.set_active_tab(tab_id)
                tab = self.get_active_tab()

                if tab:
                    self._logger.debug(
                        "EditorPanelController: active tab changed (tab_id=%s, connection=%s, state=%s)",
                        tab.tab_id,
                        tab.connection_name,
                        tab.state.name,
                    )

                w.focus_editor()

                for cb in self._on_active_tab_changed:
                    cb()
                break

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _on_editor_text_changed(self, tab_id: str) -> None:
        """Handle text changes from an editor widget."""
        self._tab_manager.mark_dirty(tab_id)

        tab = self.get_active_tab()
        if tab and tab.tab_id == tab_id:
            self.update_tab(tab)

    def _confirm_close_dirty_tab(self, tab: EditorTab) -> bool:
        """Ask user to confirm closing a dirty tab.

        Returns True if the tab may be closed.

        Note:
            The tab parameter is currently unused, but intentionally kept
            for future extensions (e.g. Save / Discard / Cancel dialogs
            showing tab-specific information).
        """
        tab_name = tab.base_title
        return self._dialogs.prompt_yes_no(
            self,
            title=self._tr(self.TR_UNSAVED_CHANGES),
            text=self._tr_fmt(self.TR_UNSAVED_CHANGES_TO, tab_name=tab_name),
            default_yes=False,
        )

    def _try_init_tab_context_menu(self) -> None:
        """Initialize the tab context menu once all dependencies are bound."""
        if self._tab_context_menu is not None:
            return

        if (
            self._save_sql is None
            or self._save_sql_as is None
            or self._get_connections is None
            or self._get_active_connection is None
        ):
            return  # Not ready yet

        self._tab_context_menu = EditorTabContextMenu(
            get_tab=self._tab_manager.get_tab,
            get_all_tab_ids=lambda: list(self._widgets.keys()),
            rename_tab=self.rename_tab,
            close_tab=self.close_tab,
            close_other_tabs=self.close_other_tabs,
            close_tabs_to_right=self.close_tabs_to_right,
            save_tab=self._save_sql,
            save_tab_as=self._save_sql_as,
            duplicate_tab=self.duplicate_tab,
            get_connections=self._get_connections,
            bind_tab_to_connection=self.bind_tab_to_connection,
            unbind_tab=self.unbind_tab,
            close_all_tabs=self.close_all_with_summary,
            parent=self,
        )
