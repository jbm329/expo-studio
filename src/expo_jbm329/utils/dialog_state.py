"""Dialog state."""
from pathlib import Path

from PyQt6.QtCore import QSettings


class DialogState:
    """Persisted dialog state using QSettings."""

    def __init__(self) -> None:
        """Initialize the dialog state."""
        self._settings = QSettings("Expo", "ExpoStudio")

    def get_dir(self, key: str, fallback: Path) -> Path:
        """Get a directory from the dialog state."""
        value = self._settings.value(key)
        if value:
            p = Path(value)
            if p.exists():
                return p
        return fallback

    def set_dir(self, key: str, path: Path) -> None:
        """Set a directory in the dialog state."""
        self._settings.setValue(key, str(path))
