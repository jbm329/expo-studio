"""Result view for multivariate Outlier Explorer screening."""

from __future__ import annotations

from typing import TYPE_CHECKING

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PyQt6.QtCore import QCoreApplication, Qt
from PyQt6.QtWidgets import (
    QHeaderView,
    QLabel,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from expo_jbm329.gui.dialogs.analysis.section_layout import (
    AnalysisResultSection,
    build_section_scroll_area,
    rich_text_lines,
)
from expo_jbm329.services.analysis.multivariate_outliers import (
    MAX_CONTAMINATION,
    MIN_CONTAMINATION,
    MIN_LOF_NEIGHBORS,
    MIN_SELECTED_COLUMNS,
    MultivariateOutlierError,
    MultivariateOutlierMethod,
)
from expo_jbm329.services.analysis.outliers_charts import (
    OutlierProjectionLabels,
    build_outlier_projection_labels,
    draw_outlier_projection,
)
from expo_jbm329.services.analysis.presentation import multivariate_outlier_method_label
from expo_jbm329.utils.format_utils import fmt_cell, fmt_int, fmt_num, fmt_pct

if TYPE_CHECKING:
    from expo_jbm329.services.analysis.multivariate_outliers import MultivariateOutlierResult

_RIGHT_ALIGNED = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
_FIXED_TABLE_COLUMNS = 2


class MultivariateOutliersView(QWidget):
    """Displays flagged rows, a PCA projection and model comments in resizable sections."""

    def __init__(self, result: MultivariateOutlierResult, parent: QWidget | None = None) -> None:
        """Initialize the view from a multivariate anomaly fit."""
        super().__init__(parent)
        self._result = result
        self._chart_labels = build_outlier_projection_labels(result, QCoreApplication.translate, count_format=fmt_int)
        self._extremes_table: QTableWidget | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        if result.error is not None:
            layout.addWidget(self._centered_label(self.error_text(result.error)))
            return

        splitter = QSplitter(Qt.Orientation.Vertical, self)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._extremes_panel(result))
        splitter.addWidget(self._projection_panel(result))
        splitter.addWidget(self._comments_panel(result))
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setStretchFactor(2, 1)
        splitter.setSizes([250, 350, 160])
        layout.addWidget(splitter, 1)

    def configuration(self) -> tuple[tuple[str, ...], MultivariateOutlierMethod, bool, float, int]:
        """Return the displayed fit configuration."""
        result = self._result
        return result.columns, result.method, result.standardize, result.contamination, result.lof_neighbors

    def extremes_table(self) -> QTableWidget | None:
        """Return the ranked anomalous-observation table, if there are rows."""
        return self._extremes_table

    def error_text(self, error: MultivariateOutlierError) -> str:
        """Return translated display text for a structured service error."""
        messages = {
            MultivariateOutlierError.NOT_ENOUGH_NUMERIC_COLUMNS: self.tr(
                "Multivariate screening needs at least {minimum} numeric columns."
            ).format(minimum=fmt_int(MIN_SELECTED_COLUMNS)),
            MultivariateOutlierError.NOT_ENOUGH_SELECTED_COLUMNS: self.tr("Select at least {minimum} features.").format(
                minimum=fmt_int(MIN_SELECTED_COLUMNS)
            ),
            MultivariateOutlierError.INVALID_COLUMN: self.tr("Choose two or more different numeric columns."),
            MultivariateOutlierError.NOT_ENOUGH_OBSERVATIONS: self.tr(
                "At least {minimum} complete rows are needed for multivariate screening."
            ).format(minimum=fmt_int(3)),
            MultivariateOutlierError.NO_VARIATION: self.tr(
                "The selected features have no variation across the complete rows."
            ),
            MultivariateOutlierError.INVALID_CONTAMINATION: self.tr(
                "Choose an expected outlier fraction between {minimum} and {maximum}."
            ).format(minimum=fmt_pct(MIN_CONTAMINATION), maximum=fmt_pct(MAX_CONTAMINATION)),
            MultivariateOutlierError.INVALID_LOF_NEIGHBORS: self.tr(
                "Choose at least {minimum} LOF neighbors and fewer than the complete rows."
            ).format(minimum=fmt_int(MIN_LOF_NEIGHBORS)),
        }
        return messages[error]

    def method_name(self, method: MultivariateOutlierMethod) -> str:
        """Return the translated display name for `method`."""
        return multivariate_outlier_method_label(method, QCoreApplication.translate)

    def result(self) -> MultivariateOutlierResult:
        """Return the displayed multivariate fit."""
        return self._result

    def chart_labels(self) -> OutlierProjectionLabels:
        """Return the translated projection text used by the view and its export."""
        return self._chart_labels

    def export_notes(self) -> tuple[str, ...]:
        """Return the displayed model comments and applied features as plain-text lines.

        Returns:
            The lines, or an empty tuple when the view shows an error.
        """
        result = self._result
        if result.error is not None:
            return ()
        features = self.tr("Features: {columns}").format(columns=", ".join(result.columns))
        return (*rich_text_lines([self._summary_text(result)]), features)

    def _comments_panel(self, result: MultivariateOutlierResult) -> QWidget:
        """Build the titled model-comments section with a scrollable fit summary."""
        return AnalysisResultSection(self.tr("Model comments"), self._summary_label(result), self)

    def _summary_label(self, result: MultivariateOutlierResult) -> QLabel:
        """Build an explanatory fit summary."""
        label = QLabel(self._summary_text(result), self)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        return label

    def _summary_text(self, result: MultivariateOutlierResult) -> str:
        """Return the rich-text fit summary with its sampling and interpretation caveats."""
        scaling = self.tr("standardized") if result.standardize else self.tr("not standardized")
        text = self.tr(
            "<b>{method}</b> on {features} features ({scaling}): {outliers} of {used} complete rows "
            "({percent}) are potential outliers. {dropped} rows were dropped for missing or infinite values."
        ).format(
            method=self.method_name(result.method),
            features=fmt_int(len(result.columns)),
            scaling=scaling,
            outliers=fmt_int(result.outlier_count),
            used=fmt_int(result.rows_used),
            percent=fmt_pct(result.outlier_count / result.rows_used),
            dropped=fmt_int(result.rows_dropped),
        )
        if result.sampled:
            text += "<br>" + self._sample_text()
        text += "<br>" + self.tr(
            "<i>Scores rank observations within this fit. Potential outliers are not necessarily errors.</i>"
        )
        return text

    def _sample_text(self) -> str:
        """Return the rich-text note that the projection shows a sample."""
        return "<i>" + " ".join(self._chart_labels.metadata.captions) + "</i>"

    def _projection_panel(self, result: MultivariateOutlierResult) -> QWidget:
        """Build the scrollable PCA visualization colored by flagged status."""
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        figure = Figure(constrained_layout=True)
        canvas = FigureCanvasQTAgg(figure)  # type: ignore[no-untyped-call]
        canvas.setMinimumSize(360, 240)
        draw_outlier_projection(figure.add_subplot(111), result, self.chart_labels())
        layout.addWidget(build_section_scroll_area(canvas, panel), 1)
        if self._chart_labels.metadata.captions:
            caption = QLabel("\n".join(self._chart_labels.metadata.captions), panel)
            caption.setTextFormat(Qt.TextFormat.PlainText)
            caption.setWordWrap(True)
            layout.addWidget(caption)
        return panel

    def _extremes_panel(self, result: MultivariateOutlierResult) -> QWidget:
        """Build the titled, ranked top-100 flagged-observation table."""
        if not result.extremes:
            panel, layout = self._build_section(self.tr("Potential outliers"))
            message = QLabel(self.tr("No potential outliers"), panel)
            message.setTextFormat(Qt.TextFormat.PlainText)
            message.setWordWrap(True)
            message.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(message)
            layout.addStretch(1)
            return panel

        panel, layout = self._build_section(self.tr("Potential outliers, most anomalous first"))
        headers = [self.tr("Row"), self.tr("Anomaly score"), *result.row_columns]
        table = QTableWidget(panel)
        table.setColumnCount(len(headers))
        table.setRowCount(len(result.extremes))
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        table.setAlternatingRowColors(True)
        vertical_header = table.verticalHeader()
        if vertical_header is not None:
            vertical_header.setVisible(False)

        for row, observation in enumerate(result.extremes):
            values = [
                fmt_int(observation.row_number),
                fmt_num(observation.score),
                *map(fmt_cell, observation.row_values),
            ]
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                if column < _FIXED_TABLE_COLUMNS:
                    item.setTextAlignment(_RIGHT_ALIGNED)
                table.setItem(row, column, item)
        table.resizeColumnsToContents()
        header = table.horizontalHeader()
        if header is not None:
            header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        layout.addWidget(table, 1)
        self._extremes_table = table
        return panel

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

    def _centered_label(self, text: str) -> QLabel:
        """Build a centered, word-wrapped message label."""
        label = QLabel(text, self)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        return label
