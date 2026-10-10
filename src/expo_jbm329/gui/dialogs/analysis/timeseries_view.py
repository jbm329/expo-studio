"""Result view for time-series analysis."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from expo_jbm329.services.analysis.timeseries import TimeSeriesError
from expo_jbm329.utils.format_utils import fmt_int

if TYPE_CHECKING:
    from matplotlib.axes import Axes

    from expo_jbm329.services.analysis.timeseries import TimeSeriesResult


class TimeSeriesView(QWidget):
    """Displays the source series, autocorrelation and seasonal components."""

    def __init__(self, result: TimeSeriesResult, parent: QWidget | None = None) -> None:
        """Initialize a view from one complete time-series result."""
        super().__init__(parent)
        self._result = result
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        if result.error is not None:
            root.addWidget(self._centered_label(self.error_text(result.error)))
            return

        root.addWidget(self._build_summary_section(result))
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        content = QWidget(scroll)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._series_plot(result))
        layout.addWidget(self._acf_plot(result))
        layout.addWidget(self._decomposition_plot(result))
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

    def configuration(self) -> tuple[str, str, str | None, int | None, object]:
        """Return the parameters of the displayed result."""
        result = self._result
        return (
            result.datetime_column,
            result.value_column,
            result.resample_frequency,
            result.seasonal_period,
            result.decomposition_model,
        )

    def error_text(self, error: TimeSeriesError) -> str:
        """Return translated text for `error`."""
        messages = {
            TimeSeriesError.NO_DATETIME_COLUMN: self.tr("A time series needs at least one datetime column."),
            TimeSeriesError.NO_NUMERIC_COLUMN: self.tr("A time series needs at least one numeric value column."),
            TimeSeriesError.INVALID_DATETIME_COLUMN: self.tr("Choose a datetime column."),
            TimeSeriesError.INVALID_VALUE_COLUMN: self.tr("Choose a numeric value column."),
            TimeSeriesError.INVALID_FREQUENCY: self.tr("Choose a valid resampling frequency."),
            TimeSeriesError.INVALID_SEASONAL_PERIOD: self.tr("Choose a seasonal period of at least 2."),
            TimeSeriesError.NOT_ENOUGH_OBSERVATIONS: self.tr("At least 3 valid time observations are needed."),
        }
        return messages[error]

    def _build_summary_section(self, result: TimeSeriesResult) -> QWidget:
        """Build a content-sized summary separate from the scrolling charts."""
        panel = QWidget(self)
        panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        heading = QLabel(self.tr("Summary"), panel)
        heading.setStyleSheet("font-weight: bold;")
        layout.addWidget(heading)
        layout.addWidget(self._summary_label(result))
        layout.addStretch(1)
        return panel

    def _summary_label(self, result: TimeSeriesResult) -> QLabel:
        """Build a text summary with data-cleaning diagnostics."""
        frequency = result.detected_frequency or self.tr("irregular")
        text = self.tr(
            "<b>{value}</b> by <b>{time}</b>: {points} time points, frequency {frequency}. "
            "{invalid} invalid rows dropped. {duplicates} duplicate rows averaged."
        ).format(
            value=result.value_column,
            time=result.datetime_column,
            points=fmt_int(len(result.timestamps)),
            frequency=frequency,
            invalid=fmt_int(result.invalid_rows),
            duplicates=fmt_int(result.duplicate_rows),
        )
        label = QLabel(text, self)
        label.setWordWrap(True)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        return label

    def _canvas(self, height: int = 220) -> tuple[FigureCanvasQTAgg, Axes]:
        """Build a constrained matplotlib canvas and one subplot."""
        figure = Figure(constrained_layout=True)
        canvas = FigureCanvasQTAgg(figure)  # type: ignore[no-untyped-call]
        canvas.setMinimumHeight(height)
        return canvas, figure.add_subplot(111)

    def _series_plot(self, result: TimeSeriesResult) -> QWidget:
        """Build the original or resampled series chart."""
        canvas, axis = self._canvas()
        axis.plot(result.timestamps, result.values, marker="o", markersize=3)  # type: ignore[arg-type]
        axis.set_title(self.tr("Series"))
        axis.set_ylabel(result.value_column)
        axis.tick_params(axis="x", rotation=30)
        return canvas

    def _acf_plot(self, result: TimeSeriesResult) -> QWidget:
        """Build ACF stems or an explanation when the metric is unavailable."""
        canvas, axis = self._canvas()
        if result.acf_values:
            lags = np.arange(1, len(result.acf_values) + 1)
            axis.vlines(lags, 0, result.acf_values)
            axis.scatter(lags, result.acf_values, s=12)
            axis.axhline(0, color="0.5", linewidth=0.8)
            axis.set_xlabel(self.tr("Lag"))
            axis.set_ylabel(self.tr("Autocorrelation"))
        else:
            axis.text(0.5, 0.5, result.diagnostics_note or "", ha="center", va="center", wrap=True)
            axis.set_axis_off()
        axis.set_title(self.tr("Autocorrelation"))
        return canvas

    def _decomposition_plot(self, result: TimeSeriesResult) -> QWidget:
        """Build seasonal components or show why decomposition is unavailable."""
        if not result.trend:
            canvas, axis = self._canvas()
            axis.text(0.5, 0.5, result.decomposition_note or "", ha="center", va="center", wrap=True)
            axis.set_title(self.tr("Seasonal decomposition"))
            axis.set_axis_off()
            return canvas

        figure = Figure(constrained_layout=True)
        canvas = FigureCanvasQTAgg(figure)  # type: ignore[no-untyped-call]
        canvas.setMinimumHeight(400)
        labels = (self.tr("Observed"), self.tr("Trend"), self.tr("Seasonal"), self.tr("Residual"))
        series = (result.values, result.trend, result.seasonal, result.residual)
        axes = figure.subplots(4, 1, sharex=True)
        for axis, label, values in zip(axes, labels, series, strict=True):
            axis.plot(result.timestamps, values)
            axis.set_ylabel(label)
        axes[0].set_title(self.tr("Seasonal decomposition"))
        axes[-1].tick_params(axis="x", rotation=30)
        return canvas

    def _centered_label(self, text: str) -> QLabel:
        """Build centered error text."""
        label = QLabel(text, self)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        return label
