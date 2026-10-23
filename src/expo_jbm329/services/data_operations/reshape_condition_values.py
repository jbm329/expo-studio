"""Cancellable distinct-value pages for the Reshape condition builder."""

from __future__ import annotations

from dataclasses import dataclass
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
    """One page without an expensive exact total distinct count."""

    entries: tuple[ConditionValue, ...]
    has_next: bool


def distinct_value_page(
    source: pd.DataFrame,
    request: ValuePageRequest,
    *,
    cancel_cb: Callable[[], bool] | None = None,
) -> ValuePage:
    """Scan the fixed source for a page of distinct matching nonmissing values.

    Args:
        source: Read-only source captured for this Reshape session.
        request: Positional column, literal search, and zero-based page.
        cancel_cb: Optional cooperative cancellation predicate.

    Returns:
        Up to 100 values in first-occurrence order and whether another exists.

    Raises:
        ValueError: If the page or column position is invalid.
        ConditionError: If scanned values are unsupported or serialize ambiguously.
        ValueRequestCancelledError: If cancellation was requested.
    """
    if request.page < 0 or not 0 <= request.column_position < len(source.columns):
        message = "Invalid condition value page or source column position."
        raise ValueError(message)
    series = source.iloc[:, request.column_position]
    search = request.search.casefold()
    start = request.page * VALUE_PAGE_SIZE
    stop = start + VALUE_PAGE_SIZE
    seen: dict[str, ConditionValue] = {}
    result: list[ConditionValue] = []
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
            ordinal = len(seen) - 1
            if ordinal == stop:
                return ValuePage(tuple(result), has_next=True)
            if ordinal >= start:
                result.append(value)
    if cancel_cb is not None and cancel_cb():
        raise ValueRequestCancelledError
    return ValuePage(tuple(result), has_next=False)
