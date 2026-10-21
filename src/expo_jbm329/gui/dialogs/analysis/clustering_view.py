"""Result view for numeric clustering."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHeaderView, QLabel, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from expo_jbm329.gui.dialogs.analysis.section_layout import (
    AnalysisResultSection,
    build_section_scroll_area,
    rich_text_lines,
)
from expo_jbm329.gui.widgets.analysis_chart_canvas import SerializedAnalysisCanvas
from expo_jbm329.services.analysis.chart_layout import ChartFigure as Figure
from expo_jbm329.services.analysis.clustering import (
    MIN_OBSERVATIONS,
    MIN_SELECTED_COLUMNS,
    ClusteringError,
    ClusteringMethod,
)
from expo_jbm329.services.analysis.clustering_charts import (
    ClusterProjectionLabels,
    build_cluster_projection_labels,
    draw_cluster_projection,
)
from expo_jbm329.services.analysis.presentation import (
    PresentationLabel,
    clustering_method_label,
    translate_presentation_label,
)
from expo_jbm329.utils.format_utils import fmt_int, fmt_num
from expo_jbm329.utils.i18n_utils import translate

if TYPE_CHECKING:
    from expo_jbm329.services.analysis.clustering import ClusteringResult

_RIGHT_ALIGNED = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter


class ClusteringView(QWidget):
    """Displays cluster sizes, an internal PCA plot and model comments in resizable sections."""

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
        splitter.addWidget(self._build_table_section(result))
        splitter.addWidget(self._build_plot_section(result))
        splitter.addWidget(self._build_comments_section(result))
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 4)
        splitter.setStretchFactor(2, 1)
        splitter.setSizes([220, 430, 130])
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

    def result(self) -> ClusteringResult:
        """Return the displayed clustering fit."""
        return self._result

    def chart_labels(self) -> ClusterProjectionLabels:
        """Return the translated projection text used by the view and its export."""
        return build_cluster_projection_labels(
            self._result,
            translate,
            count_format=fmt_int,
        )

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
        return clustering_method_label(method, translate)

    def _summary_text(self, result: ClusteringResult) -> str:
        """Return the rich-text summary of method, preprocessing, rows, silhouette and sampling."""
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
            text += "<br>" + self._sample_text(result)
        return text

    def _sample_text(self, result: ClusteringResult) -> str:
        """Return the rich-text disclosure that the plot shows a sample."""
        captions = self.chart_labels().metadata.captions
        return f"<i>{captions[0]}</i>" if captions and result.sampled else ""

    def _summary_label(self, result: ClusteringResult) -> QLabel:
        """Build summary of method, preprocessing, rows and silhouette."""
        label = QLabel(self._summary_text(result), self)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        return label

    def _build_comments_section(self, result: ClusteringResult) -> QWidget:
        """Build the titled model-comments section with a scrollable summary."""
        return AnalysisResultSection(
            translate_presentation_label(PresentationLabel.CLUSTER_MODEL_SUMMARY, translate),
            self._summary_label(result),
            self,
        )

    def _build_plot_section(self, result: ClusteringResult) -> QWidget:
        """Build the titled, scrollable cluster projection section."""
        panel, layout = self._build_section(
            translate_presentation_label(PresentationLabel.CLUSTER_PROJECTION, translate)
        )
        layout.addWidget(build_section_scroll_area(self._build_plot(result), panel), 1)
        return panel

    def _build_table_section(self, result: ClusteringResult) -> QWidget:
        """Build the titled cluster-size table section."""
        panel, layout = self._build_section(translate_presentation_label(PresentationLabel.CLUSTER_SIZES, translate))
        layout.addWidget(self._build_cluster_table(result), 1)
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

    def _build_plot(self, result: ClusteringResult) -> QWidget:
        """Build the internal PCA projection colored by cluster label."""
        figure = Figure(constrained_layout=True)
        canvas = SerializedAnalysisCanvas(figure)
        canvas.setMinimumSize(420, 260)
        canvas.build_chart(lambda: draw_cluster_projection(figure.add_subplot(111), result, self.chart_labels()))
        return canvas

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
