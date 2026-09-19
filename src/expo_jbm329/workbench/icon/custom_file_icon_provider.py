"""Theme-aware file icon provider for the workbench file tree.

This module provides a QFileIconProvider implementation that resolves icons
through the application's IconService so file and folder icons can follow the
current GUI theme at runtime.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import override

from PyQt6.QtCore import QFileInfo
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QFileIconProvider, QStyle


def _normalize_ext(ext: str) -> str:
    """Normalize file extensions: ensure leading dot, lower-case."""
    if not ext:
        return ""
    s = ext.strip().lower()
    if not s:
        return ""
    if not s.startswith("."):
        s = "." + s
    return s


class CustomFileIconProvider(QFileIconProvider):
    """Provide themed icons for files, folders, and symbolic links."""

    __slots__ = (
        "_file_icon",
        "_folder_icon",
        "_icon_service",
        "_icons_by_ext",
        "_icons_by_multi_ext",
        "_link_icon",
    )

    def __init__(self, icon_service: object=None, logger: logging.Logger | None = None) -> None:
        """Initialize the icon provider.

        Args:
            icon_service: Service used to resolve themed icons.
            logger: Optional logger instance.
        """
        super().__init__()
        self._icon_service = icon_service
        self._logger = logger or logging.getLogger("applogger.ui")

        # These are set via update_theme()
        self._folder_icon = QIcon()
        self._file_icon = QIcon()
        self._link_icon = QIcon()

        # Extension maps (single + multi)
        self._icons_by_ext: dict[str, QIcon] = {}
        self._icons_by_multi_ext: dict[str, QIcon] = {}

    # ------------------------------------------------------------------ #
    # Theme update API (called by SqlEditor)
    # ------------------------------------------------------------------ #
    def update_theme(self) -> None:
        """Refresh all icons according to the current GUI theme."""
        theme = self._icon_service.current_theme()
        # Base icons
        self._folder_icon = self._icon_service.get("folder")
        self._file_icon = self._icon_service.get("generic_file")
        self._link_icon = self._icon_service.get("file_new")  # can be changed if desired

        self._logger.info("CustomFileIconProvider: file icons refreshed due to theme change → '%s'", theme)

        # Clear previous extension registrations
        self._icons_by_ext.clear()
        self._icons_by_multi_ext.clear()

        # Map extension → icon names from your QRC
        ext_map = {
            ".csv": "csv_file",
            ".xlsx": "excel_file",
            ".xls": "excel_file",
            ".df": "binary_file",
            ".sql": "code_file",
            ".html": "html_file",
            ".htm": "html_file",
            ".json": "json_file",
            ".xml": "generic_file",
            ".md": "generic_file",
            ".txt": "generic_file",
            ".pdf": "generic_file",
            ".png": "generic_file",
            ".jpg": "generic_file",
            ".jpeg": "generic_file",
            ".svg": "generic_file",
            ".zip": "generic_file",
            ".gz": "generic_file",
            ".parquet": "binary_file",
            ".feather": "binary_file",
            ".ft": "binary_file",
            ".pkl": "binary_file",
            ".qvd": "stat_file",
            ".dta": "stat_file",
            ".sav": "stat_file",
        }

        for ext, icon_name in ext_map.items():
            self._icons_by_ext[ext] = self._icon_service.get(icon_name)

        # Multi-extension support (optional)
        multi_map = {
            ".tar.gz": "generic_file",
            ".csv.gz": "generic_file",
        }

        for mext, icon_name in multi_map.items():
            self._icons_by_multi_ext[mext] = self._icon_service.get(icon_name)

    # ------------------------------------------------------------------ #
    # QFileIconProvider override
    # ------------------------------------------------------------------ #
    @override
    def icon(self, type_or_info: QFileIconProvider.IconType | QFileInfo) -> QIcon:
        """Return an icon for a file type or QFileInfo instance.

        Args:
            type_or_info: QFileIconProvider.IconType or QFileInfo input.

        Returns:
            The themed QIcon for the given item.
        """
        try:
            # Case 1: system type (Folder/File)
            if isinstance(type_or_info, QFileIconProvider.IconType):
                return self._icon_for_type(type_or_info)

            # Case 2: QFileInfo
            if isinstance(type_or_info, QFileInfo):
                info: QFileInfo = type_or_info

                if info.isDir():
                    return self._folder_icon

                if info.isSymLink():
                    return self._link_icon if not info.isDir() else self._folder_icon

                # Determine file icon by extension
                name = info.fileName() or ""

                icon = self._icon_for_name(name)

                return icon or self._file_icon

            # Fallback
            return super().icon(type_or_info)

        except Exception:  # noqa: BLE001
            return super().icon(type_or_info)

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _icon_for_type(self, t: QFileIconProvider.IconType) -> QIcon:
        """Return a default themed icon for a QFileIconProvider icon type.

        Args:
            t: QFileIconProvider icon type.

        Returns:
            The themed QIcon for the requested type.
        """
        if t == QFileIconProvider.IconType.Folder:
            return self._folder_icon
        if t == QFileIconProvider.IconType.File:
            return self._file_icon
        # Rare fallback
        return QApplication.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)

    def _icon_for_name(self, file_name: str) -> QIcon | None:
        """Resolve an icon using file-name extension rules.

        Args:
            file_name: File name to inspect.

        Returns:
            The matching QIcon, or None if no extension rule matches.
        """
        if not file_name:
            return None

        lower = file_name.lower()

        # Multi-extension first
        for key in sorted(self._icons_by_multi_ext.keys(), key=len, reverse=True):
            if lower.endswith(key):
                return self._icons_by_multi_ext[key]

        # Single extension
        ext = Path(file_name).suffix.lower()
        if ext in self._icons_by_ext:
            return self._icons_by_ext[ext]

        return None
