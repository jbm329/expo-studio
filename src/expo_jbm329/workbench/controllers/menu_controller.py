"""Menu bar controller for the Expo application.

This module provides the MenuController class, which handles all menu bar
creation, action setup, and callback wiring for the main application window.
It encapsulates all Qt menu boilerplate, allowing the main application to
remain focused on business logic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QT_TR_NOOP
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMenu, QMenuBar

from expo_jbm329.utils.i18n_utils import tr

if TYPE_CHECKING:
    from collections.abc import Callable


class MenuController:
    """Controller for managing the menu bar in the Expo application.

    This class handles menu bar creation, action creation, and wiring actions
    to ExpoStudio controllers. It keeps ExpoStudio free from QMenu/QAction
    boilerplate by centralizing all menu-related logic.
    """

    # --- i18n markers (pylupdate6-visible) -----------------------------
    TR_FILE = QT_TR_NOOP("File")
    TR_NEW_FILE = QT_TR_NOOP("New file")
    TR_OPEN = QT_TR_NOOP("Open…")
    TR_SAVE = QT_TR_NOOP("Save")
    TR_SAVE_AS = QT_TR_NOOP("Save as…")
    TR_EXPORT = QT_TR_NOOP("Export…")
    TR_EXPORT_TO_CSV = QT_TR_NOOP("Export to CSV…")
    TR_EXPORT_TO_EXCEL = QT_TR_NOOP("Export to Excel…")
    TR_EXPORT_TO_DATA = QT_TR_NOOP("Export to binary data file…")

    TR_QUIT = QT_TR_NOOP("Quit")
    TR_EDIT = QT_TR_NOOP("Edit")
    TR_CLEAR_EDITOR = QT_TR_NOOP("Clear editor")

    TR_TOOLS = QT_TR_NOOP("Tools")
    TR_SETTINGS = QT_TR_NOOP("Settings…")
    TR_LOG_SETTINGS = QT_TR_NOOP("Log settings…")
    TR_DATABASE_CONNECTIONS = QT_TR_NOOP("Database connections…")
    TR_REST_CONNECTIONS = QT_TR_NOOP("REST connections…")

    TR_EXT_TOOLS = QT_TR_NOOP("External tools")
    TR_YDATA_PROFILING = QT_TR_NOOP("YData profiling…")

    TR_HELP = QT_TR_NOOP("Help")
    TR_ABOUT = QT_TR_NOOP("About Expo studio…")

    @staticmethod
    def _tr(text: str) -> str:
        return tr("MenuController", text)

    def __init__(
        self,
        *,
        menubar: QMenuBar,
        new_file: Callable[[], None],
        open_file: Callable[[], None],
        save_file: Callable[[], None],
        save_file_as: Callable[[], None],
        quit_app: Callable[[], object],
        export_csv: Callable[[], None],
        export_excel: Callable[[], None],
        export_data: Callable[[], None],
        export_profile: Callable[[], None],
        clear_editor: Callable[[], None],
        open_settings_dialog: Callable[[], None],
        open_log_settings_dialog: Callable[[], None],
        open_connection_dialog: Callable[[], None],
        open_rest_connection_dialog: Callable[[], None],
        show_about_dialog: Callable[[], None],
    ) -> None:
        """Initialize the MenuController.

        Args:
            menubar: The QMenuBar to populate.
            new_file: Callback for new file action.
            open_file: Callback for open file action.
            save_file: Callback for save file action.
            save_file_as: Callback for save file as action.
            quit_app: Callback for quit action.
            export_csv: Callback for export to CSV action.
            export_excel: Callback for export to Excel action.
            export_data: Callback for export to data file action.
            export_profile: Callback for export profile action.
            clear_editor: Callback for clear editor action.
            open_settings_dialog: Callback for open settings dialog.
            open_log_settings_dialog: Callback for open log settings dialog.
            open_connection_dialog: Callback for open connection dialog.
            open_rest_connection_dialog: Callback for open REST connection dialog.
            show_about_dialog: Callback for show about dialog.
        """
        self._menubar = menubar
        self._new_file = new_file
        self._open_file = open_file
        self._save_file = save_file
        self._save_file_as = save_file_as
        self._quit_app = quit_app
        self._export_csv = export_csv
        self._export_excel = export_excel
        self._export_data = export_data
        self._export_profile = export_profile
        self._clear_editor = clear_editor
        self._open_settings = open_settings_dialog
        self._open_log_settings = open_log_settings_dialog
        self._open_connections = open_connection_dialog
        self._open_rest_connections = open_rest_connection_dialog
        self._show_about = show_about_dialog

        self._build_menu_bar()
        self._connect_menu_logic()

    # ----------------------------------------------------------------------
    def _build_menu_bar(self) -> None:
        """Build the complete menu bar structure with all menus and actions."""
        mb = self._menubar

        # ============ File ============
        self._menu_file = QMenu(self._tr(self.TR_FILE), mb)
        mb.addMenu(self._menu_file)

        self._act_new = QAction(self._tr(self.TR_NEW_FILE), mb)
        self._act_new.setShortcut("Ctrl+N")
        self._menu_file.addAction(self._act_new)

        self._act_open = QAction(self._tr(self.TR_OPEN), mb)
        self._act_open.setShortcut("Ctrl+O")
        self._menu_file.addAction(self._act_open)

        self._act_save = QAction(self._tr(self.TR_SAVE), mb)
        self._act_save.setShortcut("Ctrl+S")
        self._menu_file.addAction(self._act_save)

        self._act_save_as = QAction(self._tr(self.TR_SAVE_AS), mb)
        self._menu_file.addAction(self._act_save_as)

        self._menu_file.addSeparator()

        # Export submenu
        self._menu_export = QMenu(self._tr(self.TR_EXPORT), mb)
        self._menu_file.addMenu(self._menu_export)

        self._act_export_csv = QAction(self._tr(self.TR_EXPORT_TO_CSV), mb)
        self._menu_export.addAction(self._act_export_csv)

        self._act_export_excel = QAction(self._tr(self.TR_EXPORT_TO_EXCEL), mb)
        self._menu_export.addAction(self._act_export_excel)

        self._act_export_data = QAction(self._tr(self.TR_EXPORT_TO_DATA), mb)
        self._menu_export.addAction(self._act_export_data)

        self._menu_file.addSeparator()

        self._act_quit = QAction(self._tr(self.TR_QUIT), mb)
        self._act_quit.setShortcut("Ctrl+Q")
        self._menu_file.addAction(self._act_quit)

        # ============ Edit ============
        self._menu_edit = QMenu(self._tr(self.TR_EDIT), mb)
        mb.addMenu(self._menu_edit)

        self._act_clear = QAction(self._tr(self.TR_CLEAR_EDITOR), mb)
        self._act_clear.setShortcut("Ctrl+L")
        self._menu_edit.addAction(self._act_clear)

        # ============ Tools ============
        self._menu_tools = QMenu(self._tr(self.TR_TOOLS), mb)
        mb.addMenu(self._menu_tools)

        self._act_settings = QAction(self._tr(self.TR_SETTINGS), mb)
        self._menu_tools.addAction(self._act_settings)

        self._act_log_settings = QAction(self._tr(self.TR_LOG_SETTINGS), mb)
        self._menu_tools.addAction(self._act_log_settings)

        self._act_connections = QAction(self._tr(self.TR_DATABASE_CONNECTIONS), mb)
        self._menu_tools.addAction(self._act_connections)

        self._act_rest_connections = QAction(self._tr(self.TR_REST_CONNECTIONS), mb)
        self._menu_tools.addAction(self._act_rest_connections)

        # ============ External tools ============
        self._menu_ext = QMenu(self._tr(self.TR_EXT_TOOLS), mb)
        mb.addMenu(self._menu_ext)

        self.act_ydata_profiling = QAction(self._tr(self.TR_YDATA_PROFILING), mb)
        self._menu_ext.addAction(self.act_ydata_profiling)

        # ============ Help ============
        self._menu_help = QMenu(self._tr(self.TR_HELP), mb)
        mb.addMenu(self._menu_help)

        self._act_about = QAction(self._tr(self.TR_ABOUT), mb)
        self._menu_help.addAction(self._act_about)

    # ----------------------------------------------------------------------
    def _connect_menu_logic(self) -> None:
        """Wire all menu actions to their respective callbacks."""
        # File
        self._act_new.triggered.connect(self._new_file)
        self._act_open.triggered.connect(self._open_file)
        self._act_save.triggered.connect(self._save_file)
        self._act_save_as.triggered.connect(self._save_file_as)
        self._act_quit.triggered.connect(self._quit_app)

        # Export
        self._act_export_csv.triggered.connect(self._export_csv)
        self._act_export_excel.triggered.connect(self._export_excel)
        self._act_export_data.triggered.connect(self._export_data)
        self.act_ydata_profiling.triggered.connect(self._export_profile)

        # Editing
        self._act_clear.triggered.connect(self._clear_editor)

        # Tools
        self._act_settings.triggered.connect(self._open_settings)
        self._act_log_settings.triggered.connect(self._open_log_settings)
        self._act_connections.triggered.connect(self._open_connections)
        self._act_rest_connections.triggered.connect(self._open_rest_connections)

        # Help
        self._act_about.triggered.connect(self._show_about)

    # ----------------------------------------------------------------------

    def apply_has_data_state(self, has_data: bool) -> None:
        """Enable/disable export actions based on dataset availability.

        Args:
            has_data: Whether there is data available to export.
        """
        self._act_export_csv.setEnabled(has_data)
        self._act_export_excel.setEnabled(has_data)
        self._act_export_data.setEnabled(has_data)
        self.act_ydata_profiling.setEnabled(has_data)

    # UI language
    def retranslate_ui(self) -> None:
        """Update all menu titles and action texts to the current language."""
        self._menu_file.setTitle(self._tr(self.TR_FILE))
        self._menu_edit.setTitle(self._tr(self.TR_EDIT))
        self._menu_tools.setTitle(self._tr(self.TR_TOOLS))
        self._menu_ext.setTitle(self._tr(self.TR_EXT_TOOLS))
        self._menu_help.setTitle(self._tr(self.TR_HELP))

        self._act_new.setText(self._tr(self.TR_NEW_FILE))
        self._act_open.setText(self._tr(self.TR_OPEN))
        self._act_save.setText(self._tr(self.TR_SAVE))
        self._act_save_as.setText(self._tr(self.TR_SAVE_AS))
        self._act_quit.setText(self._tr(self.TR_QUIT))

        self._menu_export.setTitle(self._tr(self.TR_EXPORT))
        self._act_export_csv.setText(self._tr(self.TR_EXPORT_TO_CSV))
        self._act_export_excel.setText(self._tr(self.TR_EXPORT_TO_EXCEL))
        self._act_export_data.setText(self._tr(self.TR_EXPORT_TO_DATA))

        self._act_clear.setText(self._tr(self.TR_CLEAR_EDITOR))

        self._act_settings.setText(self._tr(self.TR_SETTINGS))
        self._act_log_settings.setText(self._tr(self.TR_LOG_SETTINGS))
        self._act_connections.setText(self._tr(self.TR_DATABASE_CONNECTIONS))
        self._act_rest_connections.setText(self._tr(self.TR_REST_CONNECTIONS))

        self.act_ydata_profiling.setText(self._tr(self.TR_YDATA_PROFILING))
        self._act_about.setText(self._tr(self.TR_ABOUT))
