"""Language enum."""

from enum import StrEnum


class Language(StrEnum):
    """Supported languages."""

    SWEDISH = "sv"
    ENGLISH = "en"
    GERMAN = "de"
    FRENCH = "fr"
    ITALIAN = "it"
    SPANISH = "es"
    POLISH = "pl"

    @property
    def display_name(self) -> str:
        """Language name for display."""
        return {
            Language.SWEDISH: "Svenska",
            Language.ENGLISH: "English",
            Language.GERMAN: "Deutsch",
            Language.FRENCH: "Français",
            Language.ITALIAN: "Italiano",
            Language.SPANISH: "Español",
            Language.POLISH: "Polski",
        }[self]
