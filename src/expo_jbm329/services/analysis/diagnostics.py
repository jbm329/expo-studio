"""Metadata-only diagnostics shared by analysis computations, charts and reports.

Messages follow the application convention ``Component: event (corr=..., key=value)``.
Only bounded structural metadata is logged; column names, values, titles and
payloads never are.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from contextvars import ContextVar
from time import perf_counter
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from collections.abc import Generator

_LOGGER = logging.getLogger("applogger.service")
_COMPONENT = "AnalysisService"
AnalysisOutcome = Literal["success", "unavailable", "cancelled"]

# Set while a chart batch or report stage owns a summary line. Nested successful
# computations, batches and stages stay silent so exports log one line per
# operation instead of one per chart. Context variables are thread-local in
# worker pools, so concurrent jobs never silence each other.
_SUMMARY_SCOPE_ACTIVE: ContextVar[bool] = ContextVar("analysis_summary_scope_active", default=False)


def log_diagnostic(
    component: str,
    event: str,
    *,
    corr: str | None,
    level: int = logging.DEBUG,
    **fields: object,
) -> None:
    """Log one ``Component: event (corr=..., key=value)`` diagnostic line.

    Args:
        component: Stable component name shown as the message prefix.
        event: Short lower-case event description.
        corr: Operation correlation identifier; always included.
        level: Logging level.
        **fields: Bounded metadata. ``None`` values are omitted.
    """
    if not _LOGGER.isEnabledFor(level):
        return
    parts = [f"corr={corr}"]
    parts.extend(f"{key}={value}" for key, value in fields.items() if value is not None)
    _LOGGER.log(level, "%s: %s (%s)", component, event, ", ".join(parts))


def elapsed_ms(started: float) -> str:
    """Format elapsed milliseconds since a ``perf_counter`` timestamp.

    Args:
        started: Start timestamp from ``time.perf_counter``.

    Returns:
        Milliseconds with one decimal, matching JobManager timing lines.
    """
    return f"{(perf_counter() - started) * 1000.0:.1f}"


def summary_scope_active() -> bool:
    """Return whether an enclosing chart batch or report stage owns the summary."""
    return _SUMMARY_SCOPE_ACTIVE.get()


@contextmanager
def summary_scope() -> Generator[bool]:
    """Mark nested diagnostics as covered by the caller's summary line.

    Yields:
        ``True`` when this is the outermost scope and should log its success.
    """
    outermost = not _SUMMARY_SCOPE_ACTIVE.get()
    token = _SUMMARY_SCOPE_ACTIVE.set(True)
    try:
        yield outermost
    finally:
        _SUMMARY_SCOPE_ACTIVE.reset(token)


class AnalysisDiagnostic:
    """Time one computation and log a single bounded completion line."""

    def __init__(
        self,
        operation: str,
        corr_id: str | None,
        *,
        row_count: int,
        column_count: int,
        method: str | None = None,
        selected_count: int | None = None,
    ) -> None:
        """Start timing a computation.

        Args:
            operation: Stable analysis operation identifier.
            corr_id: Optional operation correlation identifier.
            row_count: Number of input rows.
            column_count: Number of input columns.
            method: Stable method identifier, if applicable.
            selected_count: Number of selected features, if applicable.
        """
        self._operation = operation
        self._corr_id = corr_id
        self._method = method
        self._row_count = row_count
        self._column_count = column_count
        self._selected_count = selected_count
        # Computations repeated per chart inside an export are summarized by the batch.
        self._silent = summary_scope_active()
        self._started_at = perf_counter()

    def finish(
        self,
        outcome: AnalysisOutcome,
        *,
        reason: str | None = None,
        rows_used: int | None = None,
        rows_dropped: int | None = None,
        item_count: int | None = None,
        sampled: bool | None = None,
    ) -> None:
        """Log the typed outcome and elapsed time.

        Args:
            outcome: Whether the computation succeeded, was unavailable, or
                was cooperatively cancelled.
            reason: Stable typed result reason code.
            rows_used: Number of complete/used rows when available.
            rows_dropped: Number of excluded rows when available.
            item_count: Bounded domain count such as groups or features.
            sampled: Whether presentation data was sampled, when applicable.
        """
        if self._silent:
            return
        log_diagnostic(
            _COMPONENT,
            "computation finished",
            corr=self._corr_id,
            operation=self._operation,
            method=self._method,
            outcome=outcome,
            reason=reason,
            rows=self._row_count,
            cols=self._column_count,
            selected=self._selected_count,
            rows_used=rows_used,
            rows_dropped=rows_dropped,
            items=item_count,
            sampled=sampled,
            ms=elapsed_ms(self._started_at),
        )


def log_recoverable_fit_failure(
    *,
    corr_id: str | None,
    model: str,
    reason: str,
    exception_class: str | None = None,
    rows_used: int,
) -> None:
    """Log a recoverable model-fit failure without exception text or data.

    Args:
        corr_id: Optional operation correlation identifier.
        model: Stable model identifier.
        reason: Stable failure reason code.
        exception_class: Exception class name for caught fit failures.
        rows_used: Number of complete rows used by the fit.
    """
    log_diagnostic(
        _COMPONENT,
        "model fit failed",
        corr=corr_id,
        level=logging.WARNING,
        model=model,
        reason=reason,
        exception_class=exception_class,
        rows_used=rows_used,
    )
