"""Grouped Overview export selection and unavailable previews for other analyses."""

from __future__ import annotations

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
from expo_jbm329.services.analysis.overview import (
    DatasetOverviewResult,
    OverviewExportFormat,
    OverviewExportRequest,
    OverviewExportTable,
)


class AnalysisExportDialog(QDialog):
    """Select available Overview tables in a single Data and Results dialog."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        overview: DatasetOverviewResult | None = None,
        overview_mode: bool = False,
    ) -> None:
        """Build grouped export choices and a format selector.

        Args:
            parent: Optional parent widget.
            overview: Successful displayed Overview snapshot, if available.
            overview_mode: Show disabled Overview choices even without a result.
        """
        super().__init__(parent)
        self.setWindowTitle(self.tr("Export"))
        self.resize(540, 540)
        self._overview = overview
        self._table_choices: dict[OverviewExportTable, QCheckBox] = {}
        self._overview_mode = overview_mode or overview is not None
        layout = QVBoxLayout(self)
        explanation = QLabel(
            self.tr(
                "Export the Overview Summary, Columns metadata, or Sample (first 100 rows), not the original dataset."
            )
            if self._overview_mode
            else self.tr("Layout preview only. Export processing is not implemented yet."),
            self,
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        if self._overview_mode:
            self._build_overview_choices(layout)
        else:
            self._build_preview_choices(layout)
        formats = QFormLayout()
        self._format_combo = QComboBox(self)
        self._format_combo.addItem("CSV", OverviewExportFormat.CSV)
        self._format_combo.addItem(self.tr("Excel workbook (.xlsx)"), OverviewExportFormat.EXCEL)
        self._format_combo.addItem(
            self.tr("Binary data file (Parquet / Feather / Pickle)"), OverviewExportFormat.BINARY
        )
        self._format_combo.setCurrentIndex(self._format_combo.findData(OverviewExportFormat.EXCEL))
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
        first_available = next((choice for choice in self._table_choices.values() if choice.isEnabled()), None)
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

    def export_request(self) -> OverviewExportRequest | None:
        """Return a validated selection, or None for previews/invalid choices."""
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
