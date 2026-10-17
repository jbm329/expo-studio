"""Result view for time-series analysis."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QSplitter, QVBoxLayout, QWidget

from expo_jbm329.gui.dialogs.analysis.section_layout import (
    AnalysisResultSection,
    build_section_scroll_area,
    rich_text_lines,
)
from expo_jbm329.gui.widgets.analysis_chart_canvas import SerializedAnalysisCanvas
from expo_jbm329.services.analysis.chart_layout import ChartFigure as Figure
from expo_jbm329.services.analysis.presentation import PresentationLabel, translate_presentation_label
from expo_jbm329.services.analysis.timeseries import DecompositionModel, TimeSeriesError
from expo_jbm329.services.analysis.timeseries_charts import (
    DECOMPOSITION_PANELS,
    TimeSeriesChartLabels,
    build_time_series_chart_labels,
    draw_acf_plot,
    draw_decomposition,
    draw_series_plot,
    has_autocorrelation,
    has_decomposition,
)
from expo_jbm329.utils.format_utils import fmt_int
from expo_jbm329.utils.i18n_utils import tr

if TYPE_CHECKING:
    from matplotlib.axes import Axes

    from expo_jbm329.services.analysis.timeseries import TimeSeriesResult


class TimeSeriesView(QWidget):
    """Displays charts and model comments in resizable sections."""

    def __init__(self, result: TimeSeriesResult, parent: QWidget | None = None) -> None:
        """Initialize a view from one complete time-series result."""
        super().__init__(parent)
        self._result = result
        self._chart_labels = build_time_series_chart_labels(result, tr)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        if result.error is not None:
            root.addWidget(self._centered_label(self.error_text(result.error)))
            return

        splitter = QSplitter(Qt.Orientation.Vertical, self)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_charts_section(result))
        splitter.addWidget(self._build_comments_section(result))
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([600, 130])
        root.addWidget(splitter, 1)

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

    def result(self) -> TimeSeriesResult:
        """Return the displayed time-series analysis."""
        return self._result

    def chart_labels(self) -> TimeSeriesChartLabels:
        """Return the translated plot text used by the view and its export."""
        return self._chart_labels

    def export_notes(self) -> tuple[str, ...]:
        """Return the displayed comments, decomposition model and unavailability reasons.

        Returns:
            Plain-text lines, or an empty tuple when the view shows an error.
        """
        result = self._result
        if result.error is not None:
            return ()
        models = {
            DecompositionModel.ADDITIVE: translate_presentation_label(PresentationLabel.TIME_SERIES_ADDITIVE, tr),
            DecompositionModel.MULTIPLICATIVE: translate_presentation_label(
                PresentationLabel.TIME_SERIES_MULTIPLICATIVE, tr
            ),
        }
        lines = [
            *rich_text_lines([self._summary_text(result)]),
            (
                f"{translate_presentation_label(PresentationLabel.TIME_SERIES_DECOMPOSITION_MODEL, tr)} "
                f"{models[result.decomposition_model]}"
            ),
        ]
        lines.extend(self.note_text(note) for note in (result.diagnostics_note, result.decomposition_note) if note)
        return tuple(lines)

    def autocorrelation_note(self) -> str:
        """Return the translated reason the autocorrelation is unavailable, or an empty string."""
        note = self._result.diagnostics_note
        return self.note_text(note) if note else ""

    def note_text(self, note: str) -> str:
        """Return the translated explanation of why a diagnostic is unavailable.

        Args:
            note: English explanation produced by the time-series service.

        Returns:
            The translation, or `note` unchanged when it is not a known explanation.
        """
        translations = {
            "The autocorrelation requires a regular time frequency.": self.tr(
                "The autocorrelation requires a regular time frequency."
            ),
            "The autocorrelation is unavailable while the series has gaps.": self.tr(
                "The autocorrelation is unavailable while the series has gaps."
            ),
            "Seasonal decomposition requires a regular time frequency.": self.tr(
                "Seasonal decomposition requires a regular time frequency."
            ),
            "Seasonal decomposition is unavailable while the series has gaps.": self.tr(
                "Seasonal decomposition is unavailable while the series has gaps."
            ),
            "No seasonal period could be detected; choose one to decompose the series.": self.tr(
                "No seasonal period could be detected; choose one to decompose the series."
            ),
            "Seasonal decomposition needs at least two complete seasonal cycles.": self.tr(
                "Seasonal decomposition needs at least two complete seasonal cycles."
            ),
            "Multiplicative decomposition requires all values to be greater than zero.": self.tr(
                "Multiplicative decomposition requires all values to be greater than zero."
            ),
        }
        return translations.get(note, note)

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

    def _build_charts_section(self, result: TimeSeriesResult) -> QWidget:
        """Build the titled section with all charts in one scroll area."""
        panel, layout = self._build_section(self.tr("Charts"))
        content = QWidget(panel)
        charts = QVBoxLayout(content)
        charts.setContentsMargins(0, 0, 0, 0)
        charts.addWidget(self._series_plot(result))
        charts.addWidget(self._acf_plot(result))
        charts.addWidget(self._decomposition_plot(result))
        layout.addWidget(build_section_scroll_area(content, panel), 1)
        return panel

    def _build_comments_section(self, result: TimeSeriesResult) -> QWidget:
        """Build the titled model-comments section with a scrollable summary."""
        return AnalysisResultSection(self.tr("Model comments"), self._summary_label(result), self)

    def _build_section(self, title: str) -> tuple[QWidget, QVBoxLayout]:
        """Build a titled section matching the Regression layout."""
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        label = QLabel(title, panel)
        label.setTextFormat(Qt.TextFormat.PlainText)
        font = label.font()
        font.setBold(True)
        label.setFont(font)
        layout.addWidget(label)
        return panel, layout

    def _summary_text(self, result: TimeSeriesResult) -> str:
        """Return the rich-text summary with data-cleaning diagnostics."""
        frequency = result.detected_frequency or self.tr("irregular")
        return self.tr(
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

    def _summary_label(self, result: TimeSeriesResult) -> QLabel:
        """Build a text summary with data-cleaning diagnostics."""
        label = QLabel(self._summary_text(result), self)
        label.setWordWrap(True)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        return label

    def _canvas(self, height: int = 220) -> tuple[SerializedAnalysisCanvas, Figure]:
        """Build a constrained canvas whose chart construction can be deferred."""
        figure = Figure(constrained_layout=True)
        canvas = SerializedAnalysisCanvas(figure)
        canvas.setMinimumHeight(height)
        return canvas, figure

    def _series_plot(self, result: TimeSeriesResult) -> QWidget:
        """Build the original or resampled series chart."""
        canvas, figure = self._canvas()
        canvas.build_chart(lambda: draw_series_plot(figure.add_subplot(111), result, self.chart_labels()))
        return canvas

    def _acf_plot(self, result: TimeSeriesResult) -> QWidget:
        """Build ACF stems or an explanation when the metric is unavailable."""
        canvas, figure = self._canvas()
        labels = self.chart_labels()
        if has_autocorrelation(result):
            canvas.build_chart(lambda: draw_acf_plot(figure.add_subplot(111), result, labels))
        else:
            canvas.build_chart(
                lambda: self._draw_unavailable(
                    figure.add_subplot(111), labels.acf_metadata.accessible_name, result.diagnostics_note
                )
            )
        return canvas

    def _decomposition_plot(self, result: TimeSeriesResult) -> QWidget:
        """Build seasonal components or show why decomposition is unavailable."""
        labels = self.chart_labels()
        if not has_decomposition(result):
            canvas, figure = self._canvas()
            canvas.build_chart(
                lambda: self._draw_unavailable(
                    figure.add_subplot(111), labels.decomposition_metadata.accessible_name, result.decomposition_note
                )
            )
            return canvas

        figure = Figure(constrained_layout=True)
        canvas = SerializedAnalysisCanvas(figure)
        canvas.setMinimumHeight(400)
        canvas.build_chart(
            lambda: draw_decomposition(list(figure.subplots(DECOMPOSITION_PANELS, 1, sharex=True)), result, labels)
        )
        return canvas

    def _draw_unavailable(self, axis: Axes, title: str, note: str | None) -> None:
        """Draw a titled, axis-free explanation in place of an unavailable chart."""
        axis.text(0.5, 0.5, self.note_text(note) if note else "", ha="center", va="center", wrap=True)
        axis.set_title(title)
        axis.set_axis_off()

    def _centered_label(self, text: str) -> QLabel:
        """Build centered error text."""
        label = QLabel(text, self)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        return label
