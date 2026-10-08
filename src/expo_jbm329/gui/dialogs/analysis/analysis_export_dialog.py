"""Overview data export selection and previews for other analysis exports."""

from __future__ import annotations

from enum import StrEnum

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


class ExportSelectionMode(StrEnum):
    """Distinguish data-table selection from analysis-result selection."""

    DATA = "data"
    RESULTS = "results"


class AnalysisExportDialog(QDialog):
    """Select structured Overview tables or preview future analysis outputs."""

    def __init__(
        self,
        mode: ExportSelectionMode,
        parent: QWidget | None = None,
        *,
        overview: DatasetOverviewResult | None = None,
        overview_mode: bool = False,
    ) -> None:
        """Build an Overview data selector or a data/results workflow preview.

        Args:
            mode: Kind of export selection to present.
            parent: Optional parent widget.
            overview: Successful displayed Overview snapshot, if available.
            overview_mode: Show disabled Overview choices even without a result.
        """
        super().__init__(parent)
        self.setWindowTitle(
            self.tr("Export analysis data") if mode is ExportSelectionMode.DATA else self.tr("Export results")
        )
        self.resize(540, 440)
        self._overview = overview if mode is ExportSelectionMode.DATA else None
        self._table_choices: dict[OverviewExportTable, QCheckBox] = {}
        if mode is ExportSelectionMode.DATA and (overview_mode or self._overview is not None):
            self._build_overview_selection()
            return
        layout = QVBoxLayout(self)
        preview = QLabel(self.tr("Layout preview only. Export processing is not implemented yet."), self)
        preview.setWordWrap(True)
        layout.addWidget(preview)

        selections = QGroupBox(self.tr("Planned export contents"), self)
        contents = QVBoxLayout(selections)
        choices = (
            (
                (self.tr("Original dataset"), False),
                (self.tr("Analysis dataset"), True),
                (self.tr("Predictions"), False),
                (self.tr("Residuals"), False),
            )
            if mode is ExportSelectionMode.DATA
            else (
                (self.tr("Summary / statistics tables"), True),
                (self.tr("Coefficients"), False),
                (self.tr("Model metrics"), False),
                (self.tr("Charts"), True),
            )
        )
        for text, checked in choices:
            choice = QCheckBox(text, selections)
            choice.setChecked(checked)
            choice.setToolTip(self.tr("Preview choice only. Availability will depend on the computed analysis."))
            contents.addWidget(choice)
        availability = QLabel(
            self.tr(
                "These are planned choices, not available outputs. "
                "Unsupported items will explain why they are unavailable."
            ),
            selections,
        )
        availability.setWordWrap(True)
        contents.addWidget(availability)
        layout.addWidget(selections)

        formats = QFormLayout()
        self._format_combo = QComboBox(self)
        if mode is ExportSelectionMode.DATA:
            self._format_combo.addItems(["CSV", self.tr("Excel workbook (.xlsx)"), "Parquet", "Feather", "Pickle"])
        else:
            self._format_combo.addItem(self.tr("Excel workbook (.xlsx)"))
        formats.addRow(self.tr("Planned format"), self._format_combo)
        if mode is ExportSelectionMode.RESULTS:
            self._chart_format_combo = QComboBox(self)
            self._chart_format_combo.addItems(["PNG", "SVG"])
            formats.addRow(self.tr("Standalone chart format"), self._chart_format_combo)
            explanation = QLabel(
                self.tr(
                    "Excel will contain tables and static chart images. "
                    "Standalone charts can also be saved as PNG or SVG. "
                    "The planned export includes all supported chart variants, not only the displayed chart."
                ),
                self,
            )
        else:
            explanation = QLabel(
                self.tr(
                    "The analysis dataset will contain the rows used by the analysis. "
                    "Predictions and residuals will be offered only where supported."
                ),
                self,
            )
        explanation.setWordWrap(True)
        layout.addLayout(formats)
        layout.addWidget(explanation)
        layout.addStretch()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel, self)
        export_button = QPushButton(self.tr("Export"), buttons)
        buttons.addButton(export_button, QDialogButtonBox.ButtonRole.ActionRole)
        export_button.setEnabled(False)
        export_button.setToolTip(self.tr("Not implemented yet. No file will be created."))
        buttons.rejected.connect(self.reject)
        localize_dialog_buttons(buttons)
        layout.addWidget(buttons)

    def _build_overview_selection(self) -> None:
        """Offer only available structured Overview tables, never the dataset."""
        result = self._overview
        layout = QVBoxLayout(self)
        explanation = QLabel(
            self.tr(
                "Export Columns metadata or Sample (first 100 rows), not the original dataset. "
                "Summary and analysis results are not available for export."
            ),
            self,
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        selections = QGroupBox(self.tr("Export contents"), self)
        contents = QVBoxLayout(selections)
        availability = {
            OverviewExportTable.COLUMNS: result is not None and bool(result.columns),
            OverviewExportTable.SAMPLE: result is not None and bool(result.sample_columns and result.sample_rows),
        }
        labels = {
            OverviewExportTable.COLUMNS: self.tr("Columns metadata"),
            OverviewExportTable.SAMPLE: self.tr("Sample (first 100 rows)"),
        }
        for table, available in availability.items():
            choice = QCheckBox(labels[table], selections)
            choice.setEnabled(available)
            if not available:
                choice.setToolTip(
                    self.tr("Run Overview successfully before exporting.")
                    if result is None
                    else self.tr("This table is empty and cannot be exported.")
                )
            self._table_choices[table] = choice
            choice.toggled.connect(self._update_export_enabled)
            contents.addWidget(choice)
        layout.addWidget(selections)
        formats = QFormLayout()
        self._format_combo = QComboBox(self)
        self._format_combo.addItem("CSV", OverviewExportFormat.CSV)
        self._format_combo.addItem(self.tr("Excel workbook (.xlsx)"), OverviewExportFormat.EXCEL)
        self._format_combo.addItem(
            self.tr("Binary data file (Parquet / Feather / Pickle)"), OverviewExportFormat.BINARY
        )
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
        """Preserve picks across formats and explain single-table restrictions."""
        excel = self._format_combo.currentData() is OverviewExportFormat.EXCEL
        self._selection_explanation.setText(
            self.tr("Excel exports selected tables as separate sheets in one workbook.")
            if excel
            else self.tr(
                "Choose exactly one table for CSV or binary export. "
                "For binary files, choose Parquet, Feather or Pickle in the save dialog."
            )
        )
        self._export_button.setEnabled(self.export_request() is not None)
