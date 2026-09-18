"""Repository for syntax highlighter themes.

This module provides a repository that loads built-in themes and discovers
custom themes from the theme directory.
"""
from __future__ import annotations

from expo_jbm329.utils.path_manager import get_theme_root
from expo_jbm329.workbench.highlighter.sql_highlighter import Theme
from expo_jbm329.workbench.theme.themes import builtins
from expo_jbm329.workbench.theme.themes.json_loader import load_theme_from_json


class HighlighterThemeRepository:
    """Load, store, and look up available syntax highlighter themes."""
    def __init__(self) -> None:
        """Initialize the repository and load all available themes."""
        self._themes: dict[str, Theme] = {}
        self._base_dir = get_theme_root()
        self._load_all()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _load_all(self) -> None:
        """Load built-in themes and JSON themes."""
        self._themes.clear()

        # --- built-ins ---
        # Use lower-case keys
        for name, value in vars(builtins).items():
            if isinstance(value, Theme):
                var_name = name.lower()

                # Normalize names
                if var_name == "light_theme":
                    key = "light"
                elif var_name == "dark_theme":
                    key = "dark"
                else:
                    key = var_name
                self._themes[key] = value

        # --- JSON themes ---
        custom_dir = self._base_dir / "themes" / "custom"

        if not custom_dir.exists():
            return

        for file in custom_dir.glob("*.json"):
            name = file.stem.lower().strip()

            try:
                theme = load_theme_from_json(file)
            except Exception as ex:
                # Skip broken themes, do not crash the app
                print(f"[theme] Skipping invalid theme '{file.name}': {ex}")
                continue

            self._themes[name] = theme

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def list_themes(self) -> dict[str, Theme]:
        """Return all available themes as a copy of the internal mapping.

        Returns:
            A dictionary mapping theme names to Theme objects.
        """
        return dict(self._themes)

    def get(self, name: str) -> Theme:
        """Return a theme by name.

        Args:
            name: Theme name, matched case-insensitively.

        Returns:
            The requested Theme object.

        Raises:
            KeyError: If the theme does not exist.
        """
        key = name.lower().strip()
        return self._themes[key]

    def has(self, name: str) -> bool:
        """Return whether a theme with the given name exists.

        Args:
            name: Theme name, matched case-insensitively.

        Returns:
            True if the theme exists, otherwise False.
        """
        return name.lower().strip() in self._themes
