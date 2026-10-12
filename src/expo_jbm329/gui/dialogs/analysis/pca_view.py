"""Principal component analysis result view."""

from __future__ import annotations

from typing import TYPE_CHECKING

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

from expo_jbm329.gui.dialogs.analysis.section_layout import build_section_scroll_area, rich_text_lines
from expo_jbm329.services.analysis.pca import MIN_OBSERVATIONS, MIN_SELECTED_COLUMNS, PCAError
from expo_jbm329.services.analysis.pca_charts import PCAChartLabels, draw_score_plot, draw_scree_plot
from expo_jbm329.services.analysis.pca_export import component_name
from expo_jbm329.utils.format_utils import fmt_int, fmt_num, fmt_pct

if TYPE_CHECKING:
    from expo_jbm329.services.analysis.pca import PCAResult


_RIGHT_ALIGNED = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter


class PCAView(QWidget):
    """Displays feature loadings, PCA plots and model comments in resizable sections."""

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

        plots_panel, plots_layout = self._build_section(self.tr("PCA plots"))
        plots = QSplitter(Qt.Orientation.Horizontal, plots_panel)
        plots.setChildrenCollapsible(False)
        plots.addWidget(self._build_scree_plot(result))
        plots.addWidget(self._build_scatter_plot(result))
        plots_layout.addWidget(build_section_scroll_area(plots, plots_panel), 1)

        splitter = QSplitter(Qt.Orientation.Vertical, self)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_loadings_panel(result))
        splitter.addWidget(plots_panel)
        splitter.addWidget(self._build_comments_panel(result))
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 4)
        splitter.setStretchFactor(2, 1)
        splitter.setSizes([230, 420, 130])
        layout.addWidget(splitter, 1)

    def configuration(self) -> tuple[tuple[str, ...], bool]:
        """Return the selected columns and scaling used by this displayed fit."""
        return self._result.columns, self._result.standardize

    def result(self) -> PCAResult:
        """Return the displayed PCA fit."""
        return self._result

    def chart_labels(self) -> PCAChartLabels:
        """Return the translated plot text used by the view and its export."""
        result = self._result
        ratios = result.explained_variance_ratio
        # Error results have no fitted ratios; their labels are never drawn or exported.
        pc1_axis = self.tr("PC1 ({variance})").format(variance=fmt_pct(ratios[0])) if ratios else component_name(0)
        pc2_axis = (
            self.tr("PC2 ({variance})").format(variance=fmt_pct(ratios[1])) if len(ratios) > 1 else component_name(1)
        )
        captions = rich_text_lines([self._sample_text(result)]) if result.sampled and result.error is None else ()
        return PCAChartLabels(
            scree_title=self.tr("Scree plot"),
            explained=self.tr("Explained variance"),
            cumulative=self.tr("Cumulative"),
            component_axis=self.tr("Component"),
            variance_axis=self.tr("Explained variance (%)"),
            scatter_title=self.tr("PC1 vs PC2"),
            pc1_axis=pc1_axis,
            pc2_axis=pc2_axis,
            scatter_captions=captions,
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

    def _summary_text(self, result: PCAResult) -> str:
        """Return the rich-text fit summary, complete-case warning and sampling disclosure."""
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
            text += "<br>" + self._sample_text(result)
        return text

    def _sample_text(self, result: PCAResult) -> str:
        """Return the rich-text disclosure that the score plot shows a sample."""
        return self.tr("<i>The PC1-vs-PC2 plot shows a deterministic sample of {count} rows.</i>").format(
            count=fmt_int(len(result.sample_pc1))
        )

    def _build_summary(self, result: PCAResult) -> QLabel:
        """Build the fit summary and complete-case warning."""
        label = QLabel(self._summary_text(result), self)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        return label

    def _build_comments_panel(self, result: PCAResult) -> QWidget:
        """Build the titled model-comments section with a scrollable summary."""
        panel, layout = self._build_section(self.tr("Model comments"))
        layout.addWidget(build_section_scroll_area(self._build_summary(result), panel), 1)
        return panel

    def _build_scree_plot(self, result: PCAResult) -> QWidget:
        """Build a scree plot of component and cumulative explained variance."""
        figure = Figure(constrained_layout=True)
        canvas = FigureCanvasQTAgg(figure)  # type: ignore[no-untyped-call]
        canvas.setMinimumSize(280, 220)
        draw_scree_plot(figure.add_subplot(111), result, self.chart_labels())
        return canvas

    def _build_scatter_plot(self, result: PCAResult) -> QWidget:
        """Build the PC1-vs-PC2 score scatterplot."""
        figure = Figure(constrained_layout=True)
        canvas = FigureCanvasQTAgg(figure)  # type: ignore[no-untyped-call]
        canvas.setMinimumSize(280, 220)
        draw_score_plot(figure.add_subplot(111), result, self.chart_labels())
        return canvas

    def _build_loadings_panel(self, result: PCAResult) -> QWidget:
        """Build the titled feature-loadings table section."""
        panel, layout = self._build_section(self.tr("Feature loadings"))

        headers = [self.tr("Feature"), *(component_name(index) for index in range(len(result.columns)))]
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
        layout.addWidget(table, 1)
        self._loadings_table = table
        return panel

    def _build_centered_label(self, text: str) -> QLabel:
        """Build a centered, word-wrapped message label."""
        label = QLabel(text, self)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        return label

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
