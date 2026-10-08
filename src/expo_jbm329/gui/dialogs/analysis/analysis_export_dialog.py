"""Selection-layout previews for analysis data and result exports."""

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


class ExportSelectionMode(StrEnum):
    """Distinguish row-level data selection from result selection."""

    DATA = "data"
    RESULTS = "results"


class AnalysisExportDialog(QDialog):
    """Preview export choices without accessing datasets or creating files."""

    def __init__(self, mode: ExportSelectionMode, parent: QWidget | None = None) -> None:
        """Build a data or results selection preview.

        Args:
            mode: Kind of export selection to present.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.setWindowTitle(
            self.tr("Export analysis data") if mode is ExportSelectionMode.DATA else self.tr("Export results")
        )
        self.resize(540, 440)
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
