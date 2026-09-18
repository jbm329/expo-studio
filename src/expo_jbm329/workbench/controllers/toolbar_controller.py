"""Toolbar controller for managing toolbar actions in the Expo application.

This module provides the ToolbarController class, which builds and manages
all toolbar actions and their wiring to command callbacks. It encapsulates
toolbar UI logic, keeping the main application window free from Qt boilerplate
while maintaining full testability through dependency injection.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import QT_TR_NOOP
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QToolBar, QWidget

from expo_jbm329.utils.i18n_utils import tr

if TYPE_CHECKING:
    from collections.abc import Callable


class ToolbarController:
    """Controller for managing toolbar actions in the Expo application.

    This class builds and owns all toolbar actions, ensuring no parent coupling
    and no business logic. All command callbacks are injected by ExpoStudio.
    """
    # --- i18n markers (pylupdate6-visible) -----------------------------
    TR_NEW = QT_TR_NOOP("New file")
    TR_OPEN = QT_TR_NOOP("Open")
    TR_SAVE = QT_TR_NOOP("Save")
    TR_RUN_QUERY = QT_TR_NOOP("Run query")
    TR_RUN_QUERY_SHORTCUT = QT_TR_NOOP("Run the query\nShortcut: Ctrl+Enter")
    TR_RUN_SELECTION = QT_TR_NOOP("Run selection")
    TR_RUN_SELECTION_SHORTCUT = QT_TR_NOOP("Run selected text\nShortcut: Ctrl+Alt+Shift+Enter")
    TR_RUN_TOP10 = QT_TR_NOOP("Run top 10")
    TR_RUN_TOP10_SHORTCUT = QT_TR_NOOP("Run top 10\nShortcut: Ctrl+Shift+Enter")
    TR_CANCEL_JOB = QT_TR_NOOP("Cancel job")
    TR_EXPORT_CSV = QT_TR_NOOP("Export to CSV")
    TR_EXPORT_EXCEL = QT_TR_NOOP("Export to Excel")
    TR_EXPORT_DATA = QT_TR_NOOP("Export to data file")
    TR_JOIN_DATASETS = QT_TR_NOOP("Join datasets")
    TR_CONCATENATE_DATASETS = QT_TR_NOOP("Concatenate datasets")
    TR_FROMAT_VIEW = QT_TR_NOOP("Format view")
    TR_CLEAR_EDITOR = QT_TR_NOOP("Clear editor")
    TR_UPDATE_SCHEMA = QT_TR_NOOP("Update schema")
    TR_UPDATE_SCHEMA_SHORTCUT = QT_TR_NOOP("Update schema\nShortcut: F5")
    TR_UNDO = QT_TR_NOOP("Undo")
    TR_UNDO_SHORTCUT = QT_TR_NOOP("Undo last action\nShortcut: Ctrl+Z")
    TR_VISUALIZE = QT_TR_NOOP("Visualize data")

    # File
    _action_new: QAction
    _action_open: QAction
    _action_save: QAction

    # Query
    _action_run_full: QAction
    _action_run_selfull: QAction
    _action_run10: QAction
    _action_cancel_job: QAction

    # Export
    _action_export_csv: QAction
    _action_export_excel: QAction
    _action_export_data: QAction

    # Data ops
    _action_join_data: QAction
    _action_concatenate_data: QAction
    _action_visualize: QAction

    # Misc
    _action_format_view: QAction
    _action_clear: QAction
    _action_refresh_schema: QAction
    _action_undo: QAction

    @staticmethod
    def _tr(text: str) -> str:
        return tr("ToolbarController", text)

    def __init__(
        self,
        icon_service,
        *,
        new_file: Callable[[], None],
        open_file: Callable[[], None],
        save_file: Callable[[], None],
        run_full: Callable[[], None],
        run_selfull: Callable[[], None],
        run_top10: Callable[[], None],
        cancel_job: Callable[[], None],
        export_csv: Callable[[], None],
        export_excel: Callable[[], None],
        export_data: Callable[[], None],
        join_data: Callable[[], None],
        concatenate_data: Callable[[], None],
        format_view: Callable[[bool], None],
        clear_editor: Callable[[], None],
        refresh_schema: Callable[[], None],
        undo: Callable[[], None],
        visualize_data: Callable[[], None],
        logger: logging.Logger | None = None,
    ):
        """Initialize the ToolbarController.

        Args:
            icon_service: Service for providing icons.
            new_file: Callback for new file action.
            open_file: Callback for open file action.
            save_file: Callback for save file action.
            run_full: Callback for run full query action.
            run_selfull: Callback for run selected query action.
            run_top10: Callback for run top 10 action.
            cancel_job: Callback for cancel job action.
            export_csv: Callback for export to CSV action.
            export_excel: Callback for export to Excel action.
            export_data: Callback for export to data file action.
            join_data: Callback for join data action.
            concatenate_data: Callback for concatenate data action.
            format_view: Callback for format view action.
            clear_editor: Callback for clear editor action.
            refresh_schema: Callback for refresh schema action.
            undo: Callback for undo action.
            visualize_data: Callback for visualize data action.
            logger: Optional logger instance.
        """
        self._icons = icon_service

        # Actions
        self.toolbar: QToolBar | None = None
        self._action_new_cb = new_file
        self._action_open_cb = open_file
        self._action_save_cb = save_file
        self._action_run_full_cb = run_full
        self._action_run_selfull_cb = run_selfull
        self._action_run10_cb = run_top10
        self._action_cancel_job_cb = cancel_job
        self._action_export_csv_cb = export_csv
        self._action_export_excel_cb = export_excel
        self._action_export_data_cb = export_data
        self._action_join_data_cb = join_data
        self._action_concatenate_data_cb = concatenate_data
        self._action_format_view_cb = format_view
        self._action_clear_cb = clear_editor
        self._action_refresh_schema_cb = refresh_schema
        self._action_undo_cb = undo
        self._action_visualize_cb = visualize_data
        self._logger = logger or logging.getLogger("applogger.ui")

    # ------------------------------------------------------------------
    def build(self, parent: QWidget) -> QToolBar:
        """Build the toolbar UI.

        Parent is injected at composition time (ExpoStudio),
        making this controller UI-agnostic and fully testable.

        Args:
            parent: The parent widget for the toolbar.

        Returns:
            QToolBar: The constructed toolbar.
        """
        tb = QToolBar("Verktygsrad", parent)
        tb.setMovable(False)
        self.toolbar = tb

        # FILE
        self._action_new = QAction(self._tr(self.TR_NEW), tb)
        tb.addAction(self._action_new)

        self._action_open = QAction(self._tr(self.TR_OPEN), tb)
        tb.addAction(self._action_open)

        self._action_save = QAction(self._tr(self.TR_SAVE), tb)
        tb.addAction(self._action_save)

        tb.addSeparator()

        # QUERY EXECUTION
        self._action_run_full = QAction(self._tr(self.TR_RUN_QUERY), tb)
        self._action_run_full.setShortcuts(["Ctrl+Return", "Ctrl+Enter"])
        self._action_run_full.setToolTip(self._tr(self.TR_RUN_QUERY_SHORTCUT))
        tb.addAction(self._action_run_full)

        self._action_run_selfull = QAction(self._tr(self.TR_RUN_SELECTION), tb)
        self._action_run_selfull.setShortcuts(["Ctrl+Alt+Shift+Return", "Ctrl+Alt+Shift+Enter"])
        self._action_run_selfull.setToolTip(self._tr(self.TR_RUN_SELECTION_SHORTCUT))
        tb.addAction(self._action_run_selfull)

        self._action_run10 = QAction(self._tr(self.TR_RUN_TOP10), tb)
        self._action_run10.setShortcuts(["Ctrl+Shift+Return", "Ctrl+Shift+Enter"])
        self._action_run10.setToolTip(self._tr(self.TR_RUN_TOP10_SHORTCUT))
        tb.addAction(self._action_run10)

        self._action_cancel_job = QAction(self._tr(self.TR_CANCEL_JOB), tb)
        tb.addAction(self._action_cancel_job)

        tb.addSeparator()

        # EXPORT
        self._action_export_csv = QAction(self._tr(self.TR_EXPORT_CSV), tb)
        tb.addAction(self._action_export_csv)

        self._action_export_excel = QAction(self._tr(self.TR_EXPORT_EXCEL), tb)
        tb.addAction(self._action_export_excel)

        self._action_export_data = QAction(self._tr(self.TR_EXPORT_DATA), tb)
        tb.addAction(self._action_export_data)

        tb.addSeparator()

        # DATA OPS
        self._action_join_data = QAction(self._tr(self.TR_JOIN_DATASETS), tb)
        self._action_join_data.setEnabled(False)
        tb.addAction(self._action_join_data)

        self._action_concatenate_data = QAction(self._tr(self.TR_CONCATENATE_DATASETS), tb)
        self._action_concatenate_data.setEnabled(False)
        tb.addAction(self._action_concatenate_data)

        self._action_visualize = QAction(self._tr(self.TR_VISUALIZE), tb)
        self._action_visualize.setEnabled(False)
        tb.addAction(self._action_visualize)

        tb.addSeparator()

        # CLEAR / REFRESH / UNDO
        self._action_clear = QAction(self._tr(self.TR_CLEAR_EDITOR), tb)
        tb.addAction(self._action_clear)

        self._action_refresh_schema = QAction(self._tr(self.TR_UPDATE_SCHEMA), tb)
        self._action_refresh_schema.setShortcut("F5")
        self._action_refresh_schema.setToolTip(self._tr(self.TR_UPDATE_SCHEMA_SHORTCUT))
        self._action_refresh_schema.setEnabled(False)
        tb.addAction(self._action_refresh_schema)

        self._action_undo = QAction(self._tr(self.TR_UNDO), tb)
        self._action_undo.setShortcut("Ctrl+Z")
        self._action_undo.setToolTip(self._tr(self.TR_UNDO_SHORTCUT))
        self._action_undo.setEnabled(False)
        tb.addAction(self._action_undo)

        tb.addSeparator()

        # Format
        self._action_format_view = QAction(self._tr(self.TR_FROMAT_VIEW), tb)
        self._action_format_view.setCheckable(True)
        tb.addAction(self._action_format_view)

        self._connect_callbacks()
        self.apply_icons()

        return tb

    # ------------------------------------------------------------------

    def _connect_callbacks(self):
        """Connect all toolbar actions to their respective callbacks."""
        self._action_new.triggered.connect(self._action_new_cb)
        self._action_open.triggered.connect(self._action_open_cb)
        self._action_save.triggered.connect(self._action_save_cb)

        self._action_run_full.triggered.connect(self._action_run_full_cb)
        self._action_run_selfull.triggered.connect(self._action_run_selfull_cb)
        self._action_run10.triggered.connect(self._action_run10_cb)
        self._action_cancel_job.triggered.connect(self._action_cancel_job_cb)

        self._action_export_csv.triggered.connect(self._action_export_csv_cb)
        self._action_export_excel.triggered.connect(self._action_export_excel_cb)
        self._action_export_data.triggered.connect(self._action_export_data_cb)

        self._action_join_data.triggered.connect(self._action_join_data_cb)
        self._action_concatenate_data.triggered.connect(self._action_concatenate_data_cb)
        self._action_visualize.triggered.connect(self._action_visualize_cb)

        self._action_clear.triggered.connect(self._action_clear_cb)
        self._action_refresh_schema.triggered.connect(self._action_refresh_schema_cb)
        self._action_undo.triggered.connect(self._action_undo_cb)

        self._action_format_view.triggered.connect(self._action_format_view_cb)

    # ------------------------------------------------------------------

    def apply_icons(self):
        """Apply icons to all toolbar actions using the icon service."""
        self._action_new.setIcon(self._icons.get("file_new"))
        self._action_open.setIcon(self._icons.get("folder_open"))
        self._action_save.setIcon(self._icons.get("save"))

        self._action_run_full.setIcon(self._icons.get("run"))
        self._action_run_selfull.setIcon(self._icons.get("run_selected"))
        self._action_run10.setIcon(self._icons.get("run_10"))
        self._action_cancel_job.setIcon(self._icons.get("stop"))

        self._action_export_csv.setIcon(self._icons.get("csv_export"))
        self._action_export_excel.setIcon(self._icons.get("excel_export"))
        self._action_export_data.setIcon(self._icons.get("binary_export"))

        self._action_join_data.setIcon(self._icons.get("join"))
        self._action_concatenate_data.setIcon(self._icons.get("concatenate"))
        self._action_visualize.setIcon(self._icons.get("chart"))

        self._action_clear.setIcon(self._icons.get("file_clear"))
        self._action_refresh_schema.setIcon(self._icons.get("refresh"))
        self._action_undo.setIcon(self._icons.get("undo"))

        self._action_format_view.setIcon(self._icons.get("format"))

    # ------------------------------------------------------------------
    def apply_connection_state(self, has_conn: bool) -> None:
        """Apply the connection state to enable/disable relevant actions.

        Args:
            has_conn: Whether there is a database connection.
        """
        self._action_run_full.setEnabled(has_conn)
        self._action_run_selfull.setEnabled(has_conn)
        self._action_run10.setEnabled(has_conn)
        self._action_refresh_schema.setEnabled(has_conn)

    # ------------------------------------------------------------------
    def set_undo_enabled(self, enabled: bool) -> None:
        """Set the enabled state of the undo action.

        Args:
            enabled: Whether to enable the undo action.
        """
        self._action_undo.setEnabled(enabled)

    # ------------------------------------------------------------------
    def apply_has_data_state(self, has_data: bool) -> None:
        """Apply the data state to enable/disable export actions.

        Args:
            has_data: Whether there is data in the current tab.
        """
        self._action_export_csv.setEnabled(has_data)
        self._action_export_excel.setEnabled(has_data)
        self._action_export_data.setEnabled(has_data)
        self._action_visualize.setEnabled(has_data)

    def apply_has_multiple_datasets_state(self, has_multiple_datasets: bool) -> None:
        """Apply the multiple datasets state to enable/disable join/concatenate actions.

        Args:
            has_multiple_datasets: Whether there are multiple datasets.
        """
        self._action_join_data.setEnabled(has_multiple_datasets)
        self._action_concatenate_data.setEnabled(has_multiple_datasets)

    def retranslate_ui(self) -> None:
        """Update all action texts for localization."""
        self._action_open.setText(self._tr(self.TR_OPEN))
        self._action_save.setText(self._tr(self.TR_SAVE))

        self._action_run_full.setText(self._tr(self.TR_RUN_QUERY))
        self._action_run_full.setToolTip(self._tr(self.TR_RUN_QUERY_SHORTCUT))

        self._action_run_selfull.setText(self._tr(self.TR_RUN_SELECTION))
        self._action_run_selfull.setToolTip(self._tr(self.TR_RUN_SELECTION_SHORTCUT))

        self._action_run10.setText(self._tr(self.TR_RUN_TOP10))
        self._action_run10.setToolTip(self._tr(self.TR_RUN_TOP10_SHORTCUT))

        self._action_export_csv.setText(self._tr(self.TR_EXPORT_CSV))
        self._action_export_excel.setText(self._tr(self.TR_EXPORT_EXCEL))
        self._action_export_data.setText(self._tr(self.TR_EXPORT_DATA))

        self._action_join_data.setText(self._tr(self.TR_JOIN_DATASETS))
        self._action_concatenate_data.setText(self._tr(self.TR_CONCATENATE_DATASETS))
        self._action_visualize.setText(self._tr(self.TR_VISUALIZE))

        self._action_clear.setText(self._tr(self.TR_CLEAR_EDITOR))
        self._action_refresh_schema.setText(self._tr(self.TR_UPDATE_SCHEMA))
        self._action_refresh_schema.setToolTip(self._tr(self.TR_UPDATE_SCHEMA_SHORTCUT))
        self._action_undo.setText(self._tr(self.TR_UNDO))
        self._action_undo.setToolTip(self._tr(self.TR_UNDO_SHORTCUT))

        self._action_format_view.setText(self._tr(self.TR_FROMAT_VIEW))
