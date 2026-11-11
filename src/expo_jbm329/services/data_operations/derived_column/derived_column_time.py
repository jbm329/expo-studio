"""Qt-free, vectorized datetime hierarchy extraction."""

from dataclasses import dataclass

import pandas as pd

from expo_jbm329.services.data_operations.derived_column.derived_column_expression import (
    ExpressionOperation as Op,
)

_MONTH_COUNT = 12


def _validate_labels(labels: object) -> None:
    if (
        not isinstance(labels, tuple)
        or len(labels) != _MONTH_COUNT
        or not all(isinstance(label, str) and label.strip() for label in labels)
    ):
        message = "Month labels must contain twelve nonempty strings in immutable tuples."
        raise ValueError(message)


@dataclass(frozen=True, slots=True)
class MonthLabels:
    """Captured standalone month names, independent of mutable locale state."""

    full: tuple[str, ...] = (
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    )
    short: tuple[str, ...] = (
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
    )

    def __post_init__(self) -> None:
        """Reject incomplete or mutable label snapshots."""
        for labels in (self.full, self.short):
            _validate_labels(labels)


DEFAULT_MONTH_LABELS = MonthLabels()


def _digits(values: pd.Series, width: int = 1) -> pd.Series:
    return values.astype("Int64").astype(pd.StringDtype()).str.zfill(width)


def extract_time_part(values: pd.Series, operation: Op, labels: MonthLabels) -> pd.Series:
    """Extract a validated time function in the source column's stored timezone.

    Args:
        values: Datetime values with a positional index; missing dates are retained.
        operation: A supported time hierarchy function.
        labels: Captured standalone full and abbreviated month names.

    Returns:
        Nullable text or numeric values on the input index, without parsing cells.

    Raises:
        ValueError: If operation is not a time hierarchy function.
    """
    match operation:
        case Op.TIME:
            return _digits(values.dt.hour, 2) + ":" + _digits(values.dt.minute, 2)
        case Op.WEEK | Op.WEEK_NUMBER | Op.ISO_YEAR | Op.YEAR_WEEK:
            calendar = values.dt.isocalendar()
            if operation == Op.WEEK_NUMBER:
                return pd.Series(calendar.week, dtype="Int64")
            if operation == Op.ISO_YEAR:
                return pd.Series(calendar.year, dtype="Int64")
            week = "W" + _digits(calendar.week, 2)
            return _digits(calendar.year, 4) + "-" + week if operation == Op.YEAR_WEEK else week
        case Op.MONTH | Op.MONTH_SHORT:
            names = labels.full if operation == Op.MONTH else labels.short
            return pd.Series(values.dt.month.map(dict(enumerate(names, start=1))), dtype=pd.StringDtype())
        case Op.MONTH_NUMBER:
            return pd.Series(values.dt.month, dtype="Int64")
        case Op.YEAR:
            return pd.Series(values.dt.year, dtype="Int64")
        case Op.YEAR_MONTH:
            return _digits(values.dt.year, 4) + "-" + _digits(values.dt.month, 2)
        case Op.QUARTER | Op.QUARTER_NUMBER | Op.YEAR_QUARTER:
            quarter = values.dt.quarter
            if operation == Op.QUARTER_NUMBER:
                return pd.Series(quarter, dtype="Int64")
            label = "Q" + _digits(quarter)
            return _digits(values.dt.year, 4) + "-" + label if operation == Op.YEAR_QUARTER else label
        case Op.TERTIAL | Op.TERTIAL_NUMBER | Op.YEAR_TERTIAL:
            tertial = (values.dt.month - 1) // 4 + 1
            if operation == Op.TERTIAL_NUMBER:
                return pd.Series(tertial, dtype="Int64")
            label = "T" + _digits(tertial)
            return _digits(values.dt.year, 4) + "-" + label if operation == Op.YEAR_TERTIAL else label
        case _:
            message = f"Unsupported time hierarchy operation: {operation}"
            raise ValueError(message)
