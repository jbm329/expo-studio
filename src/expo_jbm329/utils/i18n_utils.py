"""Internationalization (i18n) helpers.

Utilities for working safely and clearly with Qt's translation system.
"""

from __future__ import annotations

from PyQt6.QtCore import QCoreApplication


def tr(context: str, text: str) -> str:
    """Basic Qt translation wrapper.

    Args:
        context: Qt translation context (usually the class name).
        text: Source string to translate.

    Returns:
        Translated string.
    """
    return QCoreApplication.translate(context, text)


def tr_fmt(context: str, text: str, /, **kwargs) -> str:
    r"""Translate and format a string using named placeholders.

    Uses Python's ``str.format`` after Qt translation, avoiding
    positional placeholders like ``%1``.

    Example:
        tr_fmt(
            "FilePanelController",
            "The file can not be opened:\\n\\n{file}",
            file="data.csv",
        )

    Args:
        context: Qt translation context (usually the class name).
        text: Translatable source string containing named placeholders.
        **kwargs: Values to substitute into the translated string.

    Returns:
        Translated and formatted string. If formatting fails, returns
        the untranslated string.
    """
    translated = QCoreApplication.translate(context, text)

    if not kwargs:
        return translated

    try:
        return translated.format(**kwargs)
    except (
        AttributeError,
        ConnectionError,
        FileNotFoundError,
        IndexError,
        KeyError,
        LookupError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ):
        # UI must never crash due to translation formatting issues
        return translated
