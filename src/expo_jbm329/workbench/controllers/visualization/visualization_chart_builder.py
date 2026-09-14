"""Chart builder for dataset visualizations."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from matplotlib.axes import Axes
from pandas.api.types import is_numeric_dtype

from expo_jbm329.utils.visualization_models import (
    AggregationType,
    ChartType,
    MeasureType,
    VisualizationConfig,
)


class VisualizationError(ValueError):
    """Domain exception for visualization errors.

    Attributes:
        code: Stable machine-readable error code.
        detail: Optional technical detail for logs/debugging.
    """

    def __init__(self, code: str, detail: str | None = None) -> None:
        """Initialize the visualization error.

        Args:
            code: Stable machine-readable error code.
            detail: Optional technical detail for logs/debugging.
        """
        self.code = code
        self.detail = detail

        message = code if not detail else f"{code}: {detail}"
        super().__init__(message)


@dataclass(slots=True)
class PreparedSeries:
    """Prepared chart series data."""

    x: pd.Series
    y: pd.Series


class VisualizationChartBuilder:
    """Build and render visualizations from pandas DataFrames."""

    def draw(self, ax: Axes, df: pd.DataFrame, config: VisualizationConfig) -> None:
        """Render a chart onto a matplotlib axes.

        Args:
            ax: Target matplotlib axes.
            df: Source DataFrame.
            config: User-selected visualization configuration.

        Raises:
            VisualizationError: If the configuration or data is invalid.
        """
        ax.clear()

        if df.empty:
            raise VisualizationError("dataset_empty")

        if config.chart_type == ChartType.BAR:
            self._draw_bar(ax, df, config)
            return

        if config.chart_type == ChartType.LINE:
            self._draw_line(ax, df, config)
            return

        if config.chart_type == ChartType.PIE:
            self._draw_pie(ax, df, config)
            return

        if config.chart_type == ChartType.SCATTER:
            self._draw_scatter(ax, df, config)
            return

        if config.chart_type == ChartType.HISTOGRAM:
            self._draw_histogram(ax, df, config)
            return

        raise VisualizationError(
            "unsupported_chart_type",
            detail=f"chart_type={config.chart_type!r}",
        )

    # ------------------------------------------------------------------
    # Category-based charts
    # ------------------------------------------------------------------

    def _draw_bar(self, ax: Axes, df: pd.DataFrame, config: VisualizationConfig) -> None:
        """Draw a bar chart."""
        prepared = self._prepare_grouped_series(df, config)
        ax.bar(prepared.x.astype(str), prepared.y)
        ax.set_xlabel(config.category_column or "")
        ax.set_ylabel(self._value_axis_label(config))
        ax.set_title(self._chart_title(config))
        ax.tick_params(axis="x", rotation=45)

    def _draw_line(self, ax: Axes, df: pd.DataFrame, config: VisualizationConfig) -> None:
        """Draw a line chart."""
        prepared = self._prepare_grouped_series(df, config)
        ax.plot(prepared.x.astype(str), prepared.y, marker="o")
        ax.set_xlabel(config.category_column or "")
        ax.set_ylabel(self._value_axis_label(config))
        ax.set_title(self._chart_title(config))
        ax.tick_params(axis="x", rotation=45)

    def _draw_pie(self, ax: Axes, df: pd.DataFrame, config: VisualizationConfig) -> None:
        """Draw a pie chart."""
        prepared = self._prepare_grouped_series(df, config)

        if prepared.y.empty:
            raise VisualizationError("pie_no_data")

        ax.pie(
            prepared.y,
            labels=prepared.x.astype(str),
            autopct="%1.1f%%",
        )
        ax.set_title(self._chart_title(config))

    def _prepare_grouped_series(
        self,
        df: pd.DataFrame,
        config: VisualizationConfig,
    ) -> PreparedSeries:
        """Prepare grouped category/value series.

        Args:
            df: Source DataFrame.
            config: Visualization config.

        Returns:
            Prepared series for plotting.

        Raises:
            VisualizationError: If required fields are missing or invalid.
        """
        category_col = config.category_column
        measure = config.measure

        if not category_col:
            raise VisualizationError("category_column_missing")

        if category_col not in df.columns:
            raise VisualizationError(
                "category_column_not_found",
                detail=f"column={category_col!r}",
            )

        if measure is None:
            raise VisualizationError("measure_missing")

        grouped: pd.Series

        if measure.measure_type == MeasureType.ROW_COUNT:
            grouped = df.groupby(category_col, dropna=False).size()

        elif measure.measure_type == MeasureType.COLUMN:
            column = measure.column
            aggregation = measure.aggregation

            if not column:
                raise VisualizationError("value_column_missing")

            if column not in df.columns:
                raise VisualizationError(
                    "value_column_not_found",
                    detail=f"column={column!r}",
                )

            if aggregation is None:
                raise VisualizationError("aggregation_missing")

            series = df.groupby(category_col, dropna=False)[column]

            if aggregation == AggregationType.COUNT:
                grouped = series.count()

            elif aggregation == AggregationType.COUNT_DISTINCT:
                grouped = series.nunique()

            else:
                if not is_numeric_dtype(df[column]):
                    raise VisualizationError(
                        "non_numeric_measure_requires_count",
                        detail=f"column={column!r}, aggregation={aggregation.value}",
                    )

                if aggregation == AggregationType.SUM:
                    grouped = series.sum()
                elif aggregation == AggregationType.AVG:
                    grouped = series.mean()
                elif aggregation == AggregationType.MIN:
                    grouped = series.min()
                elif aggregation == AggregationType.MAX:
                    grouped = series.max()
                else:
                    raise VisualizationError(
                        "unsupported_aggregation",
                        detail=f"aggregation={aggregation!r}",
                    )

        else:
            raise VisualizationError(
                "unsupported_measure_type",
                detail=f"measure_type={measure.measure_type!r}",
            )

        grouped = grouped.dropna()

        if grouped.empty:
            raise VisualizationError("no_data_after_aggregation")

        # Sort descending and keep a reasonable default limit for readability.
        grouped = grouped.sort_values(ascending=False).head(20)

        result = grouped.reset_index()
        return PreparedSeries(
            x=result.iloc[:, 0],
            y=result.iloc[:, 1],
        )

    # ------------------------------------------------------------------
    # Scatter / histogram
    # ------------------------------------------------------------------

    def _draw_scatter(self, ax: Axes, df: pd.DataFrame, config: VisualizationConfig) -> None:
        """Draw a scatter chart."""
        x_col = config.x_column
        y_col = config.y_column

        if not x_col or not y_col:
            raise VisualizationError("scatter_axes_missing")

        if x_col not in df.columns:
            raise VisualizationError(
                "scatter_x_column_not_found",
                detail=f"column={x_col!r}",
            )

        if y_col not in df.columns:
            raise VisualizationError(
                "scatter_y_column_not_found",
                detail=f"column={y_col!r}",
            )

        plot_df = df[[x_col, y_col]].dropna()

        if plot_df.empty:
            raise VisualizationError("scatter_no_data")

        ax.scatter(plot_df[x_col], plot_df[y_col])
        ax.set_xlabel(x_col)
        ax.set_ylabel(y_col)
        ax.set_title(self._chart_title(config))

    def _draw_histogram(self, ax: Axes, df: pd.DataFrame, config: VisualizationConfig) -> None:
        """Draw a histogram."""
        measure = config.measure

        if measure is None:
            raise VisualizationError("measure_missing")

        if measure.measure_type != MeasureType.COLUMN:
            raise VisualizationError("histogram_requires_column_measure")

        if not measure.column:
            raise VisualizationError("histogram_value_column_missing")

        if measure.column not in df.columns:
            raise VisualizationError(
                "histogram_value_column_not_found",
                detail=f"column={measure.column!r}",
            )

        values = pd.to_numeric(df[measure.column], errors="coerce").dropna()

        if values.empty:
            raise VisualizationError("histogram_no_numeric_data")

        ax.hist(values, bins=20)
        ax.set_xlabel(measure.name or measure.column)
        ax.set_ylabel("Count")
        ax.set_title(self._chart_title(config))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _chart_title(self, config: VisualizationConfig) -> str:
        """Return a default chart title."""
        if config.chart_type in {ChartType.BAR, ChartType.LINE, ChartType.PIE}:
            dim = config.category_column or "-"
            measure_label = self._value_axis_label(config)
            return f"{config.chart_type.value.title()}: {dim} / {measure_label}"

        if config.chart_type == ChartType.SCATTER:
            return f"Scatter: {config.x_column or '-'} / {config.y_column or '-'}"

        if config.chart_type == ChartType.HISTOGRAM:
            if config.measure and config.measure.column:
                return f"Histogram: {config.measure.name or config.measure.column}"
            return "Histogram"

        return config.chart_type.value.title()

    def _value_axis_label(self, config: VisualizationConfig) -> str:
        """Return a label for the value axis."""
        measure = config.measure
        if measure is None:
            return ""

        if measure.name:
            return measure.name

        if measure.measure_type == MeasureType.ROW_COUNT:
            return "Row count"

        if measure.column and measure.aggregation:
            return f"{measure.aggregation.value}({measure.column})"

        return measure.column or ""
