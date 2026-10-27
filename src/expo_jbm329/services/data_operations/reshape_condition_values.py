"""Cancellable distinct-value pages for the Reshape condition builder."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from decimal import Decimal
from time import perf_counter
from typing import TYPE_CHECKING

from expo_jbm329.services.data_operations.reshape_conditions import (
    ConditionError,
    ConditionProblem,
    ConditionValue,
    condition_value,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    import pandas as pd

VALUE_PAGE_SIZE = 100
_SCAN_CHUNK_SIZE = 2048
logger = logging.getLogger("applogger.service")


def _log_value_page(
    level: int,
    event: str,
    corr_id: str | None,
    metadata_format: str,
    *values: object,
) -> None:
    """Write a value-page summary without logging filter text or returned values."""
    metadata = metadata_format % values
    if corr_id is None:
        logger.log(level, "ReshapeConditionValues: %s (%s)", event, metadata)
    else:
        logger.log(level, "ReshapeConditionValues: %s (corr=%s, %s)", event, corr_id, metadata)


class ValueRequestCancelledError(Exception):
    """The caller superseded or closed a page request."""


@dataclass(frozen=True, slots=True)
class ValuePageRequest:
    """One immutable request in a rule's current generation."""

    column_position: int
    search: str = ""
    page: int = 0


@dataclass(frozen=True, slots=True)
class ValuePage:
    """One page of globally sorted distinct values."""

    entries: tuple[ConditionValue, ...]
    has_next: bool


def _value_sort_key(value: ConditionValue) -> tuple[int, Decimal, tuple[tuple[str, int], ...], str, str]:
    """Order numbers numerically, then other values by natural casefolded text."""
    if value.kind in {"integer", "float", "decimal"}:
        return (0, Decimal(value.text), (), value.text, value.kind)
    parts = tuple(
        ("", int(part)) if part.isascii() and part.isdecimal() else (part.casefold(), 0)
        for part in re.split(r"([0-9]+)", value.text)
    )
    return (1, Decimal(0), parts, value.text, value.kind)


def distinct_value_page(
    source: pd.DataFrame,
    request: ValuePageRequest,
    *,
    cancel_cb: Callable[[], bool] | None = None,
    corr_id: str | None = None,
) -> ValuePage:
    """Scan the fixed source for a page of distinct matching nonmissing values.

    Args:
        source: Read-only source captured for this Reshape session.
        request: Positional column, literal search, and zero-based page.
        cancel_cb: Optional cooperative cancellation predicate.
        corr_id: Optional correlation ID for diagnostic logs.

    Returns:
        Up to 100 globally ascending values and whether another page exists.
        Numbers sort numerically before other scalar types, whose text uses
        case-insensitive natural ordering with numeric digit sequences.

    Raises:
        ValueError: If the page or column position is invalid.
        ConditionError: If scanned values are unsupported or serialize ambiguously.
        ValueRequestCancelledError: If cancellation was requested.
    """
    started = perf_counter()
    _log_value_page(
        logging.DEBUG,
        "value page requested",
        corr_id,
        "page=%d, source_rows=%d",
        request.page,
        len(source),
    )
    try:
        page = _distinct_value_page(source, request, cancel_cb=cancel_cb)
    except ValueRequestCancelledError:
        _log_value_page(
            logging.DEBUG,
            "value page finished",
            corr_id,
            "outcome=cancelled, page=%d, ms=%.1f",
            request.page,
            (perf_counter() - started) * 1000,
        )
        raise
    except ConditionError as error:
        _log_value_page(
            logging.WARNING,
            "value page rejected",
            corr_id,
            "page=%d, problem=%s, exception=%s, ms=%.1f",
            request.page,
            error.problem.value,
            type(error).__name__,
            (perf_counter() - started) * 1000,
        )
        raise
    except Exception as error:
        _log_value_page(
            logging.ERROR,
            "value page failed",
            corr_id,
            "page=%d, exception=%s, ms=%.1f",
            request.page,
            type(error).__name__,
            (perf_counter() - started) * 1000,
        )
        raise
    _log_value_page(
        logging.DEBUG,
        "value page finished",
        corr_id,
        "outcome=success, page=%d, entries=%d, has_next=%s, ms=%.1f",
        request.page,
        len(page.entries),
        page.has_next,
        (perf_counter() - started) * 1000,
    )
    return page


def _distinct_value_page(
    source: pd.DataFrame,
    request: ValuePageRequest,
    *,
    cancel_cb: Callable[[], bool] | None,
) -> ValuePage:
    """Scan and sort the requested page without emitting diagnostics."""
    if request.page < 0 or not 0 <= request.column_position < len(source.columns):
        message = "Invalid condition value page or source column position."
        raise ValueError(message)
    series = source.iloc[:, request.column_position]
    search = request.search.casefold()
    start = request.page * VALUE_PAGE_SIZE
    stop = start + VALUE_PAGE_SIZE
    seen: dict[str, ConditionValue] = {}
    for offset in range(0, len(series), _SCAN_CHUNK_SIZE):
        if cancel_cb is not None and cancel_cb():
            raise ValueRequestCancelledError
        for raw_value in series.iloc[offset : offset + _SCAN_CHUNK_SIZE]:
            value = condition_value(raw_value)
            if value is None or search not in value.text.casefold():
                continue
            existing = seen.get(value.text)
            if existing is not None:
                if existing != value:
                    raise ConditionError(ConditionProblem.AMBIGUOUS_VALUE)
                continue
            seen[value.text] = value
    if cancel_cb is not None and cancel_cb():
        raise ValueRequestCancelledError
    ordered = sorted(seen.values(), key=_value_sort_key)
    if cancel_cb is not None and cancel_cb():
        raise ValueRequestCancelledError
    return ValuePage(tuple(ordered[start:stop]), has_next=len(ordered) > stop)
