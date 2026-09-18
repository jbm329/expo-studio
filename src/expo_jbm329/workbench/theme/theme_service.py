"""Application theme service for the Expo workbench.

This module resolves the active GUI theme from application settings and the OS
theme, and emits notifications when the resolved theme changes.
"""
from __future__ import annotations

import logging

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import QApplication


class ThemeService(QObject):
    """Provide the resolved GUI theme and notify listeners when it changes."""
    __slots__ = (
        "_current_theme",
        "_logger",
        "_settings_theme",
        "_settings_theme_default"
    )

    theme_changed = pyqtSignal(str)  # "light" or "dark"

    def __init__(self, logger: logging.Logger | None = None):
        """Initialize the theme service.

        Args:
            logger: Optional logger instance.
        """
        super().__init__()
        self._logger = logger or logging.getLogger("applogger.ui")

        # Track current resolved theme ("light" or "dark")
        self._current_theme: str | None = None

        # Listen for OS-level theme changes
        QApplication.styleHints().colorSchemeChanged.connect(
            self._on_os_theme_changed
        )
        self._settings_theme_default: str = "system"
        self._settings_theme: str | None = self._settings_theme_default

        # Initial resolution
        QTimer.singleShot(0, self.apply_theme)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _os_is_dark(self) -> bool:
        """Return whether the OS theme is dark.

        Returns:
            True if Qt reports a dark color scheme, otherwise False.
        """
        return QApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def resolve_theme(self) -> str:
        """Resolve the effective GUI theme name.

        The value comes from application settings unless the configured theme is
        "system", in which case the OS color scheme determines the result.

        Returns:
            The resolved theme name: "light" or "dark".
        """
        if self._settings_theme == "system":
            os_dark = self._os_is_dark()
            return "dark" if os_dark else "light"

        self._logger.debug("ThemeService: using explicit theme=%s", self._settings_theme)
        return self._settings_theme

    def apply_theme(self) -> None:
        """Resolve the theme and emit a change signal if it changed."""
        new_theme = self.resolve_theme()

        if new_theme != self._current_theme:
            self._current_theme = new_theme
            self._logger.info("ThemeService: theme changed → '%s'", new_theme)
            self.theme_changed.emit(new_theme)

    # ----------------------------------------------------------------------
    # Settings reload
    # ----------------------------------------------------------------------
    def reload_settings(self, settings: dict) -> None:
        """Reload the theme setting from application settings.

        Args:
            settings: Application settings dictionary.
        """
        try:
            workbench_settings = settings.get("workbench", {}) or {}
            val = workbench_settings.get("theme", self._settings_theme_default)
            self._settings_theme = (val or self._settings_theme_default).strip()

            self._logger.debug(
                "ThemeService: settings reloaded (theme=%s)",
                self._settings_theme,

            )
            self.apply_theme()
        except Exception:
            self._logger.exception("ThemeService: failed reloading settings")

    # ------------------------------------------------------------------
    # OS theme change
    # ------------------------------------------------------------------
    def _on_os_theme_changed(self) -> None:
        """Re-apply the theme when the OS color scheme changes."""
        if self._settings_theme == "system":
            self.apply_theme()
