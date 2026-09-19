"""File dialog service for user interaction.

This module provides a unified interface for displaying file and directory
dialogs to the user, allowing them to open files, save files, and select
directories.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from PyQt6.QtWidgets import QFileDialog, QWidget


@dataclass(slots=True, frozen=True)
class OpenFileRequest:
    """Request parameters for opening a file.

    Attributes:
        title: The dialog window title.
        initial_path: The directory or file path to show initially.
        filter_str: File type filters (e.g., "SQL files (*.sql)").
    """

    title: str
    initial_path: str
    filter_str: str


@dataclass(slots=True, frozen=True)
class SaveFileRequest:
    """Request parameters for saving a file.

    Attributes:
        title: The dialog window title.
        initial_path: The directory or file path to show initially.
        filter_str: File type filters.
    """

    title: str
    initial_path: str
    filter_str: str


@dataclass(slots=True, frozen=True)
class DirectoryRequest:
    """Request parameters for selecting a directory.

    Attributes:
        title: The dialog window title.
        initial_path: The directory path to show initially.
    """

    title: str
    initial_path: str


@runtime_checkable
class FileDialogService(Protocol):
    """Abstraction for file and directory dialogs.

    Allows controllers to request file/directory selections without being
    coupled to the specific UI implementation.
    """

    def get_open_filename(self, parent: QWidget, req: OpenFileRequest) -> tuple[str, str]:
        """Request the user to select a file for opening.

        Args:
            parent: The parent widget for the dialog.
            req: The open file request parameters.

        Returns:
            A tuple of (selected filename, selected filter).
            Returns ("", "") if the user cancels.
        """
        ...

    def get_save_filename(self, parent: QWidget, req: SaveFileRequest) -> tuple[str, str]:
        """Request the user to select a filename for saving.

        Args:
            parent: The parent widget for the dialog.
            req: The save file request parameters.

        Returns:
            A tuple of (selected path, selected filter).
            Returns ("", "") if the user cancels.
        """
        ...

    def get_existing_directory(self, parent: QWidget, req: DirectoryRequest) -> str:
        """Request the user to select an existing directory.

        Args:
            parent: The parent widget for the dialog.
            req: The directory request parameters.

        Returns:
            The selected directory path, or an empty string if the user cancels.
        """
        ...


class QtFileDialogService(FileDialogService):
    """Production implementation of FileDialogService using real QFileDialog."""

    def get_open_filename(self, parent: QWidget, req: OpenFileRequest) -> tuple[str, str]:
        """Show a file open dialog.

        Args:
            parent: The parent widget.
            req: The open file request parameters.

        Returns:
            A tuple of (selected filename, selected filter).
        """
        return QFileDialog.getOpenFileName(
            parent,
            req.title,
            req.initial_path,
            req.filter_str,
        )

    def get_save_filename(self, parent: QWidget, req: SaveFileRequest) -> tuple[str, str]:
        """Show a file save dialog.

        Args:
            parent: The parent widget.
            req: The save file request parameters.

        Returns:
            A tuple of (selected path, selected filter).
        """
        path, selected = QFileDialog.getSaveFileName(
            parent,
            req.title,
            req.initial_path,
            req.filter_str,
        )
        return path, selected

    def get_existing_directory(self, parent: QWidget, req: DirectoryRequest) -> str:
        """Show a directory selection dialog.

        Args:
            parent: The parent widget.
            req: The directory request parameters.

        Returns:
            The selected directory path.
        """
        path = QFileDialog.getExistingDirectory(
            parent,
            req.title,
            req.initial_path,
        )
        return path or ""


class NullFileDialogService(FileDialogService):
    """Test implementation of FileDialogService.

    Never opens windows. Logs calls and can be configured to return
    specific selections for testing purposes.
    """

    def __init__(self) -> None:
        """Initialize the null file dialog service."""
        self.calls: list[OpenFileRequest | SaveFileRequest | DirectoryRequest] = []
        self._queue_open: list[tuple[str, str]] = []
        self._queue_save: list[tuple[str, str]] = []
        self._queue_dir: list[str] = []

    # --- Open ----------------------------------------------------
    def enqueue_open_response(self, path: str, selected_filter: str = "") -> None:
        """Prepare the next return value for get_open_filename.

        Args:
            path: The file path to return.
            selected_filter: The filter to return.
        """
        self._queue_open.append((path, selected_filter))

    def get_open_filename(self, parent: QWidget, req: OpenFileRequest) -> tuple[str, str]:
        """Simulate a file open dialog.

        Args:
            parent: The parent widget.
            req: The open file request parameters.

        Returns:
            The enqueued response or ("", "").
        """
        self.calls.append(req)
        if self._queue_open:
            return self._queue_open.pop(0)
        return "", ""

    # --- Save ----------------------------------------------------
    def enqueue_save_response(self, path: str, selected_filter: str = "") -> None:
        """Prepare the next return value for get_save_filename.

        Args:
            path: The file path to return.
            selected_filter: The filter to return.
        """
        self._queue_save.append((path, selected_filter))

    def get_save_filename(self, parent: QWidget, req: SaveFileRequest) -> tuple[str, str]:
        """Simulate a file save dialog.

        Args:
            parent: The parent widget.
            req: The save file request parameters.

        Returns:
            The enqueued response or ("", "").
        """
        self.calls.append(req)
        if self._queue_save:
            return self._queue_save.pop(0)
        # Default: simulate abort
        return "", ""

    def enqueue_directory_response(self, path: str) -> None:
        """Prepare the next return value for get_existing_directory.

        Args:
            path: The directory path to return.
        """
        self._queue_dir.append(path)

    # --- Directory ----------------------------------------------
    def get_existing_directory(self, parent: QWidget, req: DirectoryRequest) -> str:
        """Simulate a directory selection dialog.

        Args:
            parent: The parent widget.
            req: The directory request parameters.

        Returns:
            The enqueued response or "".
        """
        self.calls.append(req)
        if self._queue_dir:
            return self._queue_dir.pop(0)
        return ""  # simulate cancel
