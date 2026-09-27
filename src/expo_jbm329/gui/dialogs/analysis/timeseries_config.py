"""Configuration widget for the Time Series Explorer."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QLabel, QPushButton, QSpinBox, QVBoxLayout, QWidget

from expo_jbm329.gui.dialogs.analysis.column_combo_box import ColumnComboBox
from expo_jbm329.services.analysis.timeseries import DecompositionModel

if TYPE_CHECKING:
    from expo_jbm329.services.analysis.timeseries import TimeSeriesResult


class TimeSeriesConfigWidget(QWidget):
    """Lets users choose one datetime/value series and its diagnostics settings."""

    analysis_requested = pyqtSignal()

    def __init__(self, result: TimeSeriesResult, parent: QWidget | None = None) -> None:
        """Initialize the applied and pending controls from `result`."""
        super().__init__(parent)
        self._applied_configuration = self._configuration_from_result(result)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        form = QFormLayout()

        self._datetime_combo = ColumnComboBox(self)
        self._datetime_combo.set_columns(result.available_datetime_columns, select=result.datetime_column)
        form.addRow(QLabel(self.tr("Time column"), self), self._datetime_combo)

        self._value_combo = ColumnComboBox(self)
        self._value_combo.set_columns(result.available_value_columns, select=result.value_column)
        form.addRow(QLabel(self.tr("Value column"), self), self._value_combo)

        self._frequency_combo = QComboBox(self)
        self._frequency_combo.addItem(self.tr("Original frequency"), None)
        for frequency, label in (("D", self.tr("Daily")), ("W", self.tr("Weekly")), ("MS", self.tr("Monthly"))):
            self._frequency_combo.addItem(label, frequency)
        self._frequency_combo.setCurrentIndex(self._frequency_combo.findData(result.resample_frequency))
        form.addRow(QLabel(self.tr("Resample to"), self), self._frequency_combo)

        self._auto_period = QCheckBox(self.tr("Auto-detect seasonal period"), self)
        self._auto_period.setChecked(result.seasonal_period is None)
        form.addRow(self._auto_period)

        self._period_spin = QSpinBox(self)
        self._period_spin.setRange(2, 10_000)
        self._period_spin.setValue(result.seasonal_period or 7)
        self._period_spin.setEnabled(not self._auto_period.isChecked())
        form.addRow(QLabel(self.tr("Seasonal period"), self), self._period_spin)

        self._model_combo = QComboBox(self)
        self._model_combo.addItem(self.tr("Additive"), DecompositionModel.ADDITIVE)
        self._model_combo.addItem(self.tr("Multiplicative"), DecompositionModel.MULTIPLICATIVE)
        self._model_combo.setCurrentIndex(self._model_combo.findData(result.decomposition_model))
        form.addRow(QLabel(self.tr("Decomposition"), self), self._model_combo)
        layout.addLayout(form)

        hint = QLabel(self.tr("Duplicate timestamps are averaged. Gaps are preserved and are not interpolated."), self)
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self._apply_button = QPushButton(self.tr("Apply"), self)
        layout.addWidget(self._apply_button)
        layout.addStretch(1)

        self._auto_period.toggled.connect(self._period_spin.setDisabled)
        self._apply_button.clicked.connect(self._on_apply_clicked)

    @staticmethod
    def _configuration_from_result(
        result: TimeSeriesResult,
    ) -> tuple[str, str, str | None, int | None, DecompositionModel]:
        """Return a configuration tuple for the already displayed result."""
        return (
            result.datetime_column,
            result.value_column,
            result.resample_frequency,
            result.seasonal_period,
            result.decomposition_model,
        )

    def _on_apply_clicked(self) -> None:
        """Store pending controls and request a single replacement analysis."""
        self._applied_configuration = self.pending_configuration()
        self.analysis_requested.emit()

    def pending_configuration(self) -> tuple[str, str, str | None, int | None, DecompositionModel]:
        """Return the controls' current, not-yet-applied choices."""
        return (
            self._datetime_combo.current_column(),
            self._value_combo.current_column(),
            self._frequency_combo.currentData(),
            None if self._auto_period.isChecked() else self._period_spin.value(),
            DecompositionModel(self._model_combo.currentData()),
        )

    def analysis_configuration(self) -> tuple[str, str, str | None, int | None, DecompositionModel]:
        """Return the most recently applied analysis configuration."""
        return self._applied_configuration
