"""Grouped Overview export selection and unavailable previews for other analyses."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from expo_jbm329.gui.dialogs.service.common.localization import localize_dialog_buttons
from expo_jbm329.services.analysis.categories import HypothesisTest
from expo_jbm329.services.analysis.hypothesis_export import (
    HypothesisExportComponent,
    HypothesisExportRequest,
    HypothesisExportSnapshot,
)
from expo_jbm329.services.analysis.overview import (
    DatasetOverviewResult,
    OverviewExportFormat,
    OverviewExportRequest,
    OverviewExportTable,
)
from expo_jbm329.services.analysis.statistics import (
    DescriptiveStatisticsResult,
    StatisticsExportFormat,
    StatisticsExportRequest,
    StatisticsExportTable,
)


class AnalysisExportDialog(QDialog):
    """Select available Overview tables in a single Data and Results dialog."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        overview: DatasetOverviewResult | None = None,
        overview_mode: bool = False,
        statistics: DescriptiveStatisticsResult | None = None,
        statistics_mode: bool = False,
        hypothesis: HypothesisExportSnapshot | None = None,
        hypothesis_mode: bool = False,
    ) -> None:
        """Build grouped export choices and a format selector.

        Args:
            parent: Optional parent widget.
            overview: Successful displayed Overview snapshot, if available.
            overview_mode: Show disabled Overview choices even without a result.
            statistics: Successful displayed Statistics snapshot, if available.
            statistics_mode: Show Statistics export choices.
            hypothesis: Successfully displayed applied hypothesis selection.
            hypothesis_mode: Show hypothesis choices even before Apply.
        """
        super().__init__(parent)
        self.setWindowTitle(self.tr("Export"))
        self.resize(540, 540)
        self._overview = overview
        self._statistics = statistics
        self._hypothesis = hypothesis
        self._hypothesis_mode = hypothesis_mode or hypothesis is not None
        self._hypothesis_choices: dict[HypothesisExportComponent, QCheckBox] = {}
        self._table_choices: dict[OverviewExportTable, QCheckBox] = {}
        self._statistics_choices: dict[StatisticsExportTable, QCheckBox] = {}
        self._overview_mode = overview_mode or overview is not None
        self._statistics_mode = statistics_mode or statistics is not None
        if sum((self._overview_mode, self._statistics_mode, self._hypothesis_mode)) > 1:
            message = "An export dialog can represent only one analysis result."
            raise ValueError(message)
        layout = QVBoxLayout(self)
        explanation = QLabel(
            self.tr(
                "Export the Overview Summary, Columns metadata, or Sample (first 100 rows), not the original dataset."
            )
            if self._overview_mode
            else (
                self.tr("Export the available Statistics tables and numeric-column charts.")
                if self._statistics_mode
                else (
                    self.tr("Export computed tables and charts for the applied test, not the original dataset.")
                    if self._hypothesis_mode
                    else self.tr("Layout preview only. Export processing is not implemented yet.")
                )
            ),
            self,
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        if self._overview_mode:
            self._build_overview_choices(layout)
        elif self._statistics_mode:
            self._build_statistics_choices(layout)
        elif self._hypothesis_mode:
            self._build_hypothesis_choices(layout)
        else:
            self._build_preview_choices(layout)
        formats = QFormLayout()
        self._format_combo = QComboBox(self)
        format_type = StatisticsExportFormat if self._statistics_mode or self._hypothesis_mode else OverviewExportFormat
        self._format_combo.addItem("CSV", format_type.CSV)
        self._format_combo.addItem(self.tr("Excel workbook (.xlsx)"), format_type.EXCEL)
        self._format_combo.addItem(self.tr("Binary data file (Parquet / Feather / Pickle)"), format_type.BINARY)
        self._format_combo.setCurrentIndex(self._format_combo.findData(format_type.EXCEL))
        self._format_combo.currentIndexChanged.connect(self._update_export_enabled)
        formats.addRow(self.tr("Format"), self._format_combo)
        layout.addLayout(formats)
        self._selection_explanation = QLabel(self)
        self._selection_explanation.setWordWrap(True)
        layout.addWidget(self._selection_explanation)
        layout.addStretch()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel, self)
        self._export_button = QPushButton(self.tr("Export"), buttons)
        buttons.addButton(self._export_button, QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        localize_dialog_buttons(buttons)
        layout.addWidget(buttons)
        choices = (
            self._hypothesis_choices
            if self._hypothesis_mode
            else self._statistics_choices
            if self._statistics_mode
            else self._table_choices
        )
        first_available = next((choice for choice in choices.values() if choice.isEnabled()), None)
        if first_available is not None:
            first_available.setChecked(True)
        self._update_export_enabled()

    def _build_overview_choices(self, layout: QVBoxLayout) -> None:
        """Offer only available structured Overview tables, never the dataset."""
        result = self._overview
        data = QGroupBox(self.tr("Data"), self)
        data_layout = QVBoxLayout(data)
        results = QGroupBox(self.tr("Results"), self)
        results_layout = QVBoxLayout(results)
        availability = {
            OverviewExportTable.COLUMNS: result is not None and bool(result.columns),
            OverviewExportTable.SAMPLE: result is not None and bool(result.sample_columns and result.sample_rows),
            OverviewExportTable.SUMMARY: result is not None,
        }
        labels = {
            OverviewExportTable.COLUMNS: self.tr("Columns metadata"),
            OverviewExportTable.SAMPLE: self.tr("Sample (first 100 rows)"),
            OverviewExportTable.SUMMARY: self.tr("Summary"),
        }
        for table, available in availability.items():
            is_summary = table is OverviewExportTable.SUMMARY
            parent = results if is_summary else data
            choice = QCheckBox(labels[table], parent)
            choice.setEnabled(available)
            if is_summary:
                choice.setToolTip(
                    self.tr(
                        "Dataset metrics, column-type counts, and high-missing-value warnings. "
                        "Fractions are numeric values from 0 to 1."
                    )
                )
            if not available:
                choice.setToolTip(
                    self.tr("Run Overview successfully before exporting.")
                    if result is None
                    else self.tr("This table is empty and cannot be exported.")
                )
            self._table_choices[table] = choice
            choice.toggled.connect(self._update_export_enabled)
            (results_layout if is_summary else data_layout).addWidget(choice)
        layout.addWidget(data)
        layout.addWidget(results)

    def _build_preview_choices(self, layout: QVBoxLayout) -> None:
        """Show unavailable planned components without implying real exports."""
        for title, labels in (
            (
                self.tr("Data"),
                (
                    self.tr("Original dataset"),
                    self.tr("Analysis dataset"),
                    self.tr("Predictions"),
                    self.tr("Residuals"),
                ),
            ),
            (
                self.tr("Results"),
                (
                    self.tr("Summary / statistics tables"),
                    self.tr("Coefficients"),
                    self.tr("Model metrics"),
                    self.tr("Charts"),
                ),
            ),
        ):
            group = QGroupBox(title, self)
            contents = QVBoxLayout(group)
            for text in labels:
                choice = QCheckBox(text, group)
                choice.setEnabled(False)
                choice.setToolTip(self.tr("Not implemented yet. No file will be created."))
                contents.addWidget(choice)
            layout.addWidget(group)

    def _build_statistics_choices(self, layout: QVBoxLayout) -> None:
        """Offer available Statistics tables and a separate Excel chart component."""
        result = self._statistics
        data = QGroupBox(self.tr("Data"), self)
        data_layout = QVBoxLayout(data)
        results = QGroupBox(self.tr("Results"), self)
        results_layout = QVBoxLayout(results)
        availability = {
            StatisticsExportTable.CONTINUOUS: result is not None and bool(result.columns),
            StatisticsExportTable.CATEGORICAL: result is not None and bool(result.categorical_columns),
            StatisticsExportTable.CHARTS: result is not None and bool(result.columns),
        }
        labels = {
            StatisticsExportTable.CONTINUOUS: self.tr("Continuous"),
            StatisticsExportTable.CATEGORICAL: self.tr("Categorical"),
            StatisticsExportTable.CHARTS: self.tr("Charts"),
        }
        for component, available in availability.items():
            is_chart = component is StatisticsExportTable.CHARTS
            parent = results if is_chart else data
            choice = QCheckBox(labels[component], parent)
            choice.setEnabled(available)
            if component is StatisticsExportTable.CATEGORICAL and available:
                choice.setToolTip(self.tr("Counts are numeric, and fractions range from 0 to 1."))
            elif not available:
                choice.setToolTip(
                    self.tr("Run Statistics successfully before exporting.")
                    if result is None
                    else self.tr("This component is empty and cannot be exported.")
                )
            self._statistics_choices[component] = choice
            choice.toggled.connect(self._update_export_enabled)
            (results_layout if is_chart else data_layout).addWidget(choice)
        layout.addWidget(data)
        layout.addWidget(results)

    def _build_hypothesis_choices(self, layout: QVBoxLayout) -> None:
        """List applied identity plainly, independently of pending configuration edits."""
        snapshot = self._hypothesis
        if snapshot is not None:
            names = {
                HypothesisTest.GROUP_COMPARISON: self.tr("Group comparison"),
                HypothesisTest.CHI_SQUARE: self.tr("Chi-square independence"),
                HypothesisTest.PAIRED_COMPARISON: self.tr("Paired comparison"),
            }
            roles = {
                HypothesisTest.GROUP_COMPARISON: self.tr("Numeric column / grouping column"),
                HypothesisTest.CHI_SQUARE: self.tr("Row column / column column"),
                HypothesisTest.PAIRED_COMPARISON: self.tr("Measurement columns (occasion order)"),
            }
            identity = QLabel(
                self.tr("Applied test: {test}\n{roles}: {columns}").format(
                    test=names[snapshot.test], roles=roles[snapshot.test], columns=" / ".join(snapshot.columns)
                ),
                self,
            )
            identity.setTextFormat(Qt.TextFormat.PlainText)
            identity.setWordWrap(True)
            identity.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(identity)
        summaries = {
            HypothesisTest.GROUP_COMPARISON: self.tr("Group summary"),
            HypothesisTest.CHI_SQUARE: self.tr("Contingency table"),
            HypothesisTest.PAIRED_COMPARISON: self.tr("Measurement summary"),
        }
        for title, components in (
            (self.tr("Data"), (HypothesisExportComponent.SUMMARY,)),
            (self.tr("Results"), (HypothesisExportComponent.TEST_RESULTS, HypothesisExportComponent.CHARTS)),
        ):
            group = QGroupBox(title, self)
            contents = QVBoxLayout(group)
            for component in components:
                label = (
                    summaries[snapshot.test]
                    if component is HypothesisExportComponent.SUMMARY and snapshot is not None
                    else self.tr("Summary / statistics tables")
                    if component is HypothesisExportComponent.SUMMARY
                    else self.tr(component.value)
                )
                choice = QCheckBox(label, group)
                choice.setEnabled(snapshot is not None)
                if snapshot is None:
                    choice.setToolTip(self.tr("Apply a hypothesis test successfully before exporting."))
                self._hypothesis_choices[component] = choice
                choice.toggled.connect(self._update_export_enabled)
                contents.addWidget(choice)
            layout.addWidget(group)

    def export_request(self) -> OverviewExportRequest | StatisticsExportRequest | HypothesisExportRequest | None:
        """Return a validated selection, or None for previews/invalid choices."""
        if self._hypothesis_mode:
            if self._hypothesis is None:
                return None
            hypothesis_components = tuple(
                component
                for component, choice in self._hypothesis_choices.items()
                if choice.isEnabled() and choice.isChecked()
            )
            format_choice = self._format_combo.currentData()
            if not isinstance(format_choice, StatisticsExportFormat):
                return None
            try:
                return HypothesisExportRequest(self._hypothesis, hypothesis_components, format_choice)
            except ValueError:
                return None
        if self._statistics_mode:
            if self._statistics is None:
                return None
            components = tuple(
                component
                for component, choice in self._statistics_choices.items()
                if choice.isEnabled() and choice.isChecked()
            )
            format_choice = self._format_combo.currentData()
            if not isinstance(format_choice, StatisticsExportFormat) or not components:
                return None
            chart_selected = StatisticsExportTable.CHARTS in components
            table_count = sum(component is not StatisticsExportTable.CHARTS for component in components)
            if format_choice is not StatisticsExportFormat.EXCEL and (chart_selected or table_count != 1):
                return None
            return StatisticsExportRequest(self._statistics, components, format_choice)
        if self._overview is None:
            return None
        tables = tuple(
            table for table, choice in self._table_choices.items() if choice.isEnabled() and choice.isChecked()
        )
        format_choice = self._format_combo.currentData()
        if not isinstance(format_choice, OverviewExportFormat) or not tables:
            return None
        if format_choice is not OverviewExportFormat.EXCEL and len(tables) != 1:
            return None
        return OverviewExportRequest(self._overview, tables, format_choice)

    def _update_export_enabled(self) -> None:
        """Preserve picks across formats and explain disabled exports."""
        if self._statistics_mode or self._hypothesis_mode:
            self._update_statistics_export_enabled()
            return
        excel = self._format_combo.currentData() is OverviewExportFormat.EXCEL
        format_explanation = (
            self.tr("Excel exports selected tables as separate sheets in one workbook.")
            if excel
            else self.tr(
                "Choose exactly one table for CSV or binary export. "
                "For binary files, choose Parquet, Feather or Pickle in the save dialog."
            )
        )
        request = self.export_request()
        if not self._overview_mode:
            reason = self.tr("Not implemented yet. No file will be created.")
        elif self._overview is None:
            reason = self.tr("Run Overview successfully before exporting.")
        elif not any(choice.isEnabled() for choice in self._table_choices.values()):
            reason = self.tr("This table is empty and cannot be exported.")
        elif not any(choice.isEnabled() and choice.isChecked() for choice in self._table_choices.values()):
            reason = self.tr("Select at least one available table to export.")
        elif request is None:
            reason = self.tr("Choose exactly one table for CSV or binary export.")
        else:
            reason = ""
        self._selection_explanation.setText(f"{reason}\n{format_explanation}" if reason else format_explanation)
        self._export_button.setEnabled(request is not None)
        self._export_button.setToolTip(reason)

    def _update_statistics_export_enabled(self) -> None:
        """Preserve Statistics picks and explain format-specific constraints."""
        excel = self._format_combo.currentData() is StatisticsExportFormat.EXCEL
        format_explanation = (
            self.tr("Excel exports selected tables as separate sheets and charts on one Charts sheet.")
            if excel
            else self.tr(
                "Choose exactly one table for CSV or binary export. "
                "Charts are available only in Excel; uncheck Charts to continue."
            )
        )
        request = self.export_request()
        choices = self._hypothesis_choices if self._hypothesis_mode else self._statistics_choices
        selected = any(choice.isEnabled() and choice.isChecked() for choice in choices.values())
        available = any(choice.isEnabled() for choice in choices.values())
        chart_choice = (
            self._hypothesis_choices.get(HypothesisExportComponent.CHARTS)
            if self._hypothesis_mode
            else self._statistics_choices.get(StatisticsExportTable.CHARTS)
        )
        chart_selected = chart_choice is not None and chart_choice.isChecked()
        if self._hypothesis_mode and self._hypothesis is None:
            reason = self.tr("Apply a hypothesis test successfully before exporting.")
        elif not self._hypothesis_mode and self._statistics is None:
            reason = self.tr("Run Statistics successfully before exporting.")
        elif not available:
            reason = self.tr("This component is empty and cannot be exported.")
        elif not selected:
            reason = self.tr("Select at least one available component to export.")
        elif not excel and chart_selected:
            reason = self.tr("Charts are available only in Excel. Uncheck Charts to continue.")
        elif request is None:
            reason = self.tr("Choose exactly one table for CSV or binary export.")
        else:
            reason = ""
        self._selection_explanation.setText(f"{reason}\n{format_explanation}" if reason else format_explanation)
        self._export_button.setEnabled(request is not None)
        self._export_button.setToolTip(reason)
