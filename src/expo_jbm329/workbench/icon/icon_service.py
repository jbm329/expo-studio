"""Theme-aware icon service for the workbench UI.

This module provides icons based on the currently resolved GUI theme and
refreshes cached icon usage whenever the theme changes.
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap, QPixmapCache

from expo_jbm329.workbench.theme.theme_service import ThemeService


class IconService(QObject):
    """Provide theme-aware icons and notify listeners when they change."""

    icons_updated = pyqtSignal()

    def __init__(self, theme_service: ThemeService, logger: logging.Logger | None = None):
        """Initialize the icon service.

        Args:
            theme_service: Service that resolves and emits the current theme.
            logger: Optional logger instance.
        """
        super().__init__()
        self._theme_service = theme_service
        self._logger = logger or logging.getLogger("applogger.ui")

        # react to GUI theme changes
        theme_service.theme_changed.connect(self._on_theme_changed)

    def _on_theme_changed(self, theme: str) -> None:
        """Handle a theme change emitted by the theme service.

        Args:
            theme: The newly applied theme name.
        """
        self._logger.info("IconService: icons updated due to theme change → '%s'", theme)

        # Clear Qt's global pixmap cache
        QPixmapCache.clear()

        # Notify UI
        self.icons_updated.emit()

    def _make_disabled_pixmap(self, pix: QPixmap, *, dark_mode: bool) -> QPixmap:
        """Create a disabled-style pixmap variant.

        Args:
            pix: Source pixmap.
            dark_mode: Whether the current theme is dark.

        Returns:
            A disabled-looking pixmap derived from the source pixmap.
        """
        disabled = QPixmap(pix.size())
        disabled.fill(Qt.GlobalColor.transparent)

        p = QPainter(disabled)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.drawPixmap(0, 0, pix)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceAtop)

        overlay = QColor(0, 0, 0, 120) if dark_mode else QColor(255, 255, 255, 120)

        p.fillRect(disabled.rect(), overlay)
        p.end()

        return disabled

    def get(self, name: str) -> QIcon:
        """Return a themed icon from the resource system.

        Args:
            name: Logical icon name without file extension.

        Returns:
            A QIcon built from the current theme's resource path.
        """
        theme = self._theme_service.resolve_theme()
        path = f":/icons/{theme}/{name}.png"

        # load normal pixmap
        base_pix = QPixmap(path)

        # Force new pixmap generation by using addFile()
        icon = QIcon()
        icon.addPixmap(base_pix, QIcon.Mode.Normal, QIcon.State.Off)

        # create disabled variant
        dark_mode = (theme == "dark")
        disabled_pix = self._make_disabled_pixmap(base_pix, dark_mode=dark_mode)
        icon.addPixmap(disabled_pix, QIcon.Mode.Disabled, QIcon.State.Off)

        # DEBUG available if needed, but disabled by default
        # self._logger.debug("IconService.get('%s') → theme=%s, path=%s", name, theme, path)
        return icon

    def current_theme(self) -> str:
        """Return the currently resolved theme name."""
        return self._theme_service.resolve_theme()



