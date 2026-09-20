"""Schema controller for managing the database schema tree.

This module provides the SchemaController class, which manages the schema tree
widget for browsing database objects. It handles tree rendering, lazy column
loading and SQL snippet generation for query building.
The controller communicates with the schema cache manager for efficient data
retrieval and supports theme changes via icon updates.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from PyQt6.QtCore import QT_TR_NOOP, QPoint, Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QApplication,
    QMenu,
    QTreeWidgetItem,
    QWidget,
)

from expo_jbm329.db.base import (
    build_select_columns_auto,
    build_select_distinct,
    build_select_star,
    list_columns,
)
from expo_jbm329.gui.dialogs.service.qt_dialog_service import QtDialogService
from expo_jbm329.gui.gui_utils import ui_invoke
from expo_jbm329.utils.format_utils import fmt_int
from expo_jbm329.utils.i18n_utils import tr, tr_fmt

if TYPE_CHECKING:
    from collections.abc import Callable

    from expo_jbm329.gui.dialogs.service.dialog_service import DialogService
    from expo_jbm329.gui.widgets.schema_tree_widget import SchemaTreeWidget
    from expo_jbm329.services.job_manager import JobManager
    from expo_jbm329.services.schema_cache import SchemaCacheManager
    from expo_jbm329.workbench.controllers.async_operation_controller import (
        AsyncOperationController,
    )
    from expo_jbm329.workbench.controllers.editor_tab_manager import EditorTab
    from expo_jbm329.workbench.icon.icon_service import IconService


class SchemaController:
    """Controller for managing the schema tree and related operations.

    This class handles schema tree rendering, lazy column loading, SQL snippet
    insertion, and autocomplete rebuild triggered by the SchemaCacheManager.
    """

    # --- i18n markers (pylupdate6-visible) -----------------------------
    TR_CONNECT = QT_TR_NOOP("Connect")
    TR_DISCONNECT = QT_TR_NOOP("Disconnect")
    TR_LOADING_SCHEMA_STATUS = QT_TR_NOOP("Loading schema…")
    TR_TABLES_GROUP = QT_TR_NOOP("Tables")
    TR_VIEWS_GROUP = QT_TR_NOOP("Views")
    TR_SCHEMA_DONE_STATUS = QT_TR_NOOP("Finished loading schema")
    TR_FAILURE = QT_TR_NOOP("Failure")
    TR_COULD_NOT_LOAD_SCHEMA = QT_TR_NOOP("Could not load schema. \n\n{error}")
    TR_FAILED_TO_LOAD_SCHEMA_STATUS = QT_TR_NOOP("Failed to load schema")
    TR_COLUMNS_PLACEHOLDER = QT_TR_NOOP("(Columns …)")
    TR_PRELOADING_SCHEMA_STATUS = QT_TR_NOOP("Preloading schema… {done}/{total}")

    @staticmethod
    def _tr(text: str) -> str:
        return tr("SchemaController", text)

    @staticmethod
    def _tr_fmt(text: str, **kwargs: str) -> str:
        return tr_fmt("SchemaController", text, **kwargs)

    __slots__ = (
        "__weakref__",
        "_async_ops",
        "_connect_connection",
        "_create_tab_for_connection",
        "_dialogs",
        "_disconnect_connection",
        "_gen_top_n",
        "_gen_top_n_default",
        "_get_conn_name",
        "_get_current_connection",
        "_icon_service",
        "_insert_sql_into_tab",
        "_job_mgr",
        "_logger",
        "_parent",
        "_restore_baseline_status",
        "_schema_mgr",
        "_set_autocomplete_schema",
        "_set_status",
        "_tree",
    )

    def __init__(
        self,
        *,
        parent_widget: QWidget,
        tree_widget: SchemaTreeWidget,
        schema_mgr: SchemaCacheManager,
        async_ops: AsyncOperationController,
        job_mgr: JobManager,
        create_tab_for_connection: Callable[[str], EditorTab],
        insert_sql_into_tab: Callable[[EditorTab, str], None],
        set_status: Callable[[str, int | None], None],
        icon_service: IconService,
        get_current_connection: Callable[[], str | None],
        connect_connection: Callable[[str], None],
        disconnect_connection: Callable[[str], None],
        restore_baseline_status: Callable[[], None],
        dialogs: DialogService | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialize the SchemaController.

        Args:
            parent_widget: The parent widget.
            tree_widget: The tree widget for the schema.
            schema_mgr: The schema cache manager.
            async_ops: The async operation controller.
            job_mgr: The job manager.
            create_tab_for_connection: Callback to activate a tab for a connection.
            insert_sql_into_tab: Callback to insert SQL into a tab.
            set_status: Callback to set status.
            icon_service: Service for icons.
            get_current_connection: Callback to get current connection.
            connect_connection: Callback to connect a connection.
            disconnect_connection: Callback to disconnect a connection.
            restore_baseline_status: Callback to restore baseline status.
            dialogs: Dialog service, defaults to QtDialogService.
            logger: Optional logger.
        """
        self._parent = parent_widget
        self._tree = tree_widget
        self._schema_mgr = schema_mgr
        self._async_ops = async_ops
        self._job_mgr = job_mgr
        self._create_tab_for_connection = create_tab_for_connection
        self._insert_sql_into_tab = insert_sql_into_tab
        self._set_status = set_status
        self._icon_service = icon_service
        self._get_current_connection = get_current_connection
        self._connect_connection = connect_connection
        self._disconnect_connection = disconnect_connection
        self._restore_baseline_status = restore_baseline_status
        self._dialogs = dialogs if dialogs is not None else QtDialogService()
        self._gen_top_n_default = 1000
        self._gen_top_n: int = self._gen_top_n_default
        self._logger = logger if logger is not None else logging.getLogger("applogger.ui")

        # Tree events
        self._tree.customContextMenuRequested.connect(self._on_context_menu)
        self._tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._tree.itemExpanded.connect(self._on_item_expanded)

        # Bind schema manager callbacks after initialization to ensure all dependencies are set up
        self._bind_schema_manager_callbacks()

    # ==================================================================
    # Properties (read only, clean public API)
    # ==================================================================
    @property
    def schema_mgr(self) -> SchemaCacheManager:
        """Get the schema manager."""
        return self._schema_mgr

    # ==================================================================
    # Async helpers
    # ==================================================================
    def _bind_schema_manager_callbacks(self) -> None:
        """Bind SchemaCacheManager callbacks owned by SchemaController."""
        self._schema_mgr.progress_cb = self.on_schema_progress
        self._schema_mgr.set_job_runner(self._run_schema_prefetch_job)

        self._logger.debug("SchemaController: schema manager callbacks bound.")

    def _run_schema_prefetch_job(
        self,
        parent: object,
        fn: Callable[..., object],
        *args: object,
        started_msg: str = "",
        corr_id: str | None = None,
    ) -> object:
        """Run schema prefetch work through AsyncOperationController.

        SchemaCacheManager owns worker result/error signal handling, so this
        adapter only returns the job handle. Result/error callbacks here are
        intentionally no-ops to avoid duplicate handling.
        """
        _ = parent

        if corr_id is None:
            corr_id = uuid.uuid4().hex

        scope = "schema:prefetch"

        def _work(
            *,
            progress_cb: object = None,
            cancel_cb: Callable[[], bool] | None = None,
            job_id: str | None = None,
            job_scope: str | None = None,
            **extra_context: object,
        ) -> object:
            _ = progress_cb, job_id, job_scope, extra_context
            if cancel_cb and cancel_cb():
                return None

            return fn(*args)

        self._logger.debug(
            "SchemaController: scheduling schema prefetch job (scope=%s, corr=%s).",
            scope,
            corr_id,
        )

        return self._async_ops.run_operation(
            runner="thread",
            work=_work,
            on_result=lambda _payload: None,
            on_error=lambda _err: None,
            busy_message=started_msg,
            scope=scope,
            operation_name=started_msg or "schema prefetch",
            show_overlay=False,
            indeterminate=True,
            cancelable=True,
            foreground=False,
            show_status_progress=False,
            show_started_in_status=False,
            suppress_error_dialog=True,
            corr_id=corr_id,
        )

    # ==================================================================
    # Settings
    # ==================================================================

    def reload_settings(self, settings: dict[str, object]) -> None:
        """Reload settings for the SchemaController.

        Synchronizes with updated global settings, controlling TOP_N.

        Args:
            settings: The settings dictionary.
        """
        try:
            editor = settings.get("workbench", {})
            if not isinstance(editor, dict):
                editor = {}
            gen_top_n = int(editor.get("gen_top_n", self._gen_top_n_default))

            if gen_top_n < 0 or gen_top_n is None:  # Allow 0, reject only negative
                gen_top_n = self._gen_top_n_default

            self._gen_top_n = gen_top_n
            self._logger.info("SchemaController: settings reloaded (gen_top_n=%s).", self._gen_top_n)

        except (
            AttributeError,
            ConnectionError,
            FileNotFoundError,
            IndexError,
            KeyError,
            LookupError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as e:
            self._logger.exception("SchemaController: failed to reload settings: %s", e)

    def update_icons(self) -> None:
        """Update icons in the schema tree for theme changes.

        Walks the tree and reapplies icons based on item metadata.
        """
        if self._tree.topLevelItemCount() == 0:
            return

        self._logger.debug("SchemaController: icons refreshed due to theme change.")

        def apply_icon(item_x: QTreeWidgetItem) -> None:
            meta = item_x.data(0, Qt.ItemDataRole.UserRole)

            if isinstance(meta, dict):
                t = meta.get("type")

                if t == "connection":
                    connected = meta.get("connected", False)
                    icon_id = "connected" if connected else "disconnected"
                    item_x.setIcon(0, self._icon_service.get(icon_id))

                elif t == "database":
                    item_x.setIcon(0, self._icon_service.get("database"))
                elif t == "group":
                    item_x.setIcon(0, self._icon_service.get("folder"))
                elif t in ("table", "view"):
                    item_x.setIcon(0, self._icon_service.get(t))
                elif t == "column":
                    item_x.setIcon(0, self._icon_service.get("column"))

            for item_no in range(item_x.childCount()):
                child = item_x.child(item_no)
                if child is not None:
                    apply_icon(child)

        for item_top_no in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(item_top_no)
            if item is not None:
                apply_icon(item)
        self._tree.repaint()

    # ==================================================================
    # Connections
    # ==================================================================
    def _build_connection_nodes(self, connection_names: list[str]) -> None:
        """Build top-level connection nodes in the schema tree."""
        self._tree.clear()

        for name in connection_names:
            item = QTreeWidgetItem([name])
            item.setData(
                0,
                Qt.ItemDataRole.UserRole,
                {
                    "type": "connection",
                    "name": name,
                    "connected": False,
                },
            )
            item.setIcon(0, self._icon_service.get("disconnected"))

            font = item.font(0)
            font.setBold(False)
            item.setFont(0, font)

            item.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
            self._tree.addTopLevelItem(item)

    # ==================================================================
    # Refresh connections
    # ==================================================================
    def refresh_connections(self, connection_names: list[str]) -> None:
        """Refresh the schema tree connection nodes.

        This is the single public entry point for rebuilding
        connection-level nodes in the schema tree.
        """
        self._logger.debug(
            "SchemaController: refreshing schema connections (count=%s)",
            fmt_int(len(connection_names)),
        )
        self._build_connection_nodes(connection_names)

    # ==================================================================
    # Load & refresh schema
    # ==================================================================
    def load_schema_tree(self, connection_name: str, force_refresh: bool = False, corr_id: str | None = None) -> None:
        """Load the schema tree for a connection.

        Args:
            connection_name: The name of the connection.
            force_refresh: Whether to force a refresh.
            corr_id: The correlation ID for the operation.
        """
        if corr_id is None:
            corr_id = uuid.uuid4().hex

        if not connection_name:
            self._logger.debug("SchemaController: load schema tree aborted: empty connection name.")
            return

        self._logger.info(
            "SchemaController: loading schema (conn=%s, force_refresh=%s, corr=%s)",
            connection_name,
            force_refresh,
            corr_id,
        )

        self._set_status(self._tr(self.TR_LOADING_SCHEMA_STATUS), 1500)
        QApplication.processEvents()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)

        try:
            entry = self._schema_mgr.load_schema(connection_name, force_refresh=force_refresh, corr_id=corr_id)

            root_item: QTreeWidgetItem | None = None
            for i in range(self._tree.topLevelItemCount()):
                item = self._tree.topLevelItem(i)
                if item is None:
                    continue

                meta = item.data(0, Qt.ItemDataRole.UserRole)
                if isinstance(meta, dict) and meta.get("type") == "connection" and meta.get("name") == connection_name:
                    root_item = item
                    break

            if root_item is None:
                return

            root_item.takeChildren()

            meta = root_item.data(0, Qt.ItemDataRole.UserRole)

            root_item.setData(
                0,
                Qt.ItemDataRole.UserRole,
                {
                    **meta,
                    "connected": True,
                    "db_name": entry.db_name,
                },
            )
            root_item.setIcon(0, self._icon_service.get("connected"))

            font = root_item.font(0)
            font.setBold(True)
            root_item.setFont(0, font)

            db_item = QTreeWidgetItem([entry.db_name])
            db_item.setData(
                0,
                Qt.ItemDataRole.UserRole,
                {"type": "database", "name": entry.db_name},
            )
            db_item.setIcon(0, self._icon_service.get("database"))
            root_item.addChild(db_item)

            tables_group = self._create_group_item(self._tr(self.TR_TABLES_GROUP), "tables")
            views_group = self._create_group_item(self._tr(self.TR_VIEWS_GROUP), "views")
            db_item.addChildren([tables_group, views_group])

            # Tables
            tbl_count = 0
            for tbl in entry.tables:
                sch, name = tbl["schema"], tbl["name"]
                tables_group.addChild(self._create_object_item("table", sch, name))
                tbl_count += 1

            # Views
            vw_count = 0
            for vw in entry.views:
                sch, name = vw["schema"], vw["name"]
                views_group.addChild(self._create_object_item("view", sch, name))
                vw_count += 1

            self._tree.expandItem(root_item)

            # Build initial autocomplete (empty cols until bulk finishes)
            self._logger.debug(
                "SchemaController: building initial autocomplete (conn=%s, db=%s, tables=%s, views=%s, corr=%s)",
                connection_name,
                entry.db_name,
                fmt_int(tbl_count),
                fmt_int(vw_count),
                corr_id,
            )

            # Async prefetch
            self._logger.debug(
                "SchemaController: prefetch columns async requested (conn=%s, corr=%s).", connection_name, corr_id
            )
            self._schema_mgr.prefetch_columns_async(connection_name, corr_id=corr_id)

            self._set_status(self._tr(self.TR_SCHEMA_DONE_STATUS), 4000)
            self._logger.info(
                "SchemaController: schema loaded (conn=%s, db=%s, tables=%s, views=%s, corr=%s)",
                connection_name,
                entry.db_name,
                fmt_int(tbl_count),
                fmt_int(vw_count),
                corr_id,
            )

        except (
            AttributeError,
            ConnectionError,
            FileNotFoundError,
            IndexError,
            KeyError,
            LookupError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as e:
            self._handle_schema_error(e, connection_name, self._tr(self.TR_FAILED_TO_LOAD_SCHEMA_STATUS))
            raise

        finally:
            QApplication.restoreOverrideCursor()

    def refresh_current_schema(self) -> None:
        """Refresh schema for the currently selected connection.

        This is the public entry point used by UI actions such as toolbar refresh.
        Ensures consistent behaviour including state reset and forced reload.
        """
        conn = self._get_current_connection()

        corr_id = uuid.uuid4().hex

        if not conn:
            self._logger.debug("SchemaController: refresh skipped (no active connection)")
            return

        self._logger.info("SchemaController: refresh requested (conn=%s)", conn)

        try:
            if hasattr(self._job_mgr, "cancel_scope"):
                self._job_mgr.cancel_scope(f"load:{conn}")
        except (
            AttributeError,
            ConnectionError,
            FileNotFoundError,
            IndexError,
            KeyError,
            LookupError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ):
            self._logger.debug("SchemaController: cancel_scope failed", exc_info=True)

        try:
            self.load_schema_tree(conn, force_refresh=True, corr_id=corr_id)
        except (
            AttributeError,
            ConnectionError,
            FileNotFoundError,
            IndexError,
            KeyError,
            LookupError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ):
            # Already handled via _handle_schema_error
            self._logger.debug("SchemaController: refresh failed (handled)")

    # ==================================================================
    # Tree builders
    # ==================================================================
    def _create_group_item(self, title: str, group_type: str) -> QTreeWidgetItem:
        """Create a group item for the tree.

        Args:
            title: The title of the group.
            group_type: The type of the group.

        Returns:
            QTreeWidgetItem: The created item.
        """
        item = QTreeWidgetItem([title])
        item.setData(0, Qt.ItemDataRole.UserRole, {"type": "group", "group": group_type})
        item.setIcon(0, self._icon_service.get("folder"))
        return item

    def _create_object_item(self, obj_type: str, schema: str, name: str) -> QTreeWidgetItem:
        """Create an object item for the tree.

        Args:
            obj_type: The type of the object.
            schema: The schema name.
            name: The object name.

        Returns:
            QTreeWidgetItem: The created item.
        """
        item = QTreeWidgetItem([f"{schema}.{name}"])
        item.setData(
            0,
            Qt.ItemDataRole.UserRole,
            {"type": obj_type, "schema": schema, "name": name},
        )
        item.setIcon(0, self._icon_service.get(obj_type))
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsDragEnabled)

        # Lazy-load placeholder
        placeholder = QTreeWidgetItem([self._tr(self.TR_COLUMNS_PLACEHOLDER)])
        placeholder.setData(0, Qt.ItemDataRole.UserRole, {"type": "placeholder", "kind": "columns"})
        item.addChild(placeholder)

        return item

    # ==================================================================
    # Lazy loading of columns
    # ==================================================================
    def _on_item_expanded(self, item: QTreeWidgetItem) -> None:
        """Handle item expansion for lazy loading columns."""
        meta = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(meta, dict) or meta.get("type") not in {"table", "view"}:
            return

        # Already expanded?
        if item.childCount() == 0:
            return

        first_child = item.child(0)
        if first_child is None:
            return

        child_meta = first_child.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(child_meta, dict) or child_meta.get("type") != "placeholder":
            self._logger.debug(
                "SchemaController: item expanded ignored (already loaded) (obj=%s.%s)",
                meta.get("schema"),
                meta.get("name"),
            )
            return

        item.takeChild(0)

        schema_name = meta["schema"]
        table_name = meta["name"]

        conn = self._resolve_connection_for_item(item)
        if not conn:
            return

        # Try cache first
        entry = self._schema_mgr.get_cache_for(conn)

        cols: list[dict[str, str]] | None = entry.columns.get((schema_name, table_name)) if entry else None

        if cols is not None:
            self._logger.debug(
                "SchemaController: lazy-load columns from cache (conn=%s, obj=%s.%s, count=%s)",
                conn,
                schema_name,
                table_name,
                fmt_int(len(cols)),
            )
        else:
            self._logger.debug(
                "SchemaController: lazy-load columns from DB (conn=%s, obj=%s.%s)", conn, schema_name, table_name
            )
            try:
                cols = list_columns(conn, schema_name, table_name) or []
            except (
                AttributeError,
                ConnectionError,
                FileNotFoundError,
                IndexError,
                KeyError,
                LookupError,
                OSError,
                RuntimeError,
                TypeError,
                ValueError,
            ) as e:
                self._handle_schema_error(e, conn, self._tr(self.TR_FAILED_TO_LOAD_SCHEMA_STATUS))
                return

            if entry:
                entry.columns[(schema_name, table_name)] = cols

        if cols is None:
            return

        for col in cols:
            colname = col["COLUMN_NAME"]
            dtype = col.get("DATA_TYPE", "")
            nullable = col.get("IS_NULLABLE", "YES")
            txt = f"{colname}  ({dtype}, {'NULL' if nullable == 'YES' else 'NOT NULL'})"

            child = QTreeWidgetItem([txt])
            child.setData(
                0,
                Qt.ItemDataRole.UserRole,
                {
                    "type": "column",
                    "schema": schema_name,
                    "table": table_name,
                    "column": colname,
                    "datatype": dtype,
                    "nullable": nullable,
                },
            )
            child.setIcon(0, self._icon_service.get("column"))
            child.setFlags(child.flags() | Qt.ItemFlag.ItemIsDragEnabled)
            item.addChild(child)

    # ==================================================================
    # Handlers
    # ==================================================================
    def _on_connect_requested(self, item: QTreeWidgetItem) -> None:
        """Handle connect request for a connection node.

        Args:
            item (QTreeWidgetItem): The item representing the connection in the schema tree.
        """
        meta = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(meta, dict):
            return

        self._logger.info(
            "SchemaController: connect requested (connection=%s)",
            meta.get("name"),
        )

        name = meta.get("name")
        if not name:
            return

        try:
            self._connect_connection(str(name))
        except (
            AttributeError,
            ConnectionError,
            FileNotFoundError,
            IndexError,
            KeyError,
            LookupError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ):
            # Error already reported via dialog in load_schema_tree
            # and state reverted in ConnectionController.connect.
            # We catch it here to prevent the UI from crashing.
            self._logger.debug("SchemaController: connect request failed (safely handled)")

    def _on_disconnect_requested(self, item: QTreeWidgetItem) -> None:
        """Handle disconnect request for a connection node.

        Disconnecting clears the schema tree as a side effect.
        Therefore, the QTreeWidgetItem becomes invalid after disconnect.
        Never touch `item` after calling _disconnect_connection().
        """
        meta = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(meta, dict):
            return

        self._logger.info(
            "SchemaController: disconnect requested (connection=%s)",
            meta.get("name"),
        )

        name = meta.get("name")
        if not isinstance(name, str):
            return

        self._disconnect_connection(name)

        # Update UI-node
        item.setIcon(0, self._icon_service.get("disconnected"))

        meta = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(meta, dict):
            item.setData(
                0,
                Qt.ItemDataRole.UserRole,
                {**meta, "connected": False},
            )

        font = item.font(0)
        font.setBold(False)
        item.setFont(0, font)

        item.takeChildren()

    # ==================================================================
    # Context menu
    # ==================================================================
    def _on_connection_context_menu(self, item: QTreeWidgetItem, meta: dict[str, object], pos: QPoint) -> None:
        name_obj = meta.get("name")
        if not isinstance(name_obj, str):
            return
        name = name_obj
        connected = meta.get("connected", False)

        self._logger.debug(
            "SchemaController: context menu requested (type=%s, obj=%s, connected=%s)",
            meta.get("type"),
            name,
            connected,
        )

        menu = QMenu(self._parent)
        header = QAction(name, menu)
        menu.addAction(header)
        header.setEnabled(False)
        menu.addSeparator()

        viewport = self._tree.viewport()
        if viewport is None:
            return

        if connected:
            act_disconnect = menu.addAction(self._tr(self.TR_DISCONNECT))
            chosen = menu.exec(viewport.mapToGlobal(pos))
            if chosen == act_disconnect:
                self._logger.debug("SchemaController: disconnect requested (conn=%s)", name)
                self._on_disconnect_requested(item)
        else:
            act_connect = menu.addAction(self._tr(self.TR_CONNECT))
            chosen = menu.exec(viewport.mapToGlobal(pos))
            if chosen == act_connect:
                self._logger.debug("SchemaController: connect requested (conn=%s)", name)
                self._on_connect_requested(item)

    def _on_column_context_menu(self, item: QTreeWidgetItem, meta: dict[str, object], pos: QPoint) -> None:
        """Handle context menu request for a column node."""
        name_obj = meta.get("column")
        if not isinstance(name_obj, str) or not name_obj:
            return
        name = name_obj

        self._logger.debug(
            "SchemaController: context menu requested (type=%s, obj=%s.%s.%s)",
            meta.get("type"),
            meta.get("schema"),
            meta.get("table"),
            name,
        )

        menu = QMenu(self._parent)
        header = QAction(name, menu)
        menu.addAction(header)
        header.setEnabled(False)

        menu.addSeparator()

        act_distinct = QAction("SELECT DISTINCT", menu)
        menu.addAction(act_distinct)

        viewport = self._tree.viewport()
        if viewport is None:
            return
        chosen = menu.exec(viewport.mapToGlobal(pos))

        if not chosen:
            return

        if chosen == act_distinct:
            self._insert_select_distinct(item, meta)

    def _on_context_menu(self, pos: QPoint) -> None:
        """Handle context menu request."""
        item = self._tree.itemAt(pos)
        if not item:
            return

        meta = item.data(0, Qt.ItemDataRole.UserRole)

        if not isinstance(meta, dict):
            return

        meta_type = meta.get("type")

        if meta_type in ("database", "group"):
            return

        if isinstance(meta, dict) and meta_type == "column":
            self._on_column_context_menu(item, meta, pos)
            return

        name = meta.get("name")
        if not isinstance(name, str) or not name:
            return

        if isinstance(meta, dict) and meta_type == "connection":
            self._on_connection_context_menu(item, meta, pos)
            return

        self._logger.debug(
            "SchemaController: context menu requested (type=%s, obj=%s.%s)",
            meta.get("type"),
            meta.get("schema"),
            meta.get("name"),
        )

        menu = QMenu(self._parent)
        header = QAction(name, menu)
        menu.addAction(header)
        header.setEnabled(False)
        menu.addSeparator()
        if self._gen_top_n == 0:
            # No limit -> do not show TOP / LIMIT
            act_star = menu.addAction("SELECT *")
            act_cols = menu.addAction("SELECT")
            act_cols_schema = menu.addAction("SELECT (schema)")
        else:
            top_n = fmt_int(self._gen_top_n) if self._gen_top_n > 1000 else self._gen_top_n
            act_star = menu.addAction(f"SELECT * TOP {top_n}")
            act_cols = menu.addAction(f"SELECT TOP {top_n}")
            act_cols_schema = menu.addAction(f"SELECT TOP {top_n} (schema)")

        viewport = self._tree.viewport()
        if viewport is None:
            return
        chosen = menu.exec(viewport.mapToGlobal(pos))
        if not chosen:
            return

        if chosen == act_star:
            self._logger.debug(
                "SchemaController: context menu choice: SELECT * TOP (obj=%s.%s)", meta.get("schema"), meta.get("name")
            )
            self._insert_select_star(item, meta)
        elif chosen == act_cols:
            self._logger.debug(
                "SchemaController: context menu choice: SELECT TOP (obj=%s.%s)", meta.get("schema"), meta.get("name")
            )
            self._insert_select_columns(item, meta, with_schema=False)
        elif chosen == act_cols_schema:
            self._logger.debug(
                "SchemaController: context menu choice: SELECT TOP (schema) (obj=%s.%s)",
                meta.get("schema"),
                meta.get("name"),
            )
            self._insert_select_columns(item, meta, with_schema=True)

    # ==================================================================
    # Error & state
    # ==================================================================

    def _handle_schema_error(self, e: Exception, connection_name: str, status_text: str) -> None:
        """Handle schema loading error by logging and showing a dialog.

        Args:
            e: The exception.
            connection_name: The connection name.
            status_text: The status text to show.
        """
        self._logger.error("SchemaController: failure (conn=%s): %s", connection_name, e)

        self._reset_connection_state(connection_name)

        # Translate message for UI (supports combined msg + hint from service.py)
        raw_err = str(e)
        if "\n\n" in raw_err:
            parts = raw_err.split("\n\n", 1)
            translated = f"{tr('DbErrors', parts[0])}\n\n{tr('DbErrors', parts[1])}"
        else:
            translated = tr("DbErrors", raw_err)

        text = self._tr_fmt(self.TR_COULD_NOT_LOAD_SCHEMA, error=translated)
        self._dialogs.critical(parent=self._parent, title=self._tr(self.TR_FAILURE), text=text)
        self._set_status(status_text, 6000)

    def _reset_connection_state(self, connection_name: str) -> None:
        """Force reset of connection-related state after failure.

        Ensures no async jobs or UI states remain active.
        """
        try:
            self._logger.debug("SchemaController: resetting connection state (conn=%s)", connection_name)

            # 1. Disconnect backend connection
            try:
                self._disconnect_connection(connection_name)
            except (
                AttributeError,
                ConnectionError,
                FileNotFoundError,
                IndexError,
                KeyError,
                LookupError,
                OSError,
                RuntimeError,
                TypeError,
                ValueError,
            ):
                self._logger.debug("SchemaController: disconnect failed during reset (ignored)", exc_info=True)

            # 2. Cancel jobs for this scope (if you support this)
            try:
                if hasattr(self._job_mgr, "cancel_scope"):
                    self._job_mgr.cancel_scope(f"load:{connection_name}")
            except (
                AttributeError,
                ConnectionError,
                FileNotFoundError,
                IndexError,
                KeyError,
                LookupError,
                OSError,
                RuntimeError,
                TypeError,
                ValueError,
            ):
                self._logger.debug("SchemaController: job cancel failed (ignored)", exc_info=True)

            # 3. Reset UI node
            for i in range(self._tree.topLevelItemCount()):
                item = self._tree.topLevelItem(i)
                if not item:
                    continue

                meta = item.data(0, Qt.ItemDataRole.UserRole)
                if isinstance(meta, dict) and meta.get("name") == connection_name:
                    item.setData(
                        0,
                        Qt.ItemDataRole.UserRole,
                        {**meta, "connected": False},
                    )
                    item.setIcon(0, self._icon_service.get("disconnected"))

                    font = item.font(0)
                    font.setBold(False)
                    item.setFont(0, font)

                    item.takeChildren()
                    break

            # 4. (Optional) clear schema cache
            try:
                if hasattr(self._schema_mgr, "invalidate"):
                    self._schema_mgr.invalidate(connection_name)
            except (
                AttributeError,
                ConnectionError,
                FileNotFoundError,
                IndexError,
                KeyError,
                LookupError,
                OSError,
                RuntimeError,
                TypeError,
                ValueError,
            ):
                self._logger.debug("SchemaController: cache invalidate failed (ignored)", exc_info=True)

        except (
            AttributeError,
            ConnectionError,
            FileNotFoundError,
            IndexError,
            KeyError,
            LookupError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ):
            self._logger.exception("SchemaController: failed to reset connection state")

    # ==================================================================
    # Double-click
    # ==================================================================

    def _on_item_double_clicked(self, item: QTreeWidgetItem) -> None:
        """Handle item double-click."""
        meta = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(meta, dict):
            return

        node_type = meta.get("type")

        if node_type not in {"table", "view", "column"}:
            return

        if node_type == "column":
            self._insert_select_distinct(item, meta)

        else:
            self._logger.debug(
                "SchemaController: double-click object (type=%s, obj=%s.%s)",
                meta.get("type"),
                meta.get("schema"),
                meta.get("name"),
            )
            self._insert_select_columns(item, meta, with_schema=False)

    # ==================================================================
    # SQL generation
    # ==================================================================
    def _insert_select_distinct(self, item: QTreeWidgetItem, meta: dict[str, object]) -> None:
        """Insert SELECT DISTINCT statement into tab."""
        schema = meta.get("schema")
        table = meta.get("table")
        column = meta.get("column")
        if not isinstance(schema, str) or not isinstance(table, str) or not isinstance(column, str):
            return

        self._logger.debug(
            "SchemaController: insert select distinct values requested (obj=%s.%s, col=%s)", schema, table, column
        )

        conn = self._resolve_connection_for_item(item)
        if not conn:
            return

        tab = self._create_tab_for_connection(conn)

        if not tab:
            return

        sql = build_select_distinct(conn, schema, table, column)

        self._insert_sql_into_tab(tab, sql)

    def _insert_select_star(self, item: QTreeWidgetItem, meta: dict[str, object]) -> None:
        """Insert SELECT * SQL snippet."""
        schema = meta.get("schema")
        name = meta.get("name")
        if not isinstance(schema, str) or not isinstance(name, str):
            return

        conn = self._resolve_connection_for_item(item)

        if not conn:
            return

        tab = self._create_tab_for_connection(conn)

        if not tab:
            return

        top_label = self._gen_top_n if self._gen_top_n != 0 else "no limit"
        self._logger.debug(
            "SchemaController: generating SELECT * (conn=%s, obj=%s.%s, top_n=%s)",
            conn,
            schema,
            name,
            top_label,
        )

        sql = build_select_star(conn, schema, name, top_n=self._gen_top_n)

        self._insert_sql_into_tab(tab, sql)

    def _insert_select_columns(self, item: QTreeWidgetItem, meta: dict[str, object], with_schema: bool) -> None:
        """Insert SELECT columns SQL snippet.

        Args:
            item: The tree item for which to generate SQL.
            meta: Metadata dictionary.
            with_schema: Whether to include schema in SQL.
        """
        corr_id = uuid.uuid4().hex
        schema = meta.get("schema")
        name = meta.get("name")
        if not isinstance(schema, str) or not isinstance(name, str):
            return

        conn = self._resolve_connection_for_item(item)

        if not conn:
            return

        tab = self._create_tab_for_connection(conn)

        if not tab:
            return

        top_label = self._gen_top_n if self._gen_top_n != 0 else "no limit"
        self._logger.debug(
            "SchemaController: generating SELECT TOP (conn=%s, obj=%s.%s, top_n=%s, with_schema=%s, corr=%s)",
            conn,
            schema,
            name,
            top_label,
            with_schema,
            corr_id,
        )
        sql = build_select_columns_auto(
            conn,
            schema,
            name,
            top_n=self._gen_top_n,
            with_schema=with_schema,
            corr_id=corr_id,
        )

        self._insert_sql_into_tab(tab, sql)

    def _resolve_connection_for_item(self, item: QTreeWidgetItem) -> str | None:
        """Walk up tree to find owning connection."""
        current: QTreeWidgetItem | None = item
        while current is not None:
            meta = current.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(meta, dict) and meta.get("type") == "connection":
                name = meta.get("name")
                return name if isinstance(name, str) else None
            current = current.parent()
        return None

    # ==================================================================
    # Prefetch progress
    # ==================================================================

    def on_schema_progress(self, done: int, total: int) -> None:
        """Handle schema prefetch progress.

        Args:
            done: Number of items done.
            total: Total number of items.

        Returns:
            None
        """
        ui_invoke(self._on_schema_progress_ui, done, total)

    def _on_schema_progress_ui(self, done: int, total: int) -> None:
        """Update UI for schema progress.

        Args:
            done: Number of items done.
            total: Total number of items.
        """
        if total > 1:
            self._logger.debug("SchemaController: schema prefetch progress: %s/%s", done, total)
            self._set_status(self._tr_fmt(self.TR_PRELOADING_SCHEMA_STATUS, done=str(done), total=str(total)), 1500)
        else:
            self._restore_baseline_status()

    # UI language
    def retranslate_ui(self) -> None:
        """Update translatable UI texts for language changes."""
        for i in range(self._tree.topLevelItemCount()):
            conn_item = self._tree.topLevelItem(i)
            if not conn_item:
                continue

            conn_meta = conn_item.data(0, Qt.ItemDataRole.UserRole)
            if not isinstance(conn_meta, dict) or conn_meta.get("type") != "connection":
                continue

            # Connection name is data, not translated
            conn_name = conn_meta.get("name")
            conn_item.setText(0, conn_name if isinstance(conn_name, str) else "")

            # Database node (if connected)
            if conn_item.childCount() == 0:
                continue

            db_item = conn_item.child(0)
            if db_item is None:
                continue
            db_meta = db_item.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(db_meta, dict) and db_meta.get("type") == "database":
                db_name = db_meta.get("name")
                db_item.setText(0, db_name if isinstance(db_name, str) else "")

                # Translate groups and placeholders under database
                for gi in range(db_item.childCount()):
                    group = db_item.child(gi)
                    if not group:
                        continue

                    group_meta = group.data(0, Qt.ItemDataRole.UserRole)
                    if not isinstance(group_meta, dict):
                        continue

                    if group_meta.get("type") == "group":
                        if group_meta.get("group") == "tables":
                            group.setText(0, self._tr(self.TR_TABLES_GROUP))
                        elif group_meta.get("group") == "views":
                            group.setText(0, self._tr(self.TR_VIEWS_GROUP))

                    # Placeholders under tables/views
                    for oi in range(group.childCount()):
                        obj = group.child(oi)
                        if not obj:
                            continue

                        obj_meta = obj.data(0, Qt.ItemDataRole.UserRole)
                        if isinstance(obj_meta, dict) and obj_meta.get("type") == "placeholder":
                            obj.setText(0, self._tr(self.TR_COLUMNS_PLACEHOLDER))
