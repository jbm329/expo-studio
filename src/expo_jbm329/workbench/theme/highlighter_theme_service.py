"""Theme resolution service for SQL syntax highlighting.

This module resolves the active syntax highlighter theme from application
settings and the current OS theme, and emits updates when the selected theme
changes.
"""
from __future__ import annotations

import logging

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import QApplication

from expo_jbm329.workbench.highlighter.sql_highlighter import Theme
from expo_jbm329.workbench.theme.highlighter_theme_repository import HighlighterThemeRepository
from expo_jbm329.workbench.theme.theme_service import ThemeService


class HighlighterThemeService(QObject):
    """Resolve and publish the active syntax highlighter theme."""
    __slots__ = (
        "_current_theme",
        "_logger",
        "_repo",
        "_settings_theme",
        "_settings_theme_default",
    )

    theme_changed = pyqtSignal(Theme)

    def __init__(
            self,
            theme_service: ThemeService,
            logger: logging.Logger | None = None
    ) -> None:
        """Initialize the highlighter theme service.

        Args:
            theme_service: Service that emits application theme changes.
            logger: Optional logger instance.
        """
        super().__init__()

        self._repo = HighlighterThemeRepository()
        self._logger = logger if logger else logging.getLogger("applogger.ui")

        # Track last resolved theme to avoid duplicate signals
        self._current_theme: Theme | None = None

        self._settings_theme_default: str = "system"
        self._settings_theme: str = self._settings_theme_default

        theme_service.theme_changed.connect(self._on_gui_theme_changed)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _os_is_dark(self) -> bool:
        """Return whether the operating system is using a dark theme.

        Returns:
            True if the OS theme is dark, otherwise False.
        """
        cs = QApplication.styleHints().colorScheme()
        return cs == Qt.ColorScheme.Dark

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def resolve_theme(self) -> Theme:
        """Resolve the active theme object.

        The resolution order is:
            1. System theme, mapped from OS light/dark mode.
            2. Explicit built-in light/dark theme.
            3. Custom theme loaded from the repository.
            4. Fallback to dark.

        Returns:
            The resolved Theme object.
        """
        # Case 1: system → dynamic based on OS
        if self._settings_theme == "system":
            os_dark = self._os_is_dark()
            chosen = "dark" if os_dark else "light"
            return self._repo.get(chosen)

        # Case 2: built‑in light/dark
        if self._settings_theme in ("light", "dark"):
            self._logger.debug("HighlighterThemeService: using explicit theme=%s", self._settings_theme)
            return self._repo.get(self._settings_theme)

        # Case 3: custom JSON
        if self._repo.has(self._settings_theme):
            self._logger.debug("HighlighterThemeService: using custom theme=%s", self._settings_theme)
            return self._repo.get(self._settings_theme)

        # Fallback
        self._logger.warning(
            "HighlighterThemeService: unknown theme '%s', falling back to 'dark'",
            self._settings_theme,
        )
        return self._repo.get("dark")

    def apply_theme(self) -> None:
        """Resolve the theme and emit a change signal if it differs.

        This is called on startup and whenever settings or OS theme changes.
        """
        theme = self.resolve_theme()

        # Not the same object?
        if theme is not self._current_theme:
            self._current_theme = theme
            self._logger.info("HighlighterThemeService: theme changed → '%s'", theme.friendly_name)
            self.theme_changed.emit(theme)

    def available_themes(self) -> list[str]:
        """Return the available theme keys for UI selection.

        Returns:
            A sorted list of theme names, including "system" first.
        """
        names = list(self._repo.list_themes().keys())
        names.sort()
        return ["system", *names]

    def available_themes_with_labels(self) -> list[tuple[str, str]]:
        """Return theme keys paired with user-facing labels.

        Returns:
            A list of (theme_key, display_label) tuples, including "system".
        """
        pairs = [("system", "System")]

        for key, theme in self._repo.list_themes().items():
            pairs.append((key, theme.friendly_name))

        return pairs

    # ------------------------------------------------------------------
    # OS theme change handler
    # ------------------------------------------------------------------
    def _on_gui_theme_changed(self, gui_theme: str):
        """Re-apply the theme when the GUI theme changes.

        Args:
            gui_theme: Name of the GUI theme that was applied.
        """
        if self._settings_theme == "system":
            self.apply_theme()

    # ------------------------------------------------------------------
    # Settings update API
    # ------------------------------------------------------------------
    def reload_settings(self, settings: dict) -> None:
        """Reload the theme setting from application settings.

        Args:
            settings: Application settings dictionary.
        """
        try:
            workbench_settings = settings.get("workbench", {}) or {}
            val = workbench_settings.get("highlighter_theme", self._settings_theme_default)
            self._settings_theme = (val or self._settings_theme_default).strip()

            self._logger.debug(
                "HighlighterThemeService: settings reloaded (theme=%s)",
                self._settings_theme,

            )
            self.apply_theme()
        except Exception:
            self._logger.exception("HighlighterThemeService: failed reloading settings")

