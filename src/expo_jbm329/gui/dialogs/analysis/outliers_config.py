"""Outlier Explorer configuration widget (method, threshold, detail column)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QComboBox, QDoubleSpinBox, QFormLayout, QLabel, QWidget

from expo_jbm329.gui.dialogs.analysis.column_combo_box import ColumnComboBox
from expo_jbm329.services.analysis.outliers import (
    DEFAULT_THRESHOLDS,
    MAX_THRESHOLD,
    MIN_THRESHOLD,
    OutlierMethod,
)

if TYPE_CHECKING:
    from expo_jbm329.services.analysis.outliers import OutlierSummaryResult

_THRESHOLD_DECIMALS = 2
_THRESHOLD_STEP = 0.1


class OutliersConfigWidget(QWidget):
    """Lets the user choose the detection method, its threshold and the detail column.

    Two kinds of change are reported separately, because they need
    different amounts of recomputation:

    - `summary_requested`: the method or threshold changed, so every
      column is screened again (and the detail column with it). A method
      change resets the threshold to that method's conventional default.
      The threshold only takes effect on Enter, focus loss or an arrow
      step, not on every keystroke.
    - `column_changed`: the detail column changed. Only that column's
      detail is recomputed.

    This widget never computes anything itself and is never recreated by
    those recomputes.
    """

    summary_requested = pyqtSignal()
    column_changed = pyqtSignal(str)

    def __init__(
        self,
        result: OutlierSummaryResult,
        column: str | None,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the configuration widget.

        Args:
            result: The most recently computed outlier summary, used to
                populate the method, threshold and column pickers. Must
                have at least one available column.
            column: The column to select initially, or `None` for the
                first available one.
            parent: Optional parent widget.
        """
        super().__init__(parent)

        form = QFormLayout(self)
        form.setContentsMargins(0, 0, 0, 0)

        self._method_combo = QComboBox(self)
        self._method_combo.addItem(self.tr("IQR (Tukey's fences)"), OutlierMethod.IQR)
        self._method_combo.addItem(self.tr("Z-score"), OutlierMethod.Z_SCORE)
        self._method_combo.addItem(self.tr("Modified Z-score"), OutlierMethod.MODIFIED_Z_SCORE)
        self._method_combo.setCurrentIndex(self._method_combo.findData(result.method))
        form.addRow(QLabel(self.tr("Method"), self), self._method_combo)

        self._threshold_label = QLabel(self)
        self._threshold_spin = QDoubleSpinBox(self)
        self._threshold_spin.setRange(MIN_THRESHOLD, MAX_THRESHOLD)
        self._threshold_spin.setDecimals(_THRESHOLD_DECIMALS)
        self._threshold_spin.setSingleStep(_THRESHOLD_STEP)
        # Emit valueChanged only once editing is finished, not per keystroke.
        self._threshold_spin.setKeyboardTracking(False)
        self._threshold_spin.setValue(result.threshold)
        form.addRow(self._threshold_label, self._threshold_spin)
        self._update_threshold_texts()

        self._column_combo = ColumnComboBox(self)
        self._column_combo.set_columns(result.available_columns, select=column or "")
        form.addRow(QLabel(self.tr("Column"), self), self._column_combo)

        # Connected only after the initial population above, so setting up
        # the default selection never emits a spurious first signal.
        self._method_combo.currentIndexChanged.connect(self._on_method_changed)
        self._threshold_spin.valueChanged.connect(self._on_threshold_changed)
        self._column_combo.currentTextChanged.connect(self._on_column_changed)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _on_method_changed(self, _index: int) -> None:
        """Reset the threshold to the new method's default and request a new summary."""
        self._threshold_spin.blockSignals(True)
        try:
            self._threshold_spin.setValue(DEFAULT_THRESHOLDS[self.current_method()])
        finally:
            self._threshold_spin.blockSignals(False)
        self._update_threshold_texts()
        self.summary_requested.emit()

    def _on_threshold_changed(self, _value: float) -> None:
        """Request a new summary for the new threshold."""
        self.summary_requested.emit()

    def _on_column_changed(self, _text: str) -> None:
        """Emit `column_changed` for a newly selected column."""
        column = self.current_column()
        if column:
            self.column_changed.emit(column)

    def _update_threshold_texts(self) -> None:
        """Label the threshold for the current method."""
        if self.current_method() is OutlierMethod.IQR:
            self._threshold_label.setText(self.tr("IQR multiplier"))
            self._threshold_spin.setToolTip(
                self.tr("Values more than this many IQRs below Q1 or above Q3 are flagged.")
            )
        else:
            self._threshold_label.setText(self.tr("Score threshold"))
            self._threshold_spin.setToolTip(self.tr("Values whose absolute score exceeds this are flagged."))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_column(self, column: str) -> None:
        """Select `column` and emit `column_changed` if it changed; unknown columns are ignored.

        Args:
            column: Column to select.
        """
        if column == self.current_column() or column not in self._column_combo.eligible_columns():
            return
        self._column_combo.setCurrentIndex(self._column_combo.findText(column))

    def current_method(self) -> OutlierMethod:
        """Return the selected detection method."""
        return OutlierMethod(self._method_combo.currentData())

    def current_threshold(self) -> float:
        """Return the selected threshold."""
        return self._threshold_spin.value()

    def summary_configuration(self) -> tuple[OutlierMethod, float]:
        """Return the ``(method, threshold)`` that determine the summary."""
        return self.current_method(), self.current_threshold()

    def current_column(self) -> str:
        """Return the selected detail column, or ``""`` if there is none."""
        return self._column_combo.current_column()
