"""Main entry point and main window for the Expo Studio application.

This module contains the `ExpoStudio` class, which serves as the primary
user interface for the application. It integrates various workbench components
including the SQL editor, schema browser, file explorer, and results view.
The application logic is decoupled into controllers and services.

Language Policy:
- UI Strings (menus, dialogs, labels): Swedish.
- Documentation and Comments: English.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, cast, override

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QDockWidget,
    QMainWindow,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from expo_jbm329.app.app_services import AppServices
from expo_jbm329.app.settings.config_store import load_settings
from expo_jbm329.app.settings.connection_editor import ConnectionEditor
from expo_jbm329.app.settings.log_config_editor import LogConfigEditor
from expo_jbm329.app.settings.rest_connection_editor import RestConnectionEditor
from expo_jbm329.app.settings.settings_editor import SettingsEditor
from expo_jbm329.db.base import close_all_connections
from expo_jbm329.gui.dialogs.about_dialog import AboutDialog
from expo_jbm329.gui.widgets.file_tree_widget import FileTreeWidget
from expo_jbm329.gui.widgets.rest_tree_widget import RestTreeWidget
from expo_jbm329.gui.widgets.schema_tree_widget import SchemaTreeWidget
from expo_jbm329.utils.path_manager import (
    ensure_all_dirs,
    get_documents_dir,
)
from expo_jbm329.workbench.controllers.menu_controller import MenuController
from expo_jbm329.workbench.controllers.status_bar_controller import StatusBarController
from expo_jbm329.workbench.controllers.toolbar_controller import ToolbarController
from expo_jbm329.workbench.ui_refs import WorkbenchUIRefs
from expo_jbm329.workbench.workbench_services import WorkbenchServices

if TYPE_CHECKING:
    from PyQt6.QtGui import QCloseEvent


# ======================================================================
#  SqlEditor Main Window
# ======================================================================
class ExpoStudio(QMainWindow):
    """Main window for the Expo Studio application.

    This class represents the primary user interface window of the Expo Studio SQL
    editor application. It hosts a comprehensive workbench environment including a
    SQL editor, database schema browser, file explorer, result tabs, connection
    selector, toolbar, and status bar. The window is built using PyQt6 and follows
    a modular architecture with separate controllers and services for maintainability.

    The UI layout consists of:
    - Left dock panels: Database schema tree and file browser.
    - Central area: SQL editor and result tabs in a splitter layout.
    - Top toolbar: Quick access to common actions.
    - Status bar: Displays application status and messages.
    - Menu bar: Full menu system for application features.

    Attributes:
        settings: Application settings loaded from configuration.
        services: Backend services instance for dialogs, logging, etc.
        workbench_services: Workbench-specific services for queries, exports, etc.
        ui_logger: Logger for UI-related messages.
        result_tabs: QTabWidget for displaying query results.
        schema_tree: SchemaTreeWidget for database schema navigation.
        files_tree: QTreeView for file system browsing.
        files_model: QFileSystemModel for file system data.
        statusbar: QStatusBar for status messages.
        _toolbar: QToolBar for action buttons.
        connection_controller: Manages database connections.
        editor_controller: Handles editor interactions.
        toolbar_controller: Controls toolbar state and actions.
        status_controller: Manages status bar updates.
        menu_controller: Handles menu bar functionality.

    Notes:
        - All docstrings and comments are in English.
        - User-facing strings (menus, dialogs, labels) are in Swedish.
        - The window uses a two-phase initialization: UI construction in __init__,
          service initialization in init_services().
    """

    # ------------------------------------------------------------------
    # Constructor & Initialization
    # ------------------------------------------------------------------
    def __init__(self, parent=None) -> None:
        """Initialize the main window."""
        super().__init__(parent)
        # -----------------------------------------------------------
        # Window basics and settings
        # -----------------------------------------------------------
        self.setWindowTitle(self.tr("Expo studio"))
        self.resize(1280, 900)
        self.settings = load_settings()
        ensure_all_dirs(self.settings)

        # -------------------------------------------
        # Build raw UI widgets
        # -------------------------------------------
        self._build_central_widget()
        self._build_schema_dock()
        self._build_files_dock()
        self._build_rest_dock()
        self._build_editor_and_tabs()

        # -------------------------------------------
        # Init attributes
        # -------------------------------------------

        self._allow_close = False
        self._shutdown_in_progress = False
        self._shutdown_deadline_monotonic: float | None = None
        self._shutdown_timeout_logged = False

        self.services = None
        self.workbench_services = None
        self.ui_logger = None
        self._dialogs = None
        self._file_dialogs = None
        self.editor_controller = None
        self.statusbar = None
        self.status_controller = None
        self.menu_controller = None
        self._toolbar = None
        self.toolbar_controller = None
        self.connection_controller = None

    # ==================================================================
    # UI Construction
    # ==================================================================
    def _build_central_widget(self) -> None:
        """Builds central splitter layout for docks + workbench."""
        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setCentralWidget(central)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        layout.addWidget(splitter, 1)

        self._central_layout = layout
        self._splitter = splitter

    def _build_schema_dock(self) -> None:
        """Builds left dock containing the schema tree."""
        self.schema_tree = SchemaTreeWidget(self)

        dock = QDockWidget(self.tr("Database connections"), self)
        dock.setObjectName("Dock_Databas")
        dock.setWidget(self.schema_tree)
        dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea)

        features = QDockWidget.DockWidgetFeature.DockWidgetMovable
        features |= QDockWidget.DockWidgetFeature.DockWidgetFloatable
        dock.setFeatures(features)

        dock.setMinimumWidth(300)

        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        self._schema_dock = dock

    def _build_files_dock(self) -> None:
        """Builds file browser dock below schema panel."""
        self.files_tree = FileTreeWidget(self)
        self.files_model = self.files_tree.model

        root_dir = str(get_documents_dir(self.settings))
        root_index = self.files_model.index(root_dir)
        self.files_tree.setRootIndex(root_index)

        dock = QDockWidget(self.tr("Files"), self)
        dock.setObjectName("Dock_Filer")
        dock.setWidget(self.files_tree)
        dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea)

        features = QDockWidget.DockWidgetFeature.DockWidgetMovable
        features |= QDockWidget.DockWidgetFeature.DockWidgetFloatable
        dock.setFeatures(features)

        dock.setMinimumWidth(300)

        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        self.splitDockWidget(self._schema_dock, dock, Qt.Orientation.Vertical)
        self.resizeDocks([self._schema_dock, dock], [3, 1], Qt.Orientation.Vertical)
        self._files_dock = dock

    def _build_rest_dock(self) -> None:
        """Builds REST API connections dock below files panel."""
        self.rest_tree = RestTreeWidget(self)

        dock = QDockWidget(self.tr("REST connections"), self)
        dock.setObjectName("Dock_REST")
        dock.setWidget(self.rest_tree)
        dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea)

        features = QDockWidget.DockWidgetFeature.DockWidgetMovable
        features |= QDockWidget.DockWidgetFeature.DockWidgetFloatable
        dock.setFeatures(features)

        dock.setMinimumWidth(300)

        # Stack REST dock under Files dock
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        self.splitDockWidget(self._files_dock, dock, Qt.Orientation.Vertical)

        # Optional: adjust relative sizes (Schema : Files : REST)
        self.resizeDocks(
            [self._schema_dock, self._files_dock, dock],
            [6, 2, 2],
            Qt.Orientation.Vertical,
        )
        self._rest_dock = dock

    def _build_editor_and_tabs(self) -> None:
        """Builds the SQL workbench editor/result area with a movable splitter."""
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Vertical splitter between editor and results
        splitter = QSplitter(Qt.Orientation.Vertical, container)

        # Editor tabs (top)
        self.editor_tabs = QTabWidget(container)
        splitter.addWidget(self.editor_tabs)

        # Result tabs (bottom)
        self.result_tabs = QTabWidget(container)
        splitter.addWidget(self.result_tabs)

        # Initial stretch (editor smaller than results)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)

        layout.addWidget(splitter)
        self._splitter.addWidget(container)
        self._splitter.setStretchFactor(0, 1)

    # ==================================================================
    # Init services and controllers
    # ==================================================================
    def init_services(self):
        """Initializes services."""
        # -------------------------------------------
        # Status bar + controller (Must be before backend services to provide status_cb)
        # -------------------------------------------
        self.statusbar = self.statusBar()
        if isinstance(self.statusbar, QStatusBar):
            self.status_controller = StatusBarController(self, self.statusbar)

        # -------------------------------------------
        # Backend services
        # -------------------------------------------
        self.services = AppServices.build(self.settings)
        self.ui_logger = self.services.log_ui

        # -------------------------------------------
        # Dialogs
        # -------------------------------------------
        self._dialogs = self.services.dialogs
        self._file_dialogs = self.services.file_dialogs

        # -------------------------------------------
        # Workbench services
        # -------------------------------------------
        ui_refs = WorkbenchUIRefs(
            parent=self,
            result_tabs=self.result_tabs,
            editor_tabs=self.editor_tabs,
            schema_tree=self.schema_tree,
            files_tree=self.files_tree,
            rest_tree=self.rest_tree,
            files_model=self.files_model,
            set_status=self.status_controller.set_status,
            open_rest_connection_dialog=self.open_rest_connection_dialog,
            restore_status=self.status_controller.restore_baseline,
            set_shape=self.status_controller.set_shape_status,
            update_undo_enabled=self.update_undo_enabled,
        )

        self.workbench_services = WorkbenchServices.build(self.services, ui_refs, self.services.settings_service)

        # -------------------------------------------
        # Connection controller
        # -------------------------------------------
        self.connection_controller = self.workbench_services.connections

        # -------------------------------------------
        # Toolbar controller
        # -------------------------------------------
        self.toolbar_controller = ToolbarController(
            icon_service=self.workbench_services.icon_service,
            new_file=self.workbench_services.editor_panel.new_file,
            open_file=self.workbench_services.document.open_any_dialog,
            save_file=self.workbench_services.document.save_sql,
            run_full=self.workbench_services.query.run_full,
            run_selfull=lambda: self.workbench_services.query.run_selection(None),
            run_top10=self.workbench_services.query.run_top10,
            cancel_job=self._cancel_all_jobs_from_toolbar,
            export_csv=self.workbench_services.export.export_csv,
            export_excel=self.workbench_services.export.export_excel,
            export_data=self.workbench_services.export.export_data,
            join_data=lambda: self.workbench_services.join.open_join_dialog(),
            concatenate_data=lambda: self.workbench_services.concat.open_concat_dialog(),
            format_view=self.workbench_services.results.handle_format_view_toggle,
            clear_editor=self.workbench_services.editor_panel.clear_active_tab,
            refresh_schema=self.workbench_services.schema.refresh_current_schema,
            undo=self.workbench_services.results.undo,
            visualize_data=lambda: self.workbench_services.visualization.open_dialog(self),
            logger=self.ui_logger,
        )
        self._toolbar = self.toolbar_controller.build(self)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self._toolbar)
        self.toolbar_controller.apply_has_data_state(False)
        self.toolbar_controller.apply_connection_state(False)
        self.workbench_services.results.apply_toolbar_data_state(self.toolbar_controller.apply_has_data_state)
        self.workbench_services.results.apply_toolbar_multiple_dataset_state(
            self.toolbar_controller.apply_has_multiple_datasets_state
        )
        self.workbench_services.icon_service.icons_updated.connect(self.toolbar_controller.apply_icons)

        # ------------------------------------------------
        # Editor tab → toolbar Run-state
        # ------------------------------------------------
        def update_run_state_from_editor_tab() -> None:
            can_run = self.workbench_services.editor_panel.can_execute_sql()
            self.toolbar_controller.apply_connection_state(can_run)

        self.workbench_services.editor_panel.on_active_tab_changed(update_run_state_from_editor_tab)
        update_run_state_from_editor_tab()

        # -------------------------------------------
        # Menu
        # -------------------------------------------
        self.menu_controller = MenuController(
            menubar=self.menuBar(),  # type: ignore
            new_file=self.workbench_services.editor_panel.new_file,
            open_file=self.workbench_services.document.open_any_dialog,
            save_file=self.workbench_services.document.save_sql,
            save_file_as=self.workbench_services.document.save_sql_as,
            quit_app=self.close,
            export_csv=self.workbench_services.export.export_csv,
            export_excel=self.workbench_services.export.export_excel,
            export_data=self.workbench_services.export.export_data,
            export_profile=self.workbench_services.export.profile_report,
            clear_editor=self.workbench_services.editor_panel.clear_active_tab,
            open_settings_dialog=self._open_settings_dialog,
            open_log_settings_dialog=self._open_log_dialog,
            open_connection_dialog=self._open_connection_dialog,
            open_rest_connection_dialog=self.open_rest_connection_dialog,
            show_about_dialog=self._show_about_dialog,
        )
        self.menu_controller.apply_has_data_state(False)
        self.workbench_services.results.apply_toolbar_data_state(self.menu_controller.apply_has_data_state)

        # Apply initial translations
        self.retranslate_ui()

    # ==================================================================
    # Dialogs
    # ==================================================================
    def _open_log_dialog(self) -> None:
        """Open the log configuration dialog and reload settings if changed."""
        dlg = LogConfigEditor(
            parent=self,
            dialogs=self._dialogs,
            icon_service=self.workbench_services.icon_service,
        )
        if dlg.exec():
            self._reload_logging()
            self.status_controller.set_status(self.tr("Logg settings reloaded."), 4000)

    def _open_settings_dialog(self) -> None:
        """Open the general settings dialog and reload settings if changed."""
        dlg = SettingsEditor(
            parent=self,
            dialogs=self._dialogs,
            file_dialogs=self._file_dialogs,
            highlighter_theme_service=self.workbench_services.highlighter_theme_service,
            icon_service=self.workbench_services.icon_service,
        )
        if dlg.exec():
            self.services.settings_service.reload()
            self.status_controller.set_status(self.tr("Settings reloaded."), 4000)

    def _open_connection_dialog(self) -> None:
        """Open the database connection editor dialog."""
        dlg = ConnectionEditor(
            parent=self,
            dialogs=self._dialogs,
            icon_service=self.workbench_services.icon_service,
        )
        dlg.connections_changed.connect(
            lambda: self.workbench_services.schema.refresh_connections(
                self.connection_controller.get_connection_names()
            )
        )
        dlg.exec()

    def open_rest_connection_dialog(self, preset_name: str | None = None):
        """Open the REST connection editor dialog."""
        dlg = RestConnectionEditor(
            parent=self,
            preset_name=preset_name,
            dialogs=self._dialogs,
            icon_service=self.workbench_services.icon_service,
        )
        dlg.connections_changed.connect(self.workbench_services.rest_panel.reload)
        dlg.exec()

    def _show_about_dialog(self) -> None:
        """Show the professional About dialog."""
        dlg = AboutDialog(parent=self)
        dlg.exec()

    # ==================================================================
    # Logging and undo
    # ==================================================================
    def _reload_logging(self) -> None:
        """Reload logging configuration from logconfig.json without restarting."""
        self.services.logging_manager.setup()
        self.ui_logger.info("Logg settings reloaded.")

    def update_undo_enabled(self):
        """Enable/disable the Undo button depending on current tab's undo stack."""
        enabled = bool(self.workbench_services.results.can_undo_current())
        self.toolbar_controller.set_undo_enabled(enabled)

    # ==================================================================
    # UI language
    # ==================================================================
    def retranslate_ui(self) -> None:
        """Update all translatable UI strings."""
        self.setWindowTitle(self.tr("Expo studio"))

        # Docks
        self._schema_dock.setWindowTitle(self.tr("Database connections"))
        self._files_dock.setWindowTitle(self.tr("Files"))
        self._rest_dock.setWindowTitle(self.tr("REST connections"))

        # Menus, toolbar, status etc
        if self.menu_controller:
            self.menu_controller.retranslate_ui()

        if self.toolbar_controller:
            self.toolbar_controller.retranslate_ui()

        if self.status_controller:
            self.status_controller.retranslate_ui()

        if self.schema_tree:
            self.workbench_services.schema.retranslate_ui()

    @override
    def changeEvent(self, event):
        """Handle Qt language change events."""
        if event.type() == event.Type.LanguageChange:
            self.retranslate_ui()
        super().changeEvent(event)

    # ==================================================================
    # Cancel all jobs
    # ==================================================================

    def _cancel_all_jobs_from_toolbar(self) -> None:
        """Request cancellation for all active background jobs."""
        services = self.services
        if services is None:
            if self.ui_logger is not None:
                self.ui_logger.warning("MainWindow: cancel-all requested but no services were available.")
            return

        job_mgr = cast("object", services.job_mgr)
        if job_mgr is None:
            if self.ui_logger is not None:
                self.ui_logger.warning("MainWindow: cancel-all requested but no JobManager was available.")
            return

        active_jobs = services.job_mgr.active_jobs
        if active_jobs <= 0:
            if self.status_controller is not None:
                self.status_controller.set_status(
                    self.tr("No active jobs to cancel."),
                    4000,
                )
            return

        cancelled_count = services.job_mgr.cancel_all()

        if self.ui_logger is not None:
            self.ui_logger.info(
                "MainWindow: cancel-all requested from toolbar (active_jobs=%s, cancelled=%s)",
                active_jobs,
                cancelled_count,
            )

        if self.status_controller is not None:
            self.status_controller.set_status(
                self.tr("Cancelling active jobs…"),
                4000,
            )

    # ==================================================================
    # Close application
    # ==================================================================
    @override
    def closeEvent(self, event: QCloseEvent) -> None:
        """Coordinate application shutdown with background job teardown.

        The window is not allowed to close immediately after the user confirms exit.
        Instead, cooperative shutdown is initiated and the application waits until
        active background jobs are finalized before the close is accepted.

        Args:
            event: The Qt close event.
        """
        if self._allow_close:
            event.accept()
            return

        if self._shutdown_in_progress:
            event.ignore()
            return

        try:
            ok = self._dialogs.prompt_yes_no(
                self,
                title=self.tr("Confirm exit"),
                text=self.tr("Do you want to quit the application?"),
                informative=None,
                default_yes=False,
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
        ):
            ok = False

        if not ok:
            event.ignore()
            return

        self._shutdown_in_progress = True
        self._shutdown_timeout_logged = False
        self._shutdown_deadline_monotonic = time.monotonic() + 5.0

        try:
            from expo_jbm329.gui.gui_utils import set_app_closing

            set_app_closing(True)

            if self.services is not None and self.services.job_mgr is not None:
                still_running = self.services.job_mgr.abort_all(wait_ms=250)
                if self.ui_logger is not None and still_running:
                    self.ui_logger.warning(
                        "MainWindow: waiting for active jobs during shutdown: %s",
                        still_running,
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
        ):
            if self.ui_logger is not None:
                self.ui_logger.exception("Error initiating application shutdown.")

            # Fail safe: allow close if shutdown coordination itself crashes.
            self._allow_close = True
            event.accept()
            return

        event.ignore()
        QTimer.singleShot(100, self._continue_shutdown_poll)

    def _continue_shutdown_poll(self) -> None:
        """Poll background job teardown until shutdown can complete safely."""
        active_jobs = self.services.job_mgr.active_jobs if self.services.job_mgr is not None else 0

        if active_jobs == 0:
            self._finalize_shutdown_and_close()
            return

        deadline = self._shutdown_deadline_monotonic
        if deadline is not None and time.monotonic() >= deadline:
            if not self._shutdown_timeout_logged:
                if self.ui_logger is not None:
                    active_ids = self.services.job_mgr.active_job_ids if self.services.job_mgr is not None else ()
                    self.ui_logger.error(
                        "MainWindow: shutdown timeout with active jobs still present: %s",
                        active_ids,
                    )
                self._shutdown_timeout_logged = True

            # Retry cooperative abort once more, then keep polling.
            try:
                if self.services is not None and self.services.job_mgr is not None:
                    self.services.job_mgr.abort_all(wait_ms=250)
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
                if self.ui_logger is not None:
                    self.ui_logger.exception("Error retrying abort_all during shutdown.")

            QTimer.singleShot(100, self._continue_shutdown_poll)
            return

        QTimer.singleShot(100, self._continue_shutdown_poll)

    def _finalize_shutdown_and_close(self) -> None:
        """Perform final shutdown cleanup and close the window."""
        try:
            if self.workbench_services is not None:
                self.workbench_services.schema.schema_mgr.clear_all()

            close_all_connections()

            if self.services is not None and self.services.job_mgr is not None:
                self.services.job_mgr.shutdown(wait=False)

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
            if self.ui_logger is not None:
                self.ui_logger.exception("Error completing application shutdown.")
        finally:
            self._allow_close = True
            self.close()
