"""Shared metadata for output-independent chart presentations."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Visible repeated headings are independent of captions and accessible names.
DEFAULT_WORKSHEET_HEADING = ""


@dataclass(frozen=True, slots=True)
class ChartNumericLocale:
    """Captured numeric separators, independent of Qt and mutable locale state."""

    decimal_separator: str = "."
    group_separator: str = ","
    group_integers: bool = True

    def count(self, value: int) -> str:
        """Format a count with the captured grouping separator."""
        return format(value, ",").replace(",", self.group_separator)

    def number(self, value: float, *, precision: int = 4) -> str:
        """Match the app's positional numeric chart labels at the given precision."""
        if np.isnan(value):
            return ""
        if float(value).is_integer():
            return self.count(int(value)) if self.group_integers else str(int(value))
        return str(np.format_float_positional(value, precision=precision, unique=False, trim="k")).replace(
            ".", self.decimal_separator
        )


DEFAULT_CHART_NUMERIC_LOCALE = ChartNumericLocale()


@dataclass(frozen=True, slots=True)
class ChartPresentationMetadata:
    """Worksheet, accessibility, and caption metadata for a chart presentation."""

    worksheet_heading: str
    accessible_name: str
    captions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Require a stable accessible identity while allowing a hidden worksheet heading."""
        if not self.accessible_name:
            message = "A chart presentation requires an accessible name."
            raise ValueError(message)
