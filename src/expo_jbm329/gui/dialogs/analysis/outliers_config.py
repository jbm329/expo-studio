"""Outlier Explorer configuration widget (method, threshold, detail column)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QSignalBlocker, pyqtSignal
from PyQt6.QtWidgets import QComboBox, QDoubleSpinBox, QFormLayout, QLabel, QPushButton, QVBoxLayout, QWidget

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

    - `summary_requested`: "Apply" was clicked, so every column is
      screened again with the chosen method and threshold (and the detail
      column with it). Method and threshold changes are pending until
      then; a method change resets the threshold to that method's
      conventional default. Apply stays enabled for an unchanged
      configuration, so a failed computation can be rerun.
    - `column_changed`: the detail column changed. Only that column's
      detail is recomputed. The column picker stays disabled until the
      controller reports a displayed summary via
      `set_column_selection_enabled`, because a column detail is only
      shown alongside a summary.

    This widget never computes anything itself and is never recreated by
    those recomputes.
    """

    summary_requested = pyqtSignal()
    column_changed = pyqtSignal(str)
    multivariate_requested = pyqtSignal()

    def __init__(
        self,
        result: OutlierSummaryResult,
        column: str | None,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the configuration widget.

        Args:
            result: The default or most recently computed outlier
                summary, used to populate the method, threshold and column
                pickers. Must have at least one available column.
            column: The column to select initially, or `None` for the
                first available one.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._applied_configuration = (result.method, result.threshold)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        form = QFormLayout()

        self._mode_combo = QComboBox(self)
        self._mode_combo.addItem(self.tr("Univariate (by column)"), False)
        self._mode_combo.addItem(self.tr("Multivariate (by row)"), True)
        form.addRow(QLabel(self.tr("Mode"), self), self._mode_combo)

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
        self._threshold_spin.setValue(result.threshold)
        form.addRow(self._threshold_label, self._threshold_spin)
        self._update_threshold_texts()
        layout.addLayout(form)

        self._apply_button = QPushButton(self.tr("Apply"), self)
        layout.addWidget(self._apply_button)

        column_form = QFormLayout()
        self._column_label = QLabel(self.tr("Column"), self)
        self._column_combo = ColumnComboBox(self)
        self._column_combo.set_columns(result.available_columns, select=column or "")
        column_form.addRow(self._column_label, self._column_combo)
        layout.addLayout(column_form)
        layout.addStretch(1)
        self.set_column_selection_enabled(enabled=False)

        # Connected only after the initial population above, so setting up
        # the default selection never emits a spurious first signal.
        self._method_combo.currentIndexChanged.connect(self._on_method_changed)
        self._apply_button.clicked.connect(self._on_apply_clicked)
        self._column_combo.currentTextChanged.connect(self._on_column_changed)
        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _on_mode_changed(self, _index: int) -> None:
        """Request the distinct multivariate explorer when its mode is selected."""
        if self._mode_combo.currentData():
            self.multivariate_requested.emit()

    def _on_method_changed(self, _index: int) -> None:
        """Reset the pending threshold to the new method's default."""
        self._threshold_spin.setValue(DEFAULT_THRESHOLDS[self.current_method()])
        self._update_threshold_texts()

    def _on_apply_clicked(self) -> None:
        """Apply the pending method and threshold, and request a new summary."""
        self._applied_configuration = (self.current_method(), self.current_threshold())
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

    def set_column(self, column: str, *, notify: bool = True) -> None:
        """Select `column` and emit `column_changed` if it changed; unknown columns are ignored.

        Args:
            column: Column to select.
            notify: Whether to emit `column_changed`. `False` only syncs
                the picker with a column whose detail is already displayed.
        """
        if column == self.current_column() or column not in self._column_combo.eligible_columns():
            return
        blocker = None if notify else QSignalBlocker(self._column_combo)
        try:
            self._column_combo.setCurrentIndex(self._column_combo.findText(column))
        finally:
            if blocker is not None:
                blocker.unblock()

    def set_column_selection_enabled(self, *, enabled: bool) -> None:
        """Enable or disable the detail column picker.

        Args:
            enabled: Whether a summary is displayed, so a column change can
                update its detail.
        """
        self._column_label.setEnabled(enabled)
        self._column_combo.setEnabled(enabled)

    def is_column_selection_enabled(self) -> bool:
        """Return whether the detail column picker is enabled."""
        return self._column_combo.isEnabled()

    def current_method(self) -> OutlierMethod:
        """Return the selected (possibly not yet applied) detection method."""
        return OutlierMethod(self._method_combo.currentData())

    def current_threshold(self) -> float:
        """Return the selected (possibly not yet applied) threshold."""
        return self._threshold_spin.value()

    def summary_configuration(self) -> tuple[OutlierMethod, float]:
        """Return the applied ``(method, threshold)`` that determine the summary."""
        return self._applied_configuration

    def current_column(self) -> str:
        """Return the selected detail column, or ``""`` if there is none."""
        return self._column_combo.current_column()
