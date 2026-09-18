"""Chart builder for dataset visualizations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pandas as pd
from pandas.api.types import is_numeric_dtype

from expo_jbm329.utils.visualization_models import (
    AggregationType,
    ChartType,
    MeasureType,
    VisualizationConfig,
)

if TYPE_CHECKING:
    from matplotlib.axes import Axes


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
            msg = "dataset_empty"
            raise VisualizationError(msg)

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

        msg = "unsupported_chart_type"
        raise VisualizationError(
            msg,
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
            msg = "pie_no_data"
            raise VisualizationError(msg)

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
            msg = "category_column_missing"
            raise VisualizationError(msg)

        if category_col not in df.columns:
            msg = "category_column_not_found"
            raise VisualizationError(
                msg,
                detail=f"column={category_col!r}",
            )

        if measure is None:
            msg = "measure_missing"
            raise VisualizationError(msg)

        grouped: pd.Series

        if measure.measure_type == MeasureType.ROW_COUNT:
            grouped = df.groupby(category_col, dropna=False).size()

        elif measure.measure_type == MeasureType.COLUMN:
            column = measure.column
            aggregation = measure.aggregation

            if not column:
                msg = "value_column_missing"
                raise VisualizationError(msg)

            if column not in df.columns:
                msg = "value_column_not_found"
                raise VisualizationError(
                    msg,
                    detail=f"column={column!r}",
                )

            if aggregation is None:
                msg = "aggregation_missing"
                raise VisualizationError(msg)

            series = df.groupby(category_col, dropna=False)[column]

            if aggregation == AggregationType.COUNT:
                grouped = series.count()

            elif aggregation == AggregationType.COUNT_DISTINCT:
                grouped = series.nunique()

            else:
                if not is_numeric_dtype(df[column]):
                    msg = "non_numeric_measure_requires_count"
                    raise VisualizationError(
                        msg,
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
                    msg = "unsupported_aggregation"
                    raise VisualizationError(
                        msg,
                        detail=f"aggregation={aggregation!r}",
                    )

        else:
            msg = "unsupported_measure_type"
            raise VisualizationError(
                msg,
                detail=f"measure_type={measure.measure_type!r}",
            )

        grouped = grouped.dropna()

        if grouped.empty:
            msg = "no_data_after_aggregation"
            raise VisualizationError(msg)

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
            msg = "scatter_axes_missing"
            raise VisualizationError(msg)

        if x_col not in df.columns:
            msg = "scatter_x_column_not_found"
            raise VisualizationError(
                msg,
                detail=f"column={x_col!r}",
            )

        if y_col not in df.columns:
            msg = "scatter_y_column_not_found"
            raise VisualizationError(
                msg,
                detail=f"column={y_col!r}",
            )

        plot_df = df[[x_col, y_col]].dropna()

        if plot_df.empty:
            msg = "scatter_no_data"
            raise VisualizationError(msg)

        ax.scatter(plot_df[x_col], plot_df[y_col])
        ax.set_xlabel(x_col)
        ax.set_ylabel(y_col)
        ax.set_title(self._chart_title(config))

    def _draw_histogram(self, ax: Axes, df: pd.DataFrame, config: VisualizationConfig) -> None:
        """Draw a histogram."""
        measure = config.measure

        if measure is None:
            msg = "measure_missing"
            raise VisualizationError(msg)

        if measure.measure_type != MeasureType.COLUMN:
            msg = "histogram_requires_column_measure"
            raise VisualizationError(msg)

        if not measure.column:
            msg = "histogram_value_column_missing"
            raise VisualizationError(msg)

        if measure.column not in df.columns:
            msg = "histogram_value_column_not_found"
            raise VisualizationError(
                msg,
                detail=f"column={measure.column!r}",
            )

        values = pd.to_numeric(df[measure.column], errors="coerce").dropna()

        if values.empty:
            msg = "histogram_no_numeric_data"
            raise VisualizationError(msg)

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
