"""Language enum."""

from enum import StrEnum


class Language(StrEnum):
    """Supported languages."""

    SWEDISH = "sv"
    ENGLISH = "en"

    @property
    def display_name(self) -> str:
        """Language name for display."""
        return {
            Language.SWEDISH: "Svenska",
            Language.ENGLISH: "English",
        }[self]
