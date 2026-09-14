"""Translation service."""
from __future__ import annotations

import logging

from PyQt6.QtCore import QCoreApplication, QObject, QTranslator

from expo_jbm329.i18n.language import Language
from expo_jbm329.utils.format_utils import fmt_path
from expo_jbm329.utils.path_manager import get_i18n_root


class TranslationService(QObject):
    """Application-wide internationalization (i18n) service.

    This service manages loading and switching Qt translation files (.qm)
    at runtime based on application settings. It is designed to be owned
    by the application service container and reacts to settings updates
    via the settings bus.

    Notes:
        - Requires a Q(Core)Application instance to exist before
          switching languages.
        - This service does not update UI widgets directly; callers are
          responsible for triggering UI retranslation.
    """
    __slots__ = (
        "_current_language",
        "_locales_dir",
        "_logger",
        "_translator"
    )

    def __init__(self, logger: logging.Logger | None) -> None:
        """Initialize the translation service.

        Args:
            logger: Optional logger instance used for diagnostics and
                informational messages. If not provided, the UI application
                logger is used.
        """
        super().__init__()
        self._translator = QTranslator()
        self._locales_dir = get_i18n_root() / "locales"
        self._current_language: str | None = None
        self._logger = logger if logger else logging.getLogger("applogger.ui")

    def reload_settings(self, settings: dict) -> None:
        """Reload language configuration from application settings.

        This method is intended to be registered as a subscriber to the
        settings service. It extracts the language value from the workbench
        configuration and switches language if it has changed.

        Expected settings structure:
            settings["workbench"]["language"] -> str

        Args:
            settings: The complete application settings dictionary.
        """
        try:
            wb = settings.get("workbench", {}) or {}

            lang = wb.get("language", Language.ENGLISH.value)
            lang = lang.strip().lower()

            if lang not in {_lang.value for _lang in Language}:
                return

            if not isinstance(lang, str):
                return

            if lang == self._current_language:
                return

            self.switch_language(lang)

        except Exception as exc:
            self._logger.exception("TranslationService: failed to reload language: %s", exc)

    def switch_language(self, language: str) -> None:
        """"Switch the application language at runtime.

        Loads the corresponding Qt translation file (``app_<language>.qm``)
        from the locales directory and installs it into the current
        QCoreApplication.

        Args:
            language: ISO 639-1 language code (e.g. ``'en'``, ``'sv'``).

        Notes:
            If the translation file cannot be loaded, the current language
            remains unchanged.
        """
        if language == self._current_language:
            return

        QCoreApplication.removeTranslator(self._translator)

        qm_path = self._locales_dir / f"app_{language}.qm"

        if not qm_path.exists():
            self._logger.warning("TranslationService: missing translation file: %s", fmt_path(qm_path))
            return

        if self._translator.load(str(qm_path)):
            QCoreApplication.installTranslator(self._translator)
            self._current_language = language
            self._logger.info("TranslationService: language switched to '%s'", language)
