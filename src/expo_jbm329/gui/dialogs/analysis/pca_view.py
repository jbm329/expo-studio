"""Principal component analysis result view."""

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

from expo_jbm329.services.analysis.pca import MIN_OBSERVATIONS, MIN_SELECTED_COLUMNS, PCAError
from expo_jbm329.utils.format_utils import fmt_int, fmt_num, fmt_pct

if TYPE_CHECKING:
    from matplotlib.axes import Axes

    from expo_jbm329.services.analysis.pca import PCAResult


_RIGHT_ALIGNED = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter


class PCAView(QWidget):
    """Displays PCA summary, explained variance, loadings and PC1-vs-PC2."""

    def __init__(self, result: PCAResult, parent: QWidget | None = None) -> None:
        """Initialize the result view.

        Args:
            result: Computed PCA result to display.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._result = result
        self._loadings_table: QTableWidget | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        if result.error is not None:
            layout.addWidget(self._build_centered_label(self.error_text(result.error)))
            return

        plots_panel = QWidget(self)
        plots_layout = QVBoxLayout(plots_panel)
        plots_layout.setContentsMargins(0, 0, 0, 0)
        plots_layout.addWidget(self._build_section_title(self.tr("PCA plots"), plots_panel))

        plots = QSplitter(Qt.Orientation.Horizontal, plots_panel)
        plots.setChildrenCollapsible(False)
        plots.addWidget(self._build_scree_plot(result))
        plots.addWidget(self._build_scatter_plot(result))
        plots_layout.addWidget(plots, 1)

        splitter = QSplitter(Qt.Orientation.Vertical, self)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_summary_panel(result))
        splitter.addWidget(plots_panel)
        splitter.addWidget(self._build_loadings_panel(result))
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 4)
        splitter.setStretchFactor(2, 2)
        splitter.setSizes([130, 420, 230])
        layout.addWidget(splitter, 1)

    def configuration(self) -> tuple[tuple[str, ...], bool]:
        """Return the selected columns and scaling used by this displayed fit."""
        return self._result.columns, self._result.standardize

    def loadings_table(self) -> QTableWidget | None:
        """Return the feature-loading table, or `None` for an error result."""
        return self._loadings_table

    def error_text(self, error: PCAError) -> str:
        """Return a translated presentation message for a PCA error."""
        messages = {
            PCAError.NOT_ENOUGH_NUMERIC_COLUMNS: self.tr(
                "A principal component analysis needs at least {minimum} numeric columns."
            ).format(minimum=fmt_int(MIN_SELECTED_COLUMNS)),
            PCAError.NOT_ENOUGH_SELECTED_COLUMNS: self.tr("Select at least {minimum} features.").format(
                minimum=fmt_int(MIN_SELECTED_COLUMNS)
            ),
            PCAError.INVALID_COLUMN: self.tr("Choose two or more different numeric columns."),
            PCAError.NOT_ENOUGH_OBSERVATIONS: self.tr(
                "At least {minimum} complete rows are needed for principal component analysis."
            ).format(minimum=fmt_int(MIN_OBSERVATIONS)),
            PCAError.NO_VARIATION: self.tr("The selected features have no variation across the complete rows."),
        }
        return messages[error]

    def _build_summary(self, result: PCAResult) -> QLabel:
        """Build the fit summary and complete-case warning."""
        scaling = self.tr("standardized") if result.standardize else self.tr("not standardized")
        text = self.tr(
            "<b>{features} features</b>, {scaling}. PCA used {used} of {total} rows "
            "({dropped} dropped because a selected value was missing or infinite)."
        ).format(
            features=fmt_int(len(result.columns)),
            scaling=scaling,
            used=fmt_int(result.rows_used),
            total=fmt_int(result.total_rows),
            dropped=fmt_int(result.rows_dropped),
        )
        if result.sampled:
            text += "<br>" + self.tr("<i>The PC1-vs-PC2 plot shows a deterministic sample of {count} rows.</i>").format(
                count=fmt_int(len(result.sample_pc1))
            )
        label = QLabel(text, self)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        return label

    def _build_summary_panel(self, result: PCAResult) -> QWidget:
        """Build the titled PCA summary section."""
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._build_section_title(self.tr("Summary"), panel))
        layout.addWidget(self._build_summary(result))
        layout.addStretch(1)
        return panel

    def _build_scree_plot(self, result: PCAResult) -> QWidget:
        """Build a scree plot of component and cumulative explained variance."""
        figure = Figure(constrained_layout=True)
        canvas = FigureCanvasQTAgg(figure)  # type: ignore[no-untyped-call]
        canvas.setMinimumSize(280, 220)
        self._draw_scree_plot(figure.add_subplot(111), result)
        return canvas

    def _draw_scree_plot(self, ax: Axes, result: PCAResult) -> None:
        """Draw the per-component bars and cumulative-variance line."""
        positions = np.arange(1, len(result.explained_variance_ratio) + 1)
        percentages = np.asarray(result.explained_variance_ratio) * 100
        cumulative = np.asarray(result.cumulative_variance_ratio) * 100
        ax.bar(positions, percentages, label=self.tr("Explained variance"))
        ax.plot(positions, cumulative, color="tab:red", marker="o", label=self.tr("Cumulative"))
        ax.set_title(self.tr("Scree plot"))
        ax.set_xlabel(self.tr("Component"))
        ax.set_ylabel(self.tr("Explained variance (%)"))
        ax.set_xticks(positions)
        ax.set_ylim(0, 105)
        ax.legend(fontsize=8)

    def _build_scatter_plot(self, result: PCAResult) -> QWidget:
        """Build the PC1-vs-PC2 score scatterplot."""
        figure = Figure(constrained_layout=True)
        canvas = FigureCanvasQTAgg(figure)  # type: ignore[no-untyped-call]
        canvas.setMinimumSize(280, 220)
        self._draw_scatter_plot(figure.add_subplot(111), result)
        return canvas

    def _draw_scatter_plot(self, ax: Axes, result: PCAResult) -> None:
        """Draw PC1 and PC2 scores with their explained-variance labels."""
        pc1, pc2 = result.explained_variance_ratio[:2]
        ax.scatter(result.sample_pc1, result.sample_pc2, s=6, alpha=0.4)
        ax.axhline(0, color="0.7", linewidth=0.8)
        ax.axvline(0, color="0.7", linewidth=0.8)
        ax.set_title(self.tr("PC1 vs PC2"))
        ax.set_xlabel(self.tr("PC1 ({variance})").format(variance=fmt_pct(pc1)))
        ax.set_ylabel(self.tr("PC2 ({variance})").format(variance=fmt_pct(pc2)))

    def _build_loadings_panel(self, result: PCAResult) -> QWidget:
        """Build the feature-loadings table beneath the charts."""
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        label = QLabel(self.tr("<b>Feature loadings</b>"), panel)
        label.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(label)

        headers = [self.tr("Feature"), *(f"PC{index}" for index in range(1, len(result.columns) + 1))]
        table = QTableWidget(panel)
        table.setColumnCount(len(headers))
        table.setRowCount(len(result.columns))
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        table.setAlternatingRowColors(True)
        vheader = table.verticalHeader()
        if vheader is not None:
            vheader.setVisible(False)

        for row, (feature, loadings) in enumerate(zip(result.columns, result.loadings, strict=True)):
            table.setItem(row, 0, QTableWidgetItem(feature))
            for column, loading in enumerate(loadings, start=1):
                item = QTableWidgetItem(fmt_num(loading))
                item.setTextAlignment(_RIGHT_ALIGNED)
                table.setItem(row, column, item)

        table.resizeColumnsToContents()
        hheader = table.horizontalHeader()
        if hheader is not None:
            hheader.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        layout.addWidget(table)
        self._loadings_table = table
        return panel

    def _build_centered_label(self, text: str) -> QLabel:
        """Build a centered, word-wrapped message label."""
        label = QLabel(text, self)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        return label

    @staticmethod
    def _build_section_title(text: str, parent: QWidget) -> QLabel:
        """Build a bold title for a PCA section."""
        label = QLabel(text, parent)
        label.setStyleSheet("font-weight: bold;")
        return label
