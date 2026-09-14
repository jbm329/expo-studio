"""Controller for file-open and file-save actions.

This module coordinates file selection dialogs and dispatches the requested
operation to the appropriate workbench service.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QT_TR_NOOP
from PyQt6.QtWidgets import QWidget

from expo_jbm329.gui.dialogs.service.dialog_service import DialogService
from expo_jbm329.gui.dialogs.service.qt_dialog_service import QtDialogService
from expo_jbm329.gui.dialogs.workflows.file.file_dialog_service import (
    FileDialogService,
    OpenFileRequest,
    SaveFileRequest,
)
from expo_jbm329.services.file_types import FileType, classify_file
from expo_jbm329.utils.dialog_state import DialogState
from expo_jbm329.utils.format_utils import fmt_path
from expo_jbm329.utils.i18n_utils import tr, tr_fmt
from expo_jbm329.utils.path_manager import get_documents_dir
from expo_jbm329.workbench.controllers.editor_tab_manager import EditorTab


class DocumentController:
    """Handle file-open and file-save operations for ExpoStudio."""

    # --- i18n markers (pylupdate6-visible) -----------------------------
    TR_SUPPORTED_FILES_FILTER = QT_TR_NOOP(
        "All supported files (*.sql *.csv *.xls *.xlsx *.feather *.ft *.parquet *.qvd *.dta *.sav "
        "*.df *.pkl *.html *.htm);;"
        "SQL files (*.sql);;"
        "CSV files (*.csv);;"
        "Excel files (*.xls *.xlsx);;"
        "Feather files (*.feather *.ft);;"
        "Parquet files (*.parquet);;"
        "Pickle/DF files (*.df *.pkl);;"
        "HTML files (*.html *.htm);;"
        "QVD files (*.qvd);;"
        "SPSS files (*.sav);;"
        "Stata files (*.dta);;"
    )
    # --- i18n markers (pylupdate6-visible) -----------------------------
    TR_OPEN_FILE = QT_TR_NOOP("Open file")
    TR_SAVE_SQL_FILE = QT_TR_NOOP("Save SQL file")

    TR_OPENED_SQL_FILE = QT_TR_NOOP("Opened SQL file: {file_name}")
    TR_OPENED_HTML_FILE = QT_TR_NOOP("Opened HTML file in browser: {file_name}")
    TR_SAVED_SQL_FILE = QT_TR_NOOP("Saved SQL file: {file_name}")

    TR_FAILURE = QT_TR_NOOP("Failure")
    TR_UNSUPPORTED_FILE_TYPE = QT_TR_NOOP("File type not supported in ExpoStudio: {file_name}")
    TR_OPEN_SQL_FILE_FAILED = QT_TR_NOOP("Open SQL file failed")
    TR_OPEN_HTML_FILE_FAILED = QT_TR_NOOP("Open HTML file failed")
    TR_SAVE_SQL_FILE_FAILED = QT_TR_NOOP("Save SQL file failed")
    TR_OPEN_SQL_FILE_FAILED_ERROR = QT_TR_NOOP("Open SQL file failed:\n{error}")
    TR_SAVE_SQL_FILE_FAILED_ERROR = QT_TR_NOOP("Save SQL file failed:\n{error}")
    TR_OPEN_HTML_FILE_FAILED_ERROR = QT_TR_NOOP("Open HTML file failed:\n{error}")
    
    TR_SQL_FILE_FILTER = QT_TR_NOOP("SQL files (*.sql)")
    TR_COULD_NOT_OPEN_FILE = QT_TR_NOOP("Could not open file:\n\n{error}")
    TR_NO_SQL = QT_TR_NOOP("No SQL")
    TR_NO_SQL_TO_SAVE = QT_TR_NOOP("There is no active tab to save.")

    @staticmethod
    def _tr(text: str) -> str:
        return tr("DocumentController", text)

    @staticmethod
    def _tr_fmt(text: str, **kwargs: str) -> str:
        return tr_fmt("DocumentController", text, **kwargs)

    __slots__ = (
        "__weakref__",
        "_clear_dirty",
        "_create_tab",
        "_dialog_state",
        "_dialogs",
        "_documents_dir",
        "_file_dialogs",
        "_get_active_tab",
        "_get_editor_text",
        "_insert_sql_into_tab",
        "_logger",
        "_open_data_file",
        "_parent",
        "_set_file_path",
        "_set_status",
        "_update_tab_ui",
    )

    def __init__(
        self,
        parent: QWidget,
        file_dialogs: FileDialogService,
        dialogs: DialogService,
        set_status: Callable[[str, int | None], None],
        get_active_tab: Callable[[], EditorTab | None],
        clear_dirty: Callable[[str], None],
        set_file_path: Callable[[str, str], None],
        update_tab_ui: Callable[[EditorTab], None],
        get_editor_text: Callable[[], str | None],
        create_tab: Callable[..., EditorTab],
        insert_sql_into_tab: Callable[[EditorTab, str], None],
        open_data_file: Callable,
        dialog_state: DialogState,
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialize the controller.

        Args:
            parent: Parent widget used for dialogs.
            file_dialogs: Service responsible for opening file dialogs.
            dialogs: Service responsible for showing dialogs.
            set_status: Callback for setting the status bar message.
            get_active_tab: Callback for retrieving the active editor tab.
            clear_dirty: Callback for clearing the dirty state of a file.
            set_file_path: Callback for setting the file path in an editor tab.
            update_tab_ui: Callback for updating the UI of an editor tab.
            get_editor_text: Callback for retrieving the text from the current editor.
            create_tab: Callback for creating an editor tab from SQL file.
            insert_sql_into_tab: Callback for inserting SQL into a specific editor tab.
            open_data_file: Callback for opening data files.
            dialog_state: Dialog state manager.
            logger: Optional logger instance.
        """
        self._parent = parent
        self._file_dialogs = file_dialogs
        self._dialogs = dialogs if dialogs is not None else QtDialogService()
        self._set_status = set_status
        self._get_active_tab = get_active_tab
        self._clear_dirty = clear_dirty
        self._set_file_path = set_file_path
        self._update_tab_ui = update_tab_ui
        self._get_editor_text = get_editor_text
        self._create_tab = create_tab
        self._insert_sql_into_tab = insert_sql_into_tab
        self._open_data_file = open_data_file
        self._dialog_state = dialog_state
        self._logger = logger if logger is not None else logging.getLogger("applogger.ui")
        self._documents_dir: Path | None = None

    # ==================================================================
    # Settings
    # ==================================================================
    def reload_settings(self, settings: dict) -> None:
        """Synchronize ExportController with updated global settings.

        Things controlled by settings:
            • get_documents_dir
        """
        try:
            self._documents_dir = get_documents_dir(settings)
            self._logger.debug(
                "DocumentController: settings reloaded (documents_dir=%s).",
                fmt_path(self._get_documents_dir()),
            )
        except Exception as e:
            self._logger.exception("DocumentController: failed to reload settings: %s", e)

    # ----------------------------------------------------------------------
    # Helpers
    # ----------------------------------------------------------------------

    def _open_sql_file(self, path: str | Path) -> None:
        """Open a SQL file and insert its contents into the editor."""
        p = Path(path)
        self._logger.info("DocumentController: opening SQL file: %s", fmt_path(p))
        try:
            with open(p, encoding="utf-8") as f:
                sql = f.read()                
                self._logger.info(
                    "DocumentController: SQL file opened successfully: %s", fmt_path(p)
                )
        except Exception as e:
            status = self._tr(self.TR_OPEN_SQL_FILE_FAILED)
            self._set_status(status, 6000)
            self._logger.error(
                "DocumentController: Failed to open SQL file '%s': %s",
                fmt_path(p),
                e,
                exc_info=True,
            )
            self._dialogs.critical(
                self._parent,
                title=self._tr(self.TR_FAILURE),
                text=self._tr_fmt(
                    self.TR_COULD_NOT_OPEN_FILE,
                    error=str(e),
                ),
            )
            return

        tab = self._create_tab(
            connection_name=None,
            base_title=p.name,
        )

        self._insert_sql_into_tab(tab, sql)
        self._set_file_path(tab.tab_id, str(p))
        self._clear_dirty(tab.tab_id)
        self._update_tab_ui(tab)
        status = self._tr_fmt(self.TR_OPENED_SQL_FILE, file_name=p.name)
        self._set_status(status, 5000)
            
    def _get_documents_dir(self) -> Path:
        """Return documents directory, guaranteed to be initialized."""
        if self._documents_dir is None:
            raise RuntimeError(
                "DocumentController: documents_dir not initialized. "
                "reload_settings() must be called before export."
            )
        return self._documents_dir   

    def _build_incremented_path(self, path: Path) -> Path:
        """Return a non-existing path by appending (n) before suffix.

        Example:
            customers.sql → customers.sql (1)
            customers.sql (1) → customers.sql (2)
        """
        _ = self._logger
        parent = path.parent
        stem = path.stem
        suffix = path.suffix

        # Remove existing " (n)" if present
        base = stem
        counter = 1

        import re

        m = re.match(r"^(.*?)(?:\s\((\d+)\))?$", stem)
        if m:
            base = m.group(1)
            if m.group(2):
                counter = int(m.group(2)) + 1

        candidate = parent / f"{base}{suffix}"
        if not candidate.exists():
            return candidate

        while True:
            candidate = parent / f"{base}{suffix} ({counter})"
            if not candidate.exists():
                return candidate
            counter += 1

    # ----------------------------------------------------------------------
    # Public API
    # ----------------------------------------------------------------------

    def open_any_dialog(self) -> None:
        """Open a supported file and dispatch it to the correct handler."""
        filter_str = self._tr_fmt(self.TR_SUPPORTED_FILES_FILTER)

        start_dir = self._dialog_state.get_dir(
            "dialogs/open_any_dir",
            fallback=self._get_documents_dir(),
        )

        req = OpenFileRequest(
            title=self._tr(self.TR_OPEN_FILE),
            initial_path=str(start_dir),
            filter_str=filter_str
        )
        path, _ = self._file_dialogs.get_open_filename(
            parent=self._parent,
            req=req
        )

        if not path:
            return

        self._dialog_state.set_dir(
            "dialogs/open_any_dir",
            Path(path).parent,
        )
        self.open_any(path)

    def open_any(self, path: str | Path) -> None:
        """Open a file and dispatch it to the correct handler."""
        path = Path(path)
        ft: FileType = classify_file(path=path)

        if ft == "sql":
            self._open_sql_file(path=path)
            return
        if ft == "html":
            self.open_html_file(path=path)
            return
        if ft == "data":
            self._open_data_file(path=path)
            return
        status = self._tr_fmt(self.TR_UNSUPPORTED_FILE_TYPE, file_name=path.name)
        self._set_status(status, 5000)
        self._dialogs.info(
            self._parent,
            title=self._tr(self.TR_FAILURE),
            text=self._tr_fmt(self.TR_UNSUPPORTED_FILE_TYPE, file_name=path.name),
        )

    def save_sql(self) -> None:
        """Save SQL content from the editor to its current file, or prompt for a location if not already saved."""
        self._logger.info("DocumentController: saving SQL file")

        tab = self._get_active_tab()
        if not tab:
            self._dialogs.info(
                self._parent,
                title=self._tr(self.TR_NO_SQL),
                text=self._tr(self.TR_NO_SQL_TO_SAVE),
            )
            return

        text = self._get_editor_text()
        if not text:
            return

        if not tab.file_path:
            self.save_sql_as()
            return

        try:
            Path(tab.file_path).write_text(text, encoding="utf-8")
            self._logger.info(
                "DocumentController: SQL file saved as successfully: %s", fmt_path(tab.file_path)
            )
            status = self._tr(self.TR_SAVED_SQL_FILE)
            self._set_status(status, 3000)
            
        except Exception as e:
            self._logger.error(
                "DocumentController: Failed to save as SQL file '%s': %s",
                fmt_path(tab.file_path),
                e,
                exc_info=True,
            )
            status = self._tr(self.TR_SAVE_SQL_FILE_FAILED)
            self._set_status(status, 6000)
            self._dialogs.critical(
                self._parent,
                title=self._tr(self.TR_FAILURE),
                text=str(e),
            )
            return

        self._clear_dirty(tab.tab_id)
        self._update_tab_ui(tab)

    def save_sql_as(self) -> None:
        """Save SQL content from the editor to a new file."""
        tab = self._get_active_tab()
        if not tab:
            self._dialogs.info(
                self._parent,
                title=self._tr(self.TR_NO_SQL),
                text=self._tr(self.TR_NO_SQL_TO_SAVE),
            )
            return

        text = self._get_editor_text()
        if not text:
            return

        # --------------------------------------------------
        # Determine default path (smart, state-aware)
        # --------------------------------------------------
        if tab.file_path:
            # Existing file → suggest incremented copy
            default_path = self._build_incremented_path(Path(tab.file_path))
        else:
            # New file → derive from tab title
            base_name = tab.base_title or "query"
            if not base_name.lower().endswith(".sql"):
                base_name = f"{base_name}.sql"

            base_dir = self._dialog_state.get_dir(
                "dialogs/save_sql_dir",
                fallback=self._get_documents_dir(),
            )

            default_path = Path(base_dir) / base_name

        # --------------------------------------------------
        # Open save dialog
        # --------------------------------------------------
        req = SaveFileRequest(
            title=self._tr(self.TR_SAVE_SQL_FILE),
            initial_path=str(default_path),
            filter_str=self._tr(self.TR_SQL_FILE_FILTER),
        )

        path, _ = self._file_dialogs.get_save_filename(self._parent, req)
        if not path:
            return

        # --------------------------------------------------
        # Write file
        # --------------------------------------------------
        try:
            Path(path).write_text(text, encoding="utf-8")
            self._logger.info("DocumentController: SQL file saved as successfully: %s", fmt_path(path))
            status = self._tr(self.TR_SAVED_SQL_FILE)
            self._set_status(status, 3000)
        except Exception as e:
            self._logger.error(
                "DocumentController: Failed to save as SQL file '%s': %s",
                fmt_path(path),
                e,
                exc_info=True,
            )
            status = self._tr(self.TR_SAVE_SQL_FILE_FAILED)
            self._set_status(status, 6000)
            self._dialogs.critical(
                self._parent,
                title=self._tr(self.TR_FAILURE),
                text=str(e),
            )
            return

        # --------------------------------------------------
        # Persist state after successful save
        # --------------------------------------------------
        self._dialog_state.set_dir(
            "dialogs/save_sql_dir",
            Path(path).parent,
        )

        self._set_file_path(tab.tab_id, path)
        self._clear_dirty(tab.tab_id)
        self._update_tab_ui(tab)

    def open_html_file(self, *, path: str | Path) -> bool:
        """Open an HTML file in the default browser.

        Args:
            path: The path to the HTML file.
        """
        p = Path(path)
        self._logger.info("DocumentController: opening HTML file: %s", fmt_path(p))
        import webbrowser
        ok = False
        try:
            uri = p.resolve().as_uri()
            ok = webbrowser.open(uri)
            status = self._tr_fmt(self.TR_OPENED_HTML_FILE, file_name=p.name)
            self._set_status(status, 5000)
            self._logger.info("DocumentController: HTML file opened: %s", fmt_path(p))
            return ok

        except Exception as e:
            status = self._tr(self.TR_OPEN_HTML_FILE_FAILED)
            self._set_status(status, 6000)
            self._logger.error(
                "DocumentController: failed to open HTML file '%s': %s",
                fmt_path(p),
                e,
                exc_info=True
            )
            self._dialogs.critical(
                parent=self._parent,
                title=self._tr(self.TR_FAILURE),
                text=self._tr_fmt(self.TR_OPEN_HTML_FILE_FAILED_ERROR, error=str(e))
            )
            return ok
        