"""Controller for the file panel in the workbench UI.

This module coordinates file-panel interactions such as opening files,
handling context-menu actions, and delegating file operations to the
appropriate services.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QT_TR_NOOP, QModelIndex, QPoint, Qt
from PyQt6.QtGui import QAction, QFileSystemModel
from PyQt6.QtWidgets import (
    QMenu,
    QTreeView,
    QWidget,
)

from expo_jbm329.gui.dialogs.service.dialog_service import DialogService
from expo_jbm329.gui.dialogs.service.qt_dialog_service import QtDialogService
from expo_jbm329.services.file_types import classify_file
from expo_jbm329.utils.format_utils import fmt_path, fmt_path_size
from expo_jbm329.utils.i18n_utils import tr, tr_fmt


class FilePanelController:
    """Coordinate file-panel interactions in the left dock."""

    # --- i18n markers (pylupdate6-visible) -----------------------------
    TR_UNKNOWN_FILE_FORMAT = QT_TR_NOOP("Unknown file format")
    TR_CANNOT_OPEN_FILE = QT_TR_NOOP("The file can not be opened:\n\n{file}")
    TR_OPEN = QT_TR_NOOP("Open")
    TR_RENAME = QT_TR_NOOP("Rename…")
    TR_DELETE = QT_TR_NOOP("Delete…")
    TR_DELETE_FAILED = QT_TR_NOOP("Failed to delete the file.")
    TR_FILE_NO_LONGER_EXISTS = QT_TR_NOOP("The file no longer exists.")
    TR_RENAME_FILE = QT_TR_NOOP("Rename file")
    TR_NEW_FILE_NAME = QT_TR_NOOP("New file name:")
    TR_FAILED_TO_RENAME_FILE = QT_TR_NOOP("Failed to rename the file.")
    TR_SOMETHING_WENT_WRONG_RENAME_FILE = QT_TR_NOOP(
        "Something went wrong trying to rename file: \n\n{error}"
    )
    TR_FAILURE = QT_TR_NOOP("Failure")
    TR_DELETE_FILE = QT_TR_NOOP("Delete file")
    TR_DELETING_FILE = QT_TR_NOOP("Deleting file: {file} …")
    TR_FILE_DELETED = QT_TR_NOOP("File deleted: {file}")
    TR_FAILED_TO_DELETE_FILE = QT_TR_NOOP("Failed to delete the file.")
    TR_SOMETHING_WENT_WRONG_DELETE_FILE = QT_TR_NOOP(
        "Something went wrong trying to delete file: \n\n{path}"
    )
    TR_CONFIRM_DELETE = QT_TR_NOOP("Confirm delete")
    TR_SOMETHING_WENT_WRONG_DELETE_FILE_ERROR = QT_TR_NOOP(
        "Something went wrong trying to delete file: \n\n{file}\n\n{error}"
    )

    @staticmethod
    def _tr(text: str) -> str:
        return tr("FilePanelController", text)

    @staticmethod
    def _tr_fmt(text: str, **kwargs: str) -> str:
        return tr_fmt("FilePanelController", text, **kwargs)

    __slots__ = (
        "__weakref__",
        "_close_result_tabs",
        "_dialogs",
        "_file_icon_provider",
        "_files_model",
        "_files_tree",
        "_fmt_int",
        "_fmt_path",
        "_fmt_time",
        "_logger",
        "_open_any",
        "_parent",
        "_rename_file",
        "_set_status",
    )

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------
    def __init__(
        self,
        *,
        parent_widget: QWidget,
        files_tree: QTreeView,
        files_model: QFileSystemModel,
        open_any: Callable[[Path], None],
        close_result_tabs: Callable[[str], None],
        rename_file: Callable[[Path, str], tuple[bool, str | None]],
        set_status: Callable[[str, int | None], None],
        file_icon_provider,
        dialogs: DialogService | None = None,
        logger: logging.Logger | None = None,
    ):
        """Initialize the file panel controller.

        Args:
            parent_widget: Parent widget used for dialogs and status messages.
            files_tree: Tree view showing the file system.
            files_model: File system model backing the tree view.
            open_any: Callback for opening any file type.
            close_result_tabs: Callback for closing result tabs.
            rename_file: Callback for renaming files.
            set_status: Callback for status-bar updates.
            file_icon_provider: Provider used to resolve file icons.
            dialogs: Optional dialog service for UI prompts and confirmations.
            logger: Optional logger instance.
        """
        self._parent = parent_widget
        self._files_tree = files_tree
        self._files_model = files_model
        self._open_any = open_any
        self._close_result_tabs = close_result_tabs
        self._rename_file = rename_file
        self._set_status = set_status
        self._file_icon_provider = file_icon_provider
        self._dialogs = dialogs if dialogs is not None else QtDialogService()
        self._logger = logger if logger is not None else logging.getLogger("applogger.ui")

        # Connect UI signals
        self._files_tree.doubleClicked.connect(self._on_file_double_clicked)
        self._files_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._files_tree.customContextMenuRequested.connect(self._on_context_menu)

    # ==================================================================
    # Settings
    # ==================================================================

    def reload_settings(self, settings: dict) -> None:
        """Reload controller state from updated application settings.

        Args:
            settings: Updated application settings dictionary.
        """
        from expo_jbm329.utils.path_manager import get_documents_dir

        try:
            # Update root folder based on new settings
            root_dir = str(get_documents_dir(settings))
            root_index = self._files_model.index(root_dir)
            self._files_tree.setRootIndex(root_index)
            self._logger.debug(
                "FilePanelController: settings reloaded (root_dir=%s)",
                fmt_path(root_dir)
            )

        except Exception as e:
            self._logger.exception("FilePanelController: failed to reload settings: %s", e)

    def update_icons(self):
        """Refresh file icons after a theme or icon-provider change."""
        try:
            self._logger.debug("FilePanelController: updating icons")
            self._files_model.setIconProvider(self._file_icon_provider)

            vp = self._files_tree.viewport()
            if vp is not None:
                vp.update()

            self._logger.info("FilePanelController: icons refreshed due to theme change.")
        except Exception as e:
            self._logger.exception("FilePanelController: failed to update icons: %s", e)

    # ==================================================================
    # Double click handling
    # ==================================================================
    def _on_file_double_clicked(self, index: QModelIndex):
        """Handle double-clicks on files in the tree view.

        Args:
            index: Model index of the clicked item.
        """
        path_str = self._files_model.filePath(index)
        if not path_str:
            return

        path = Path(path_str)
        if path.is_dir():
            return
        p = fmt_path(path)
        self._logger.debug("FilePanelController: double-click detected (path=%s)", p)
        self._open_any(path)

    # ==================================================================
    # Context menu
    # ==================================================================
    def _on_context_menu(self, pos: QPoint):
        """Show the file panel context menu.

        Args:
            pos: Position of the context-menu request in view coordinates.
        """
        index = self._files_tree.indexAt(pos)
        if not index.isValid():
            return

        path_str = self._files_model.filePath(index)
        if not path_str:
            return

        path = Path(path_str)
        if path.is_dir():
            return
        p = fmt_path(path)
        self._logger.debug("FilePanelController: context menu requested (path=%s)", p)
        file_type = classify_file(path)
        self._logger.debug("FilePanelController: context menu file type (path=%s, type=%s)", p, file_type)

        # Build menu
        menu = QMenu(self._parent)
        header = QAction(path.name, menu)
        menu.addAction(header)
        header.setEnabled(False)
        menu.addSeparator()

        act_open = QAction(self._tr(self.TR_OPEN), menu)
        menu.addAction(act_open)
        if file_type != "unknown":
            act_open.setEnabled(True)
        else:
            act_open.setEnabled(False)

        act_rename = QAction(self._tr(self.TR_RENAME), menu)
        menu.addAction(act_rename)
        act_delete = QAction(self._tr(self.TR_DELETE), menu)
        menu.addAction(act_delete)

        vp = self._files_tree.viewport()
        if vp is None:
            return

        chosen = menu.exec(vp.mapToGlobal(pos))

        if not chosen:
            self._logger.debug("FilePanelController: context menu dismissed (path=%s)", p)
            return

        # Rename
        if chosen == act_rename:
            self._rename(index)
            return

        # Delete
        if chosen == act_delete:
            self._delete_file(index)
            return

        # Open (any supported type)
        if chosen == act_open:
            self._open_any(path)

    # ==================================================================
    # Rename file
    # ==================================================================
    def _rename(self, index: QModelIndex):
        """Handle rename requests from the context menu.

        Args:
            index: Model index of the file to rename.
        """
        path_str = self._files_model.filePath(index)
        if not path_str:
            return

        old_path = Path(path_str)
        p_old = fmt_path(old_path)
        self._logger.debug("FilePanelController: rename requested (path=%s)", p_old)
        if not old_path.exists() or not old_path.is_file():
            self._logger.info("FilePanelController: rename aborted, file missing (path=%s)", p_old)
            self._set_status(self._tr(self.TR_FILE_NO_LONGER_EXISTS), 6000)
            self._dialogs.info(
                parent=self._parent,
                title=self._tr(self.TR_RENAME_FILE),
                text=self._tr(self.TR_FILE_NO_LONGER_EXISTS)
            )
            return
        new_name, ok = self._dialogs.prompt_text(
            parent=self._parent,
            title=self._tr(self.TR_RENAME_FILE),
            label=self._tr(self.TR_NEW_FILE_NAME),
            default=old_path.name
        )

        if not ok or not new_name.strip():
            self._logger.debug("FilePanelController: rename cancelled by user (path=%s)", p_old)
            return

        self._logger.info("FilePanelController: renaming file (%s → %s)", p_old, fmt_path(new_name))
        ok2, err = self._rename_file(old_path, new_name)
        if not ok2:
            if err is None:
                err = ""
            self._logger.error("FilePanelController: rename failed (path=%s, err=%s)", p_old, err)
            self._set_status(self._tr(self.TR_FAILED_TO_RENAME_FILE), 8000)
            text = self._tr_fmt(self.TR_SOMETHING_WENT_WRONG_RENAME_FILE, error=err)

            self._dialogs.critical(
                parent=self._parent,
                title=self._tr(self.TR_FAILURE),
                text=text
            )
        else:
            self._logger.info("FilePanelController: rename completed (%s → %s)", p_old, fmt_path(new_name))

    # ==================================================================
    # Delete file
    # ==================================================================
    def _delete_file(self, index: QModelIndex):
        """Delete a file after user confirmation.

        Args:
            index: Model index of the file to delete.
        """
        path_str = self._files_model.filePath(index)
        if not path_str:
            return

        path = Path(path_str)
        p = fmt_path(path)

        self._logger.debug("FilePanelController: delete requested (path=%s)", p)

        if not path.exists() or not path.is_file():
            self._logger.info("Delete aborted, file missing (path=%s)", p)
            self._set_status(self._tr(self.TR_FILE_NO_LONGER_EXISTS), 6000)
            self._dialogs.info(
                parent=self._parent,
                title=self._tr(self.TR_DELETE_FILE),
                text=self._tr(self.TR_FILE_NO_LONGER_EXISTS)
            )
            return

        if not self._confirm_delete(path):
            self._logger.debug("FilePanelController: delete cancelled by user (path=%s)", p)
            return

        # Close tabs showing this file (based on title = filename)
        self._close_result_tabs(path.name)

        self._set_status(self._tr_fmt(self.TR_DELETING_FILE, file=path.name), 0)

        ok = self._delete_via_model(index)

        if ok:
            self._logger.info("FilePanelController: file deleted (path=%s)", p)

            self._set_status(self._tr_fmt(self.TR_FILE_DELETED, file=path.name), 8000)

        else:
            self._logger.error("FilePanelController: delete failed (path=%s)", p)

            self._set_status(self._tr(self.TR_FAILED_TO_DELETE_FILE), 8000)

            err_msg = self._tr_fmt(self.TR_SOMETHING_WENT_WRONG_DELETE_FILE, path=str(path))
            self._dialogs.critical(
                parent=self._parent,
                title=self._tr(self.TR_FAILURE),
                text=err_msg
            )

    # ------------------------------------------------------------------
    def _confirm_delete(self, path: Path) -> bool:
        """Show a confirmation dialog before deleting a file.

        Args:
            path: File path to be deleted.

        Returns:
            True if the user confirms deletion, otherwise False.
        """
        p = fmt_path(path)
        self._logger.debug("FilePanelController: confirm delete dialog (path=%s)", p)

        size_str = fmt_path_size(path)

        result = self._dialogs.confirm_delete(
            parent=self._parent,
            title=self._tr(self.TR_CONFIRM_DELETE),
            name=path.name,
            full_path=str(path),
            size_hint=size_str or None,
        )
        self._logger.debug("FilePanelController: confirm delete result (path=%s, ok=%s)", p, result)
        return result

    # ------------------------------------------------------------------

    def _delete_via_model(self, index: QModelIndex) -> bool:
        """Delete a file using the model, with unlink fallback.

        Args:
            index: Model index of the file to delete.

        Returns:
            True if deletion succeeds, otherwise False.
        """
        try:
            p = Path(self._files_model.filePath(index))
            fp = fmt_path(p)
        except Exception:
            self._logger.error("FilePanelController: delete-via-model: failed to resolve path")
            return False

        self._logger.debug("FilePanelController: attempting delete via model (path=%s)", fp)

        try:
            ok = self._files_model.remove(index)
            if ok:
                self._logger.debug("FilePanelController: delete-via-model succeeded (path=%s)", fp)
                return True
        except Exception:
            self._logger.debug("FilePanelController: delete-via-model failed, trying unlink (path=%s)", fp)
            pass

        # Fallback: try direct unlink to get a precise exception (e.g., PermissionError)
        try:
            p.unlink()
            self._logger.debug("FilePanelController: delete-via-unlink succeeded (path=%s)", fp)
            return True
        except PermissionError as e:
            self._logger.error(
                "FilePanelController: delete-via-unlink permission error (path=%s, err=%s)", fp, e
            )
            err_msg = (
                self._tr_fmt(
                    self.TR_SOMETHING_WENT_WRONG_DELETE_FILE_ERROR,
                    file=p.name,
                    error=str(e)
                )
            )

            self._dialogs.warn(
                parent=self._parent,
                title=self._tr(self.TR_FAILURE),
                text=err_msg
            )
            return False
        except Exception as e:
            self._logger.error("FilePanelController: delete-via-unlink failed (path=%s, err=%s)", fp, e)
            err_msg = self._tr_fmt(
                self.TR_SOMETHING_WENT_WRONG_DELETE_FILE_ERROR,
                file=p.name,
                error=str(e),
            )
            self._dialogs.warn(
                parent=self._parent,
                title=self._tr(self.TR_FAILURE),
                text=err_msg
            )
            return False
