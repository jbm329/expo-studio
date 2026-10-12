"""Typed exports of a displayed univariate or multivariate outlier screening."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TYPE_CHECKING

import pandas as pd

from expo_jbm329.services.analysis.multivariate_outliers import MultivariateOutlierMethod, MultivariateOutlierResult
from expo_jbm329.services.analysis.outliers import OutlierColumnDetail, OutlierMethod, OutlierSummaryResult
from expo_jbm329.services.analysis.outliers_charts import OutlierHistogramLabels, OutlierProjectionLabels
from expo_jbm329.services.analysis.statistics import StatisticsExportFormat

if TYPE_CHECKING:
    from collections.abc import Sequence

    from expo_jbm329.services.analysis.multivariate_outliers import MultivariateExtremeObservation
    from expo_jbm329.services.analysis.outliers import ExtremeObservation


class OutlierExportComponent(StrEnum):
    """Selectable displayed results; charts are Excel-only.

    Univariate screening offers the column summary, the selected column's
    details, its potential outliers and charts. Multivariate screening offers
    the model summary, its potential outliers and the PCA chart.
    """

    COLUMN_SUMMARY = "column_summary"
    COLUMN_DETAILS = "column_details"
    MODEL_SUMMARY = "model_summary"
    POTENTIAL_OUTLIERS = "potential_outliers"
    CHARTS = "charts"


class OutlierMetric(StrEnum):
    """Stable keys of the metric/value tables, localized at the UI boundary."""

    THRESHOLD = "threshold"
    VALUES = "values"
    MISSING = "missing"
    OUTLIERS = "outliers"
    OUTLIER_SHARE = "outlier_share"
    LOW = "low"
    HIGH = "high"
    LOWER_FENCE = "lower_fence"
    UPPER_FENCE = "upper_fence"
    Q1 = "q1"
    Q3 = "q3"
    IQR = "iqr"
    MEAN = "mean"
    STD = "std"
    MEDIAN = "median"
    MAD = "mad"
    FEATURES = "features"
    CONTAMINATION = "contamination"
    LOF_NEIGHBORS = "lof_neighbors"
    TOTAL_ROWS = "total_rows"
    ROWS_USED = "rows_used"
    ROWS_DROPPED = "rows_dropped"
    INLIERS = "inliers"


UNIVARIATE_COMPONENTS = (
    OutlierExportComponent.COLUMN_SUMMARY,
    OutlierExportComponent.COLUMN_DETAILS,
    OutlierExportComponent.POTENTIAL_OUTLIERS,
    OutlierExportComponent.CHARTS,
)
MULTIVARIATE_COMPONENTS = (
    OutlierExportComponent.MODEL_SUMMARY,
    OutlierExportComponent.POTENTIAL_OUTLIERS,
    OutlierExportComponent.CHARTS,
)


@dataclass(frozen=True, slots=True)
class UnivariateOutlierExportSnapshot:
    """Own the displayed per-column screening, its selected column and chart data.

    Attributes:
        summary: The applied per-column summary.
        data: Owned copy of every screened numeric column, used to render
            each column's histogram in the export worker.
        chart_labels: Translated histogram text captured on the GUI thread.
        summary_notes: Plain-text lines displayed with the summary table.
        detail: The selected column's displayed detail, if any.
        detail_notes: Plain-text lines displayed with the selected column.
    """

    summary: OutlierSummaryResult
    data: pd.DataFrame
    chart_labels: OutlierHistogramLabels
    summary_notes: tuple[str, ...] = ()
    detail: OutlierColumnDetail | None = None
    detail_notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Reject failed summaries, mismatched data and details of another screening."""
        summary = self.summary
        if not isinstance(summary, OutlierSummaryResult):  # pyright: ignore[reportUnnecessaryIsInstance]
            message = "A typed outlier summary is required."
            raise TypeError(message)
        if summary.error is not None:
            message = "A failed outlier summary cannot be exported."
            raise ValueError(message)
        if not summary.columns:
            message = "An applied outlier summary must contain screened columns."
            raise ValueError(message)
        if not isinstance(self.data, pd.DataFrame):  # pyright: ignore[reportUnnecessaryIsInstance]
            message = "Owned outlier data must be a DataFrame."
            raise TypeError(message)
        if tuple(self.data.columns) != summary.available_columns or len(self.data) != summary.row_count:
            message = "Owned outlier data does not match the applied summary."
            raise ValueError(message)
        if not isinstance(self.chart_labels, OutlierHistogramLabels):  # pyright: ignore[reportUnnecessaryIsInstance]
            message = "Histogram labels are required."
            raise TypeError(message)
        detail = self.detail
        if detail is None:
            return
        if detail.error is not None:
            message = "A failed column detail cannot be exported."
            raise ValueError(message)
        if (
            detail.method is not summary.method
            or detail.threshold != summary.threshold
            or detail.summary.column not in summary.available_columns
        ):
            message = "The column detail does not belong to the applied summary."
            raise ValueError(message)

    @property
    def components(self) -> tuple[OutlierExportComponent, ...]:
        """Return the components offered for univariate screening."""
        return UNIVARIATE_COMPONENTS

    @property
    def chart_columns(self) -> tuple[str, ...]:
        """Return every screened column in summary order; unscreened ones have no histogram."""
        return tuple(column.column for column in self.summary.columns if column.status is None)

    def is_available(self, component: OutlierExportComponent) -> bool:
        """Return whether `component` has displayed content to export."""
        match component:
            case OutlierExportComponent.COLUMN_SUMMARY:
                return True
            case OutlierExportComponent.COLUMN_DETAILS:
                return self.detail is not None
            case OutlierExportComponent.POTENTIAL_OUTLIERS:
                return self.detail is not None and bool(self.detail.extremes)
            case OutlierExportComponent.CHARTS:
                return bool(self.chart_columns)
            case OutlierExportComponent.MODEL_SUMMARY:
                return False

    def with_detail(
        self, detail: OutlierColumnDetail | None, notes: tuple[str, ...]
    ) -> UnivariateOutlierExportSnapshot:
        """Return a snapshot sharing the summary and data with another displayed column."""
        return replace(self, detail=detail, detail_notes=notes)


@dataclass(frozen=True, slots=True)
class MultivariateOutlierExportSnapshot:
    """Own the displayed multivariate fit, its comments and chart text.

    Attributes:
        result: The successful fit shown in the content pane.
        chart_labels: Translated projection text captured on the GUI thread.
        notes: Plain-text lines of the displayed model comments.
    """

    result: MultivariateOutlierResult
    chart_labels: OutlierProjectionLabels
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Reject failed or unfitted results."""
        result = self.result
        if not isinstance(result, MultivariateOutlierResult):  # pyright: ignore[reportUnnecessaryIsInstance]
            message = "A typed multivariate outlier result is required."
            raise TypeError(message)
        if result.error is not None:
            message = "A failed multivariate outlier result cannot be exported."
            raise ValueError(message)
        if result.rows_used == 0 or not result.sample_pc1:
            message = "An applied multivariate outlier result must be fitted."
            raise ValueError(message)
        if not isinstance(self.chart_labels, OutlierProjectionLabels):  # pyright: ignore[reportUnnecessaryIsInstance]
            message = "Projection labels are required."
            raise TypeError(message)

    @property
    def components(self) -> tuple[OutlierExportComponent, ...]:
        """Return the components offered for multivariate screening."""
        return MULTIVARIATE_COMPONENTS

    def is_available(self, component: OutlierExportComponent) -> bool:
        """Return whether `component` has displayed content to export."""
        match component:
            case OutlierExportComponent.MODEL_SUMMARY | OutlierExportComponent.CHARTS:
                return True
            case OutlierExportComponent.POTENTIAL_OUTLIERS:
                return bool(self.result.extremes)
            case OutlierExportComponent.COLUMN_SUMMARY | OutlierExportComponent.COLUMN_DETAILS:
                return False


OutlierExportSnapshot = UnivariateOutlierExportSnapshot | MultivariateOutlierExportSnapshot


@dataclass(frozen=True, slots=True)
class OutlierExportRequest:
    """Selected components from one immutable displayed snapshot."""

    snapshot: OutlierExportSnapshot
    components: tuple[OutlierExportComponent, ...]
    format: StatisticsExportFormat

    def __post_init__(self) -> None:
        """Validate the selection without altering retained dialog choices."""
        if not self.components or len(set(self.components)) != len(self.components):
            message = "Select distinct available outlier components."
            raise ValueError(message)
        if any(
            not isinstance(item, OutlierExportComponent)  # pyright: ignore[reportUnnecessaryIsInstance]
            for item in self.components
        ):
            message = "Unknown outlier export component."
            raise ValueError(message)
        if not isinstance(self.format, StatisticsExportFormat):  # pyright: ignore[reportUnnecessaryIsInstance]
            message = "Unknown outlier export format."
            raise TypeError(message)
        if any(not self.snapshot.is_available(item) for item in self.components):
            message = "Only displayed, non-empty outlier components can be exported."
            raise ValueError(message)
        if self.format is not StatisticsExportFormat.EXCEL and (
            OutlierExportComponent.CHARTS in self.components or len(self.components) != 1
        ):
            message = "CSV and binary exports require exactly one table and no charts."
            raise ValueError(message)


def outlier_export_tables(
    snapshot: OutlierExportSnapshot,
    components: Sequence[OutlierExportComponent],
    *,
    row_label: str = "Row",
    score_label: str = "Score",
) -> dict[OutlierExportComponent, pd.DataFrame]:
    """Build fresh tables for the selected non-chart components.

    Args:
        snapshot: The displayed screening.
        components: Selected components; charts are ignored.
        row_label: Translated header of the potential outliers' row numbers.
        score_label: Translated header of the potential outliers' scores.

    Returns:
        Tables in selection order, keyed by component.

    Raises:
        ValueError: If a component is unavailable for the snapshot.
    """
    tables: dict[OutlierExportComponent, pd.DataFrame] = {}
    for component in components:
        if component is OutlierExportComponent.CHARTS:
            continue
        if not snapshot.is_available(component):
            message = f"The {component.value} component is not available for this outlier screening."
            raise ValueError(message)
        if component is OutlierExportComponent.POTENTIAL_OUTLIERS:
            tables[component] = potential_outliers_table(snapshot, row_label=row_label, score_label=score_label)
        elif isinstance(snapshot, MultivariateOutlierExportSnapshot):
            tables[component] = outlier_model_summary_table(snapshot)
        elif component is OutlierExportComponent.COLUMN_SUMMARY:
            tables[component] = outlier_column_summary_table(snapshot)
        else:
            tables[component] = outlier_column_details_table(snapshot)
    return tables


def outlier_column_summary_table(snapshot: UnivariateOutlierExportSnapshot) -> pd.DataFrame:
    """Return one row per numeric column in the displayed ranking, with the displayed notes.

    Unscreened columns keep their value and missing counts, have missing
    screening values and carry their `ColumnOutlierStatus` key in ``status``.
    Notes share column rows where possible, adding rows only when necessary.

    Args:
        snapshot: The displayed univariate screening.

    Returns:
        A table with stable snake_case column names.
    """
    rows = snapshot.summary.columns
    screened = [row.status is None for row in rows]
    row_count = max(len(rows), len(snapshot.summary_notes))

    def _counts(values: list[int], *, screened_only: bool = True) -> pd.Series:
        return pd.Series(
            [
                value if is_screened or not screened_only else None
                for value, is_screened in zip(values, screened, strict=True)
            ],
            dtype=pd.Int64Dtype(),
        ).reindex(range(row_count))

    def _floats(values: list[float]) -> pd.Series:
        return pd.Series(
            [value if is_screened else float("nan") for value, is_screened in zip(values, screened, strict=True)],
            dtype="float64",
        ).reindex(range(row_count))

    def _texts(values: list[str | None] | tuple[str, ...]) -> pd.Series:
        return pd.Series(list(values), dtype=pd.StringDtype()).reindex(range(row_count))

    return pd.DataFrame({
        "column": _texts([row.column for row in rows]),
        "values": _counts([row.n for row in rows], screened_only=False),
        "missing": _counts([row.missing for row in rows], screened_only=False),
        "outliers": _counts([row.outlier_count for row in rows]),
        "share": _floats([row.outlier_fraction for row in rows]),
        "low": _counts([row.low_count for row in rows]),
        "high": _counts([row.high_count for row in rows]),
        "lower_fence": _floats([row.lower_fence for row in rows]),
        "upper_fence": _floats([row.upper_fence for row in rows]),
        "status": _texts([None if row.status is None else row.status.value for row in rows]),
        "notes": _texts(snapshot.summary_notes),
    })


def _column_detail_values(detail: OutlierColumnDetail) -> list[tuple[OutlierMetric, float]]:
    """Return the selected column's displayed statistics, in display order."""
    summary = detail.summary
    values: list[tuple[OutlierMetric, float]] = [
        (OutlierMetric.THRESHOLD, detail.threshold),
        (OutlierMetric.VALUES, summary.n),
        (OutlierMetric.MISSING, summary.missing),
    ]
    if summary.status is not None:
        return values
    values += [
        (OutlierMetric.OUTLIERS, summary.outlier_count),
        (OutlierMetric.OUTLIER_SHARE, summary.outlier_fraction),
        (OutlierMetric.LOW, summary.low_count),
        (OutlierMetric.HIGH, summary.high_count),
        (OutlierMetric.LOWER_FENCE, summary.lower_fence),
        (OutlierMetric.UPPER_FENCE, summary.upper_fence),
    ]
    match detail.method:
        case OutlierMethod.IQR:
            values += [(OutlierMetric.Q1, detail.q1), (OutlierMetric.Q3, detail.q3), (OutlierMetric.IQR, detail.scale)]
        case OutlierMethod.Z_SCORE:
            values += [(OutlierMetric.MEAN, detail.mean), (OutlierMetric.STD, detail.std)]
        case OutlierMethod.MODIFIED_Z_SCORE:
            values += [(OutlierMetric.MEDIAN, detail.median), (OutlierMetric.MAD, detail.mad)]
    return values


def outlier_column_details_table(snapshot: UnivariateOutlierExportSnapshot) -> pd.DataFrame:
    """Return the selected column's statistics as metric/value rows with its displayed notes.

    Args:
        snapshot: The displayed univariate screening with a selected column.

    Returns:
        Columns ``metric`` (an `OutlierMetric` key), ``value`` and ``notes``.

    Raises:
        ValueError: If no column detail is displayed.
    """
    if snapshot.detail is None:
        message = "No column detail is displayed."
        raise ValueError(message)
    return _metric_table(_column_detail_values(snapshot.detail), snapshot.detail_notes)


def outlier_model_summary_table(snapshot: MultivariateOutlierExportSnapshot) -> pd.DataFrame:
    """Return the multivariate fit's counts and settings with its displayed comments.

    Args:
        snapshot: The displayed multivariate fit.

    Returns:
        Columns ``metric`` (an `OutlierMetric` key), ``value`` and ``notes``.
    """
    result = snapshot.result
    values: list[tuple[OutlierMetric, float]] = [
        (OutlierMetric.FEATURES, len(result.columns)),
        (OutlierMetric.CONTAMINATION, result.contamination),
    ]
    if result.method is MultivariateOutlierMethod.LOCAL_OUTLIER_FACTOR:
        values.append((OutlierMetric.LOF_NEIGHBORS, result.lof_neighbors))
    values += [
        (OutlierMetric.TOTAL_ROWS, result.total_rows),
        (OutlierMetric.ROWS_USED, result.rows_used),
        (OutlierMetric.ROWS_DROPPED, result.rows_dropped),
        (OutlierMetric.OUTLIERS, result.outlier_count),
        (OutlierMetric.OUTLIER_SHARE, result.outlier_count / result.rows_used),
        (OutlierMetric.INLIERS, result.inlier_count),
    ]
    return _metric_table(values, snapshot.notes)


def _metric_table(values: list[tuple[OutlierMetric, float]], notes: tuple[str, ...]) -> pd.DataFrame:
    """Combine metric rows and notes, adding rows only when there are more notes."""
    row_count = max(len(values), len(notes))
    return pd.DataFrame({
        "metric": pd.Series([metric.value for metric, _ in values], dtype=pd.StringDtype()).reindex(range(row_count)),
        "value": pd.Series([float(value) for _, value in values], dtype="float64").reindex(range(row_count)),
        "notes": pd.Series(notes, dtype=pd.StringDtype()).reindex(range(row_count)),
    })


def potential_outliers_table(
    snapshot: OutlierExportSnapshot,
    *,
    row_label: str = "Row",
    score_label: str = "Score",
) -> pd.DataFrame:
    """Return the displayed potential outliers, most extreme first.

    Univariate rows hold the row number, the screened value, its score and
    every other dataset column; multivariate rows hold the row number, the
    anomaly score and every dataset column. The fixed headers get a
    numbered suffix when a dataset column already uses the same name.

    Args:
        snapshot: The displayed screening.
        row_label: Header of the 1-based dataset row numbers.
        score_label: Header of the method's score.

    Returns:
        A table with unique column names, limited to the displayed rows.

    Raises:
        ValueError: If no potential outliers are displayed.
    """
    if not snapshot.is_available(OutlierExportComponent.POTENTIAL_OUTLIERS):
        message = "No potential outliers are displayed."
        raise ValueError(message)
    if isinstance(snapshot, UnivariateOutlierExportSnapshot):
        detail = snapshot.detail
        if detail is None:  # pragma: no cover - excluded by is_available
            message = "No column detail is displayed."
            raise ValueError(message)
        return _univariate_outliers_table(detail, row_label, score_label)
    return _multivariate_outliers_table(snapshot.result, row_label, score_label)


def _univariate_outliers_table(detail: OutlierColumnDetail, row_label: str, score_label: str) -> pd.DataFrame:
    """Build the selected column's displayed outlier rows."""
    column = detail.summary.column
    other_indexes = [index for index, name in enumerate(detail.row_columns) if name != column]
    others = [detail.row_columns[index] for index in other_indexes]
    row_header, score_header = unique_headers((row_label, score_label), (column, *others))
    observations: tuple[ExtremeObservation, ...] = detail.extremes
    data: dict[str, pd.Series] = {
        row_header: pd.Series([item.row_number for item in observations], dtype="int64"),
        column: pd.Series([item.value for item in observations], dtype="float64"),
        score_header: pd.Series([item.score for item in observations], dtype="float64"),
    }
    for index, name in zip(other_indexes, others, strict=True):
        data[name] = _value_series([item.row_values[index] for item in observations])
    return pd.DataFrame(data)


def _multivariate_outliers_table(result: MultivariateOutlierResult, row_label: str, score_label: str) -> pd.DataFrame:
    """Build the fit's displayed outlier rows."""
    row_header, score_header = unique_headers((row_label, score_label), result.row_columns)
    observations: tuple[MultivariateExtremeObservation, ...] = result.extremes
    data: dict[str, pd.Series] = {
        row_header: pd.Series([item.row_number for item in observations], dtype="int64"),
        score_header: pd.Series([item.score for item in observations], dtype="float64"),
    }
    for index, name in enumerate(result.row_columns):
        data[name] = _value_series([item.row_values[index] for item in observations])
    return pd.DataFrame(data)


def _value_series(values: list[object]) -> pd.Series:
    """Return dataset values with inferred dtype, keeping text as `pd.StringDtype`."""
    series = pd.Series(values)
    if series.dtype == object and all(isinstance(value, str) for value in series.dropna()):
        return series.astype(pd.StringDtype())
    return series


def unique_headers(fixed: Sequence[str], existing: Sequence[str]) -> tuple[str, ...]:
    """Return `fixed` headers renamed so none collides with `existing` or each other.

    A colliding header gets the first free `` (n)`` suffix, starting at 2.

    Args:
        fixed: Headers added by the export, in order.
        existing: Dataset column names that must keep their names.

    Returns:
        Unique headers in the order of `fixed`.
    """
    taken = set(existing)
    result: list[str] = []
    for header in fixed:
        candidate = header
        suffix = 2
        while candidate in taken:
            candidate = f"{header} ({suffix})"
            suffix += 1
        taken.add(candidate)
        result.append(candidate)
    return tuple(result)
