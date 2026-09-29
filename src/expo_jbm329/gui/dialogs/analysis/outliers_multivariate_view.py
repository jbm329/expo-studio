"""Result view for multivariate Outlier Explorer screening."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHeaderView,
    QLabel,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from expo_jbm329.services.analysis.multivariate_outliers import (
    MAX_CONTAMINATION,
    MIN_CONTAMINATION,
    MIN_LOF_NEIGHBORS,
    MIN_SELECTED_COLUMNS,
    MultivariateOutlierError,
    MultivariateOutlierMethod,
)
from expo_jbm329.utils.format_utils import fmt_cell, fmt_int, fmt_num, fmt_pct

if TYPE_CHECKING:
    from matplotlib.axes import Axes

    from expo_jbm329.services.analysis.multivariate_outliers import MultivariateOutlierResult

_RIGHT_ALIGNED = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
_FIXED_TABLE_COLUMNS = 2


class MultivariateOutliersView(QWidget):
    """Displays multivariate anomaly summary, PCA projection and flagged rows."""

    def __init__(self, result: MultivariateOutlierResult, parent: QWidget | None = None) -> None:
        """Initialize the view from a multivariate anomaly fit."""
        super().__init__(parent)
        self._result = result
        self._extremes_table: QTableWidget | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        if result.error is not None:
            layout.addWidget(self._centered_label(self.error_text(result.error)))
            return

        layout.addWidget(self._summary_label(result))
        splitter = QSplitter(Qt.Orientation.Vertical, self)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._projection(result))
        splitter.addWidget(self._extremes_panel(result))
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
        match method:
            case MultivariateOutlierMethod.ISOLATION_FOREST:
                return self.tr("Isolation Forest")
            case MultivariateOutlierMethod.LOCAL_OUTLIER_FACTOR:
                return self.tr("Local Outlier Factor")

    def _summary_label(self, result: MultivariateOutlierResult) -> QLabel:
        """Build an explanatory fit summary."""
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
            text += "<br>" + self.tr("<i>The projection shows a deterministic sample of {count} rows.</i>").format(
                count=fmt_int(len(result.sample_outliers))
            )
        text += "<br>" + self.tr(
            "<i>Scores rank observations within this fit. Potential outliers are not necessarily errors.</i>"
        )
        label = QLabel(text, self)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setWordWrap(True)
        return label

    def _projection(self, result: MultivariateOutlierResult) -> QWidget:
        """Build a PCA visualization colored by flagged status."""
        figure = Figure(constrained_layout=True)
        canvas = FigureCanvasQTAgg(figure)  # type: ignore[no-untyped-call]
        canvas.setMinimumSize(360, 240)
        self._draw_projection(figure.add_subplot(111), result)
        return canvas

    def _draw_projection(self, axis: Axes, result: MultivariateOutlierResult) -> None:
        """Draw internal PCA plot without implying that the model used only two features."""
        x = np.asarray(result.sample_pc1)
        y = np.asarray(result.sample_pc2)
        outliers = np.asarray(result.sample_outliers)
        axis.scatter(x[~outliers], y[~outliers], s=7, alpha=0.35, label=self.tr("Inliers"))
        axis.scatter(x[outliers], y[outliers], s=12, alpha=0.7, color="tab:red", label=self.tr("Potential outliers"))
        axis.axhline(0, color="0.8", linewidth=0.8)
        axis.axvline(0, color="0.8", linewidth=0.8)
        axis.set_title(self.tr("PCA projection (visualization only)"))
        axis.set_xlabel(self.tr("PC1"))
        axis.set_ylabel(self.tr("PC2"))
        axis.legend(fontsize=8)

    def _extremes_panel(self, result: MultivariateOutlierResult) -> QWidget:
        """Build the ranked top-100 flagged-observation table."""
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        if not result.extremes:
            layout.addWidget(QLabel(self.tr("<b>No potential outliers</b>"), panel))
            return panel

        title = QLabel(self.tr("<b>Potential outliers, most anomalous first</b>"), panel)
        title.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(title)
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
        layout.addWidget(table)
        self._extremes_table = table
        return panel

    def _centered_label(self, text: str) -> QLabel:
        """Build a centered, word-wrapped message label."""
        label = QLabel(text, self)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        return label
