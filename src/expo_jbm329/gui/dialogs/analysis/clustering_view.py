"""Result view for numeric clustering."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHeaderView, QLabel, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from expo_jbm329.services.analysis.clustering import (
    MIN_OBSERVATIONS,
    MIN_SELECTED_COLUMNS,
    ClusteringError,
    ClusteringMethod,
)
from expo_jbm329.utils.format_utils import fmt_int, fmt_num

if TYPE_CHECKING:
    from matplotlib.axes import Axes

    from expo_jbm329.services.analysis.clustering import ClusteringResult

_RIGHT_ALIGNED = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter


class ClusteringView(QWidget):
    """Displays cluster summary, membership counts and an internal PCA plot."""

    def __init__(self, result: ClusteringResult, parent: QWidget | None = None) -> None:
        """Initialize the view for `result`."""
        super().__init__(parent)
        self._result = result
        self._cluster_table: QTableWidget | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        if result.error is not None:
            layout.addWidget(self._centered_label(self.error_text(result.error)))
            return

        splitter = QSplitter(Qt.Orientation.Vertical, self)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_summary_section(result))
        splitter.addWidget(self._build_plot_section(result))
        splitter.addWidget(self._build_table_section(result))
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 4)
        splitter.setStretchFactor(2, 2)
        splitter.setSizes([130, 430, 220])
        layout.addWidget(splitter, 1)

    def configuration(self) -> tuple[tuple[str, ...], ClusteringMethod, bool, int, float, int]:
        """Return the configuration of the displayed fit."""
        result = self._result
        return (
            result.columns,
            result.method,
            result.standardize,
            result.cluster_count,
            result.dbscan_epsilon,
            result.dbscan_min_samples,
        )

    def cluster_table(self) -> QTableWidget | None:
        """Return the cluster size table, or `None` for errors."""
        return self._cluster_table

    def error_text(self, error: ClusteringError) -> str:
        """Return translated presentation text for a clustering error."""
        messages = {
            ClusteringError.NOT_ENOUGH_NUMERIC_COLUMNS: self.tr(
                "A clustering analysis needs at least {minimum} numeric columns."
            ).format(minimum=fmt_int(MIN_SELECTED_COLUMNS)),
            ClusteringError.NOT_ENOUGH_SELECTED_COLUMNS: self.tr("Select at least {minimum} features.").format(
                minimum=fmt_int(MIN_SELECTED_COLUMNS)
            ),
            ClusteringError.INVALID_COLUMN: self.tr("Choose two or more different numeric columns."),
            ClusteringError.NOT_ENOUGH_OBSERVATIONS: self.tr(
                "At least {minimum} complete rows are needed for clustering."
            ).format(minimum=fmt_int(MIN_OBSERVATIONS)),
            ClusteringError.NO_VARIATION: self.tr("The selected features have no variation across the complete rows."),
            ClusteringError.INVALID_CLUSTER_COUNT: self.tr(
                "Choose a number of clusters that is valid for the complete rows."
            ),
            ClusteringError.INVALID_DBSCAN_EPSILON: self.tr("Choose a valid DBSCAN neighborhood radius."),
            ClusteringError.INVALID_DBSCAN_MIN_SAMPLES: self.tr("Choose a valid DBSCAN minimum sample count."),
        }
        return messages[error]

    def method_name(self, method: ClusteringMethod) -> str:
        """Return the translated display name of `method`."""
        match method:
            case ClusteringMethod.K_MEANS:
                return self.tr("K-Means")
            case ClusteringMethod.DBSCAN:
                return self.tr("DBSCAN")
            case ClusteringMethod.AGGLOMERATIVE:
                return self.tr("Agglomerative")

    def _summary_label(self, result: ClusteringResult) -> QLabel:
        """Build summary of method, preprocessing, rows and silhouette."""
        scaling = self.tr("standardized") if result.standardize else self.tr("not standardized")
        text = self.tr(
            "<b>{method}</b> on {features} features ({scaling}). Used {used} of {total} rows "
            "({dropped} dropped because a selected value was missing or infinite)."
        ).format(
            method=self.method_name(result.method),
            features=fmt_int(len(result.columns)),
            scaling=scaling,
            used=fmt_int(result.rows_used),
            total=fmt_int(result.total_rows),
            dropped=fmt_int(result.rows_dropped),
        )
        if result.silhouette_score is None:
            text += "<br>" + self.tr("Silhouette score: not available for this clustering.")
        else:
            text += "<br>" + self.tr("Silhouette score: {score}").format(score=fmt_num(result.silhouette_score))
        if result.sampled:
            text += "<br>" + self.tr("<i>The plot shows a deterministic sample of {count} rows.</i>").format(
                count=fmt_int(len(result.sample_labels))
            )
        label = QLabel(text, self)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setWordWrap(True)
        return label

    def _build_summary_section(self, result: ClusteringResult) -> QWidget:
        """Build the titled clustering summary section."""
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._build_section_title(self.tr("Summary"), panel))
        layout.addWidget(self._summary_label(result))
        return panel

    def _build_plot_section(self, result: ClusteringResult) -> QWidget:
        """Build the titled cluster projection section."""
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._build_section_title(self.tr("Cluster projection"), panel))
        layout.addWidget(self._build_plot(result))
        return panel

    def _build_table_section(self, result: ClusteringResult) -> QWidget:
        """Build the titled cluster-size table section."""
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._build_section_title(self.tr("Cluster sizes"), panel))
        layout.addWidget(self._build_cluster_table(result))
        return panel

    def _build_plot(self, result: ClusteringResult) -> QWidget:
        """Build the internal PCA projection colored by cluster label."""
        figure = Figure(constrained_layout=True)
        canvas = FigureCanvasQTAgg(figure)  # type: ignore[no-untyped-call]
        canvas.setMinimumSize(420, 260)
        self._draw_plot(figure.add_subplot(111), result)
        return canvas

    def _draw_plot(self, ax: Axes, result: ClusteringResult) -> None:
        """Draw the internal two-component PCA projection with cluster colors."""
        labels = np.asarray(result.sample_labels)
        x = np.asarray(result.sample_pc1)
        y = np.asarray(result.sample_pc2)
        for label in sorted(set(labels.tolist())):
            mask = labels == label
            name = self.tr("Noise") if label == -1 else self.tr("Cluster {number}").format(number=label + 1)
            color = "0.5" if label == -1 else None
            ax.scatter(x[mask], y[mask], s=8, alpha=0.5, label=name, color=color)
        ax.axhline(0, color="0.8", linewidth=0.8)
        ax.axvline(0, color="0.8", linewidth=0.8)
        ax.set_title(self.tr("Cluster projection (internal PCA)"))
        ax.set_xlabel(self.tr("PC1"))
        ax.set_ylabel(self.tr("PC2"))
        ax.legend(fontsize=8)

    def _build_cluster_table(self, result: ClusteringResult) -> QTableWidget:
        """Build cluster membership counts, with a DBSCAN noise row if applicable."""
        rows = len(result.clusters) + int(result.noise_count > 0)
        table = QTableWidget(self)
        table.setColumnCount(2)
        table.setRowCount(rows)
        table.setHorizontalHeaderLabels([self.tr("Cluster"), self.tr("Rows")])
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        table.setAlternatingRowColors(True)
        vheader = table.verticalHeader()
        if vheader is not None:
            vheader.setVisible(False)

        for row, cluster in enumerate(result.clusters):
            table.setItem(row, 0, QTableWidgetItem(self.tr("Cluster {number}").format(number=cluster.label + 1)))
            count = QTableWidgetItem(fmt_int(cluster.count))
            count.setTextAlignment(_RIGHT_ALIGNED)
            table.setItem(row, 1, count)
        if result.noise_count:
            row = len(result.clusters)
            table.setItem(row, 0, QTableWidgetItem(self.tr("Noise")))
            count = QTableWidgetItem(fmt_int(result.noise_count))
            count.setTextAlignment(_RIGHT_ALIGNED)
            table.setItem(row, 1, count)

        table.resizeColumnsToContents()
        hheader = table.horizontalHeader()
        if hheader is not None:
            hheader.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._cluster_table = table
        return table

    def _centered_label(self, text: str) -> QLabel:
        """Build centered error text."""
        label = QLabel(text, self)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        return label

    @staticmethod
    def _build_section_title(text: str, parent: QWidget) -> QLabel:
        """Build a bold title for a clustering section."""
        label = QLabel(text, parent)
        label.setStyleSheet("font-weight: bold;")
        return label
