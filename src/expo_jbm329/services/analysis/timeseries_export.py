"""Typed exports of a displayed time-series analysis."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

import pandas as pd

from expo_jbm329.services.analysis.statistics import StatisticsExportFormat
from expo_jbm329.services.analysis.timeseries import TimeSeriesResult
from expo_jbm329.services.analysis.timeseries_charts import (
    TimeSeriesChartLabels,
    has_autocorrelation,
    has_decomposition,
)

if TYPE_CHECKING:
    from collections.abc import Sequence


class TimeSeriesExportComponent(StrEnum):
    """Selectable displayed results; charts are Excel-only."""

    SERIES = "series"
    AUTOCORRELATION = "autocorrelation"
    MODEL_SUMMARY = "model_summary"
    CHARTS = "charts"


class TimeSeriesMetric(StrEnum):
    """Stable keys of the model summary, localized at the UI boundary."""

    SOURCE_ROWS = "source_rows"
    INVALID_ROWS = "invalid_rows"
    DUPLICATE_ROWS = "duplicate_rows"
    TIME_POINTS = "time_points"
    SEASONAL_PERIOD = "seasonal_period"


TIME_SERIES_COMPONENTS = tuple(TimeSeriesExportComponent)


@dataclass(frozen=True, slots=True)
class TimeSeriesExportSnapshot:
    """Own the displayed time-series analysis, its comments and chart text.

    Attributes:
        result: The successful analysis shown in the content pane.
        chart_labels: Translated plot text captured on the GUI thread.
        notes: Plain-text lines of the displayed model comments and unavailability reasons.
        autocorrelation_note: Translated reason shown when autocorrelation is unavailable.
    """

    result: TimeSeriesResult
    chart_labels: TimeSeriesChartLabels
    notes: tuple[str, ...] = ()
    autocorrelation_note: str = ""

    def __post_init__(self) -> None:
        """Reject failed or unanalyzed results."""
        result = self.result
        if not isinstance(result, TimeSeriesResult):  # pyright: ignore[reportUnnecessaryIsInstance]
            message = "A typed time-series result is required."
            raise TypeError(message)
        if result.error is not None:
            message = "A failed time-series result cannot be exported."
            raise ValueError(message)
        if not result.timestamps:
            message = "An applied time-series result must be analyzed."
            raise ValueError(message)
        if not isinstance(self.chart_labels, TimeSeriesChartLabels):  # pyright: ignore[reportUnnecessaryIsInstance]
            message = "Time-series chart labels are required."
            raise TypeError(message)

    @property
    def components(self) -> tuple[TimeSeriesExportComponent, ...]:
        """Return the components available for this analysis.

        Autocorrelation is omitted when the series is irregular or has gaps.
        """
        return tuple(
            component
            for component in TIME_SERIES_COMPONENTS
            if component is not TimeSeriesExportComponent.AUTOCORRELATION or has_autocorrelation(self.result)
        )


@dataclass(frozen=True, slots=True)
class TimeSeriesExportRequest:
    """Selected components from one immutable displayed snapshot."""

    snapshot: TimeSeriesExportSnapshot
    components: tuple[TimeSeriesExportComponent, ...]
    format: StatisticsExportFormat

    def __post_init__(self) -> None:
        """Validate the selection without altering retained dialog choices."""
        if not isinstance(self.snapshot, TimeSeriesExportSnapshot):  # pyright: ignore[reportUnnecessaryIsInstance]
            message = "A typed time-series export snapshot is required."
            raise TypeError(message)
        if not self.components or len(set(self.components)) != len(self.components):
            message = "Select distinct time-series components."
            raise ValueError(message)
        if any(
            not isinstance(item, TimeSeriesExportComponent)  # pyright: ignore[reportUnnecessaryIsInstance]
            for item in self.components
        ):
            message = "Unknown time-series export component."
            raise ValueError(message)
        if any(item not in self.snapshot.components for item in self.components):
            message = "The selected time-series component is unavailable."
            raise ValueError(message)
        if not isinstance(self.format, StatisticsExportFormat):  # pyright: ignore[reportUnnecessaryIsInstance]
            message = "Unknown time-series export format."
            raise TypeError(message)
        if self.format is not StatisticsExportFormat.EXCEL and (
            TimeSeriesExportComponent.CHARTS in self.components or len(self.components) != 1
        ):
            message = "CSV and binary exports require exactly one table and no charts."
            raise ValueError(message)


def time_series_export_tables(
    snapshot: TimeSeriesExportSnapshot,
    components: Sequence[TimeSeriesExportComponent],
) -> dict[TimeSeriesExportComponent, pd.DataFrame]:
    """Build fresh tables for the selected non-chart components.

    Args:
        snapshot: The displayed time-series analysis.
        components: Selected components; charts are ignored.

    Returns:
        Tables in selection order, keyed by component.
    """
    tables: dict[TimeSeriesExportComponent, pd.DataFrame] = {}
    for component in components:
        match component:
            case TimeSeriesExportComponent.SERIES:
                tables[component] = series_table(snapshot)
            case TimeSeriesExportComponent.AUTOCORRELATION:
                tables[component] = autocorrelation_table(snapshot)
            case TimeSeriesExportComponent.MODEL_SUMMARY:
                tables[component] = time_series_model_summary_table(snapshot)
            case TimeSeriesExportComponent.CHARTS:
                pass
    return tables


def series_table(snapshot: TimeSeriesExportSnapshot) -> pd.DataFrame:
    """Return the prepared series behind the charts, one row per time point.

    Duplicate timestamps are already averaged and any resampling applied;
    resampled periods without data stay missing. Decomposition columns are
    included only when the decomposition is available.

    Args:
        snapshot: The displayed time-series analysis.

    Returns:
        Columns ``timestamp`` and ``value``, plus ``trend``, ``seasonal`` and
        ``residual`` when decomposed.
    """
    result = snapshot.result
    data: dict[str, pd.Series] = {
        "timestamp": pd.Series(pd.DatetimeIndex(result.timestamps)),
        "value": pd.Series(result.values, dtype="float64"),
    }
    if has_decomposition(result):
        data["trend"] = pd.Series(result.trend, dtype="float64")
        data["seasonal"] = pd.Series(result.seasonal, dtype="float64")
        data["residual"] = pd.Series(result.residual, dtype="float64")
    return pd.DataFrame(data)


def autocorrelation_table(snapshot: TimeSeriesExportSnapshot) -> pd.DataFrame:
    """Return the displayed autocorrelation coefficients from lag 1.

    Args:
        snapshot: The displayed time-series analysis.

    Returns:
        Columns ``lag`` and ``autocorrelation``; empty when unavailable.
    """
    values = snapshot.result.acf_values
    return pd.DataFrame({
        "lag": pd.Series(range(1, len(values) + 1), dtype=pd.Int64Dtype()),
        "autocorrelation": pd.Series(values, dtype="float64"),
    })


def time_series_model_summary_table(snapshot: TimeSeriesExportSnapshot) -> pd.DataFrame:
    """Return row diagnostics and the seasonal period with the displayed comments.

    The seasonal period is missing when none was chosen or detected; the
    comments explain why.

    Args:
        snapshot: The displayed time-series analysis.

    Returns:
        Columns ``metric`` (a `TimeSeriesMetric` key), ``value`` and ``notes``.
    """
    result = snapshot.result
    period = float("nan") if result.seasonal_period is None else float(result.seasonal_period)
    values: list[tuple[TimeSeriesMetric, float]] = [
        (TimeSeriesMetric.SOURCE_ROWS, result.source_rows),
        (TimeSeriesMetric.INVALID_ROWS, result.invalid_rows),
        (TimeSeriesMetric.DUPLICATE_ROWS, result.duplicate_rows),
        (TimeSeriesMetric.TIME_POINTS, len(result.timestamps)),
        (TimeSeriesMetric.SEASONAL_PERIOD, period),
    ]
    notes = snapshot.notes
    row_count = max(len(values), len(notes))
    return pd.DataFrame({
        "metric": pd.Series([metric.value for metric, _ in values], dtype=pd.StringDtype()).reindex(range(row_count)),
        "value": pd.Series([float(value) for _, value in values], dtype="float64").reindex(range(row_count)),
        "notes": pd.Series(notes, dtype=pd.StringDtype()).reindex(range(row_count)),
    })
