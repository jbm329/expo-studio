"""Visualization models."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ChartType(StrEnum):
    """Supported chart types."""

    LINE = "line"
    BAR = "bar"
    PIE = "pie"
    SCATTER = "scatter"
    HISTOGRAM = "histogram"


class AggregationType(StrEnum):
    """Supported aggregation types."""

    SUM = "sum"
    COUNT = "count"
    COUNT_DISTINCT = "count_distinct"
    AVG = "avg"
    MIN = "min"
    MAX = "max"


class MeasureType(StrEnum):
    """Supported measure types."""

    COLUMN = "column"
    ROW_COUNT = "row_count"


@dataclass(frozen=True, slots=True)
class VisualizationDatasetRef:
    """Lightweight reference for a result-tab dataset.

    Attributes:
        tab_id: Stable internal tab ID.
        title: Visible dataset title.
        row_count: Number of rows in the dataset.
        column_count: Number of columns in the dataset.
    """

    tab_id: str
    title: str
    row_count: int
    column_count: int


@dataclass(slots=True)
class MeasureConfig:
    """Definition of a measure used in a visualization.

    Attributes:
        measure_type: Whether the measure is based on a dataset column or row count.
        column: Source column for column-based measures.
        aggregation: Aggregation applied to the measure.
        name: Optional user-defined label for the measure.
    """

    measure_type: MeasureType
    column: str | None = None
    aggregation: AggregationType | None = None
    name: str | None = None


@dataclass(slots=True)
class VisualizationConfig:
    """User-selected configuration for a visualization.

    Attributes:
        dataset_tab_id: Dataset source tab ID.
        chart_type: Selected chart type.
        category_column: Category/dimension column for bar/line/pie.
        measure: Measure column for bar/line/pie/histogram.
        x_column: X-axis column for scatter.
        y_column: Y-axis column for scatter.
        aggregation: Aggregation applied for category-based charts.
    """

    dataset_tab_id: str
    chart_type: ChartType

    category_column: str | None = None
    measure: MeasureConfig | None = None

    x_column: str | None = None
    y_column: str | None = None

    aggregation: AggregationType | None = None
