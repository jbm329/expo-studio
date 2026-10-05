"""Select explicitly collected Qt binaries for the desktop application."""

from __future__ import annotations

from pathlib import PureWindowsPath
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable


def filter_qt_binaries(binaries: Iterable[tuple[str, str]]) -> list[tuple[str, str]]:
    """Exclude unused Qt SQL-driver plugins before dependency analysis.

    These plugins can pull database client DLLs from unrelated applications on
    the build machine. Expo uses Python database drivers, not Qt SQL drivers.

    Args:
        binaries: Source/destination pairs returned by Qt binary collection.

    Returns:
        Retained pairs in their original order. Both path separator styles are
        supported so the collection policy can be tested on any platform.
    """
    retained: list[tuple[str, str]] = []
    for source, destination in binaries:
        parts = tuple(part.casefold() for part in PureWindowsPath(source).parts)
        is_sql_plugin = any(parts[index : index + 2] == ("plugins", "sqldrivers") for index in range(len(parts) - 1))
        if not is_sql_plugin:
            retained.append((source, destination))
    return retained
