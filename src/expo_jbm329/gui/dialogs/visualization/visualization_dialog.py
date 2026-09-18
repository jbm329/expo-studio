"""Visualization dialog with a three-pane workspace layout."""
from __future__ import annotations

from collections.abc import Iterable

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from expo_jbm329.gui.dialogs.visualization.chart_preview_widget import ChartPreviewWidget
from expo_jbm329.utils.visualization_models import (
    AggregationType,
    ChartType,
    MeasureConfig,
    MeasureType,
    VisualizationConfig,
    VisualizationDatasetRef,
)


class VisualizationDialog(QDialog):
    """Dialog for configuring and previewing dataset visualizations."""

    dataset_changed = pyqtSignal(str)
    preview_requested = pyqtSignal(object)  # VisualizationConfig

    def __init__(
        self,
        *,
        parent: QWidget | None,
        datasets: list[VisualizationDatasetRef],
        active_tab_id: str | None,
    ) -> None:
        """Initialize the visualization dialog.

        Args:
            parent: Parent widget.
            datasets: Available datasets.
            active_tab_id: Initially selected dataset tab ID.
        """
        super().__init__(parent)

        self._datasets = datasets
        self._all_columns: list[str] = []
        self._numeric_columns: list[str] = []

        self.setWindowTitle(self.tr("Visualize data"))
        self.resize(1450, 760)

        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        left_panel = self._build_left_panel(active_tab_id)
        center_panel = self._build_center_panel()
        right_panel = self._build_right_panel()

        root.addWidget(left_panel, 1)
        root.addWidget(center_panel, 3)
        root.addWidget(right_panel, 1)

        self._connect_signals()
        self._sync_controls_for_chart_type()
        self._sync_measure_controls()

        if self._dataset_combo.currentData():
            self.dataset_changed.emit(str(self._dataset_combo.currentData()))

    # ------------------------------------------------------------------
    # UI building
    # ------------------------------------------------------------------

    def _build_left_panel(self, active_tab_id: str | None) -> QWidget:
        """Build the left selection panel."""
        panel = QGroupBox(self.tr("Datasource and chart type"), self)
        layout = QVBoxLayout(panel)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)

        self._dataset_combo = QComboBox(panel)
        for ds in self._datasets:
            label = f"{ds.title} ({ds.row_count} x {ds.column_count})"
            self._dataset_combo.addItem(label, ds.tab_id)

        if active_tab_id:
            for i in range(self._dataset_combo.count()):
                if self._dataset_combo.itemData(i) == active_tab_id:
                    self._dataset_combo.setCurrentIndex(i)
                    break

        self._chart_type_combo = QComboBox(panel)
        self._chart_type_combo.addItem(self.tr("Line chart"), ChartType.LINE)
        self._chart_type_combo.addItem(self.tr("Bar chart"), ChartType.BAR)
        self._chart_type_combo.addItem(self.tr("Pie chart"), ChartType.PIE)
        self._chart_type_combo.addItem(self.tr("Scatter plot"), ChartType.SCATTER)
        self._chart_type_combo.addItem(self.tr("Histogram"), ChartType.HISTOGRAM)

        form.addRow(QLabel(self.tr("Dataset"), panel), self._dataset_combo)
        form.addRow(QLabel(self.tr("Chart type"), panel), self._chart_type_combo)

        layout.addLayout(form)
        layout.addStretch(1)

        return panel

    def _build_center_panel(self) -> QWidget:
        """Build the center chart preview panel."""
        panel = QGroupBox(self.tr("Visualization"), self)
        layout = QVBoxLayout(panel)

        self._preview = ChartPreviewWidget(panel)
        self._preview.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

        layout.addWidget(self._preview)
        return panel

    def _build_right_panel(self) -> QWidget:
        """Build the right configuration panel."""
        panel = QGroupBox(self.tr("Dimensions and measures"), self)
        layout = QVBoxLayout(panel)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)

        self._dimension_label = QLabel(self.tr("Dimension"), panel)
        self._dimension_combo = QComboBox(panel)

        self._measure_type_label = QLabel(self.tr("Measure type"), panel)
        self._measure_type_combo = QComboBox(panel)
        self._measure_type_combo.addItem(self.tr("Column"), MeasureType.COLUMN)
        self._measure_type_combo.addItem(self.tr("Number of rows"), MeasureType.ROW_COUNT)

        self._measure_column_label = QLabel(self.tr("Measure"), panel)
        self._measure_column_combo = QComboBox(panel)

        self._aggregation_label = QLabel(self.tr("Aggregation"), panel)
        self._aggregation_combo = QComboBox(panel)

        self._measure_name_label = QLabel(self.tr("Label"), panel)
        self._measure_name_edit = QLineEdit(panel)
        self._measure_name_edit.setPlaceholderText(self.tr("Name of choice"))

        self._x_label = QLabel(self.tr("X-axis"), panel)
        self._x_combo = QComboBox(panel)

        self._y_label = QLabel(self.tr("Y-axis"), panel)
        self._y_combo = QComboBox(panel)

        form.addRow(self._dimension_label, self._dimension_combo)
        form.addRow(self._measure_type_label, self._measure_type_combo)
        form.addRow(self._measure_column_label, self._measure_column_combo)
        form.addRow(self._aggregation_label, self._aggregation_combo)
        form.addRow(self._measure_name_label, self._measure_name_edit)
        form.addRow(self._x_label, self._x_combo)
        form.addRow(self._y_label, self._y_combo)

        self._update_button = QPushButton(self.tr("Show chart"), panel)

        layout.addLayout(form)
        layout.addWidget(self._update_button)
        layout.addStretch(1)

        return panel

    # ------------------------------------------------------------------
    # Connections and behavior
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        """Connect internal dialog signals."""
        self._dataset_combo.currentIndexChanged.connect(self._emit_dataset_changed)
        self._chart_type_combo.currentIndexChanged.connect(self._sync_controls_for_chart_type)
        self._measure_type_combo.currentIndexChanged.connect(self._sync_measure_controls)
        self._measure_column_combo.currentIndexChanged.connect(self._sync_aggregation_choices)
        self._update_button.clicked.connect(self._emit_preview_requested)

    def _emit_dataset_changed(self) -> None:
        """Emit the selected dataset ID."""
        value = self._dataset_combo.currentData()
        if isinstance(value, str) and value:
            self.dataset_changed.emit(value)

    def _emit_preview_requested(self) -> None:
        """Emit a preview request with the current config."""
        self.preview_requested.emit(self.current_config())

    def _sync_controls_for_chart_type(self) -> None:
        """Adjust visible controls based on selected chart type."""
        chart_type = self.selected_chart_type()

        is_category_chart = chart_type in {ChartType.LINE, ChartType.BAR, ChartType.PIE}
        is_scatter = chart_type == ChartType.SCATTER
        is_histogram = chart_type == ChartType.HISTOGRAM

        self._dimension_label.setVisible(is_category_chart)
        self._dimension_combo.setVisible(is_category_chart)

        self._measure_type_label.setVisible(is_category_chart or is_histogram)
        self._measure_type_combo.setVisible(is_category_chart or is_histogram)

        self._measure_column_label.setVisible(is_category_chart or is_histogram)
        self._measure_column_combo.setVisible(is_category_chart or is_histogram)

        self._aggregation_label.setVisible(is_category_chart or is_histogram)
        self._aggregation_combo.setVisible(is_category_chart or is_histogram)

        self._measure_name_label.setVisible(is_category_chart or is_histogram)
        self._measure_name_edit.setVisible(is_category_chart or is_histogram)

        self._x_label.setVisible(is_scatter)
        self._x_combo.setVisible(is_scatter)

        self._y_label.setVisible(is_scatter)
        self._y_combo.setVisible(is_scatter)

        self._sync_measure_controls()

    def _sync_measure_controls(self) -> None:
        """Enable or disable measure-related controls based on current selections."""
        chart_type = self.selected_chart_type()
        measure_type = self.selected_measure_type()

        is_category_chart = chart_type in {ChartType.LINE, ChartType.BAR, ChartType.PIE}
        is_histogram = chart_type == ChartType.HISTOGRAM
        is_measure_chart = is_category_chart or is_histogram

        if not is_measure_chart:
            self._measure_column_combo.setEnabled(False)
            self._aggregation_combo.setEnabled(False)
            self._measure_name_edit.setEnabled(False)
            return

        self._measure_name_edit.setEnabled(True)

        if measure_type == MeasureType.ROW_COUNT:
            self._measure_column_combo.setEnabled(False)

            # Histogram should not support row count.
            if is_histogram:
                self._measure_type_combo.setCurrentIndex(
                    self._measure_type_combo.findData(MeasureType.COLUMN)
                )
                return

            self._set_aggregation_items([AggregationType.COUNT])
            self._aggregation_combo.setEnabled(False)
        else:
            self._measure_column_combo.setEnabled(True)
            self._aggregation_combo.setEnabled(True)
            self._sync_aggregation_choices()

    def _sync_aggregation_choices(self) -> None:
        """Refresh valid aggregations based on the selected measure column."""
        chart_type = self.selected_chart_type()
        measure_type = self.selected_measure_type()

        if chart_type not in {ChartType.LINE, ChartType.BAR, ChartType.PIE, ChartType.HISTOGRAM}:
            return

        if measure_type == MeasureType.ROW_COUNT:
            self._set_aggregation_items([AggregationType.COUNT])
            return

        column = self._current_combo_text(self._measure_column_combo)
        if not column:
            self._set_aggregation_items(
                [
                    AggregationType.SUM,
                    AggregationType.COUNT,
                    AggregationType.COUNT_DISTINCT,
                    AggregationType.AVG,
                    AggregationType.MIN,
                    AggregationType.MAX,
                ]
            )
            return

        is_numeric = column in self._numeric_columns
        if is_numeric:
            self._set_aggregation_items(
                [
                    AggregationType.SUM,
                    AggregationType.COUNT,
                    AggregationType.COUNT_DISTINCT,
                    AggregationType.AVG,
                    AggregationType.MIN,
                    AggregationType.MAX,
                ]
            )
        else:
            self._set_aggregation_items(
                [
                    AggregationType.COUNT,
                    AggregationType.COUNT_DISTINCT,
                ]
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def selected_chart_type(self) -> ChartType:
        """Return the selected chart type."""
        value = self._chart_type_combo.currentData()
        return value if isinstance(value, ChartType) else ChartType.BAR

    def selected_measure_type(self) -> MeasureType:
        """Return the selected measure type."""
        value = self._measure_type_combo.currentData()
        return value if isinstance(value, MeasureType) else MeasureType.COLUMN

    def selected_dataset_tab_id(self) -> str | None:
        """Return the selected dataset tab ID."""
        value = self._dataset_combo.currentData()
        return value if isinstance(value, str) else None

    def current_config(self) -> VisualizationConfig:
        """Build and return the current visualization config."""
        dataset_tab_id = self.selected_dataset_tab_id() or ""
        chart_type = self.selected_chart_type()

        measure = None
        if chart_type in {ChartType.LINE, ChartType.BAR, ChartType.PIE, ChartType.HISTOGRAM}:
            aggregation_raw = self._aggregation_combo.currentData()
            aggregation = (
                aggregation_raw if isinstance(aggregation_raw, AggregationType) else None
            )

            measure = MeasureConfig(
                measure_type=self.selected_measure_type(),
                column=self._current_combo_text(self._measure_column_combo),
                aggregation=aggregation,
                name=self._measure_name_edit.text().strip() or None,
            )

        return VisualizationConfig(
            dataset_tab_id=dataset_tab_id,
            chart_type=chart_type,
            category_column=self._current_combo_text(self._dimension_combo),
            measure=measure,
            x_column=self._current_combo_text(self._x_combo),
            y_column=self._current_combo_text(self._y_combo),
        )

    def set_available_columns(
        self,
        *,
        all_columns: list[str],
        numeric_columns: list[str],
    ) -> None:
        """Update selector choices for the current dataset.

        Args:
            all_columns: All dataset columns.
            numeric_columns: Numeric-only columns.
        """
        self._all_columns = list(all_columns)
        self._numeric_columns = list(numeric_columns)

        self._set_combo_items(self._dimension_combo, self._all_columns)
        self._set_combo_items(self._measure_column_combo, self._all_columns)
        self._set_combo_items(self._x_combo, self._numeric_columns)
        self._set_combo_items(self._y_combo, self._numeric_columns)

        self._sync_measure_controls()

    def apply_smart_defaults(
        self,
        *,
        preferred_dimension: str | None,
        preferred_numeric_measure: str | None,
    ) -> None:
        """Apply smart default field selections.

        Args:
            preferred_dimension: Suggested category/dimension column.
            preferred_numeric_measure: Suggested numeric measure column.
        """
        if preferred_dimension:
            idx = self._dimension_combo.findText(preferred_dimension)
            if idx >= 0:
                self._dimension_combo.setCurrentIndex(idx)

        if preferred_numeric_measure:
            idx = self._measure_column_combo.findText(preferred_numeric_measure)
            if idx >= 0:
                self._measure_column_combo.setCurrentIndex(idx)

        if not preferred_numeric_measure:
            row_count_index = self._measure_type_combo.findData(MeasureType.ROW_COUNT)
            if row_count_index >= 0:
                self._measure_type_combo.setCurrentIndex(row_count_index)

        self._sync_measure_controls()

    def show_empty_preview(self) -> None:
        """Show the default empty preview state."""
        self._preview.show_message(self.tr("No visualization yet."))

    def show_error_preview(self, message: str) -> None:
        """Display an error message in the preview area.

        Args:
            message: Error text.
        """
        self._preview.show_message(message)

    def preview_widget(self) -> ChartPreviewWidget:
        """Return the chart preview widget."""
        return self._preview

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _set_combo_items(self, combo: QComboBox, items: Iterable[str]) -> None:
        """Replace all items in a combo box."""
        current = combo.currentText().strip()
        combo.blockSignals(True)
        try:
            combo.clear()
            combo.addItem("", None)
            for item in items:
                combo.addItem(item, item)

            if current:
                idx = combo.findText(current)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
        finally:
            combo.blockSignals(False)

    def _set_aggregation_items(self, aggregations: list[AggregationType]) -> None:
        """Replace aggregation options while preserving selection when possible."""
        current = self._aggregation_combo.currentData()
        self._aggregation_combo.blockSignals(True)
        try:
            self._aggregation_combo.clear()
            for agg in aggregations:
                self._aggregation_combo.addItem(self._aggregation_label_for(agg), agg)

            if current in aggregations:
                idx = self._aggregation_combo.findData(current)
                if idx >= 0:
                    self._aggregation_combo.setCurrentIndex(idx)
        finally:
            self._aggregation_combo.blockSignals(False)

    def _aggregation_label_for(self, aggregation: AggregationType) -> str:
        """Return the localized label for an aggregation."""
        labels = {
            AggregationType.SUM: self.tr("Sum"),
            AggregationType.COUNT: self.tr("Count"),
            AggregationType.COUNT_DISTINCT: self.tr("Count distinct"),
            AggregationType.AVG: self.tr("Average"),
            AggregationType.MIN: self.tr("Min"),
            AggregationType.MAX: self.tr("Max"),
        }
        return labels.get(aggregation, aggregation.value)

    def _current_combo_text(self, combo: QComboBox) -> str | None:
        """Return the current non-empty combo text."""
        text = combo.currentText().strip()
        return text or None
