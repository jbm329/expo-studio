"""Outlier Explorer configuration widget (mode, method and threshold)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QComboBox, QDoubleSpinBox, QFormLayout, QLabel, QPushButton, QVBoxLayout, QWidget

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
    """Lets the user choose the detection mode, method and threshold.

    `summary_requested` is emitted on Apply, screening every column with
    the chosen method and threshold. A method change resets the pending
    threshold to its conventional default. Apply remains enabled for
    unchanged settings so a failed computation can be rerun. Detail column
    selection belongs to the results table.
    Every configuration edit replaces outdated results with the Apply prompt.

    This widget never computes anything itself and is never recreated by
    those recomputes.
    """

    summary_requested = pyqtSignal()
    configuration_changed = pyqtSignal()
    multivariate_requested = pyqtSignal()

    def __init__(
        self,
        result: OutlierSummaryResult,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the configuration widget.

        Args:
            result: The default or most recently computed outlier
                summary, used to populate the method and threshold.
                Must have at least one available column.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._configuration_revision = 0
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

        layout.addStretch(1)

        # Connected only after the initial population above, so setting up
        # the default selection never emits a spurious first signal.
        self._method_combo.currentIndexChanged.connect(self._on_method_changed)
        self._apply_button.clicked.connect(self._on_apply_clicked)
        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        self._threshold_spin.valueChanged.connect(self._on_configuration_changed)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _on_configuration_changed(self) -> None:
        """Invalidate displayed results without requesting a new analysis."""
        self._configuration_revision += 1
        self.configuration_changed.emit()

    def _on_mode_changed(self, _index: int) -> None:
        """Request the distinct multivariate explorer when its mode is selected."""
        self._on_configuration_changed()
        if self._mode_combo.currentData():
            self.multivariate_requested.emit()

    def _on_method_changed(self, _index: int) -> None:
        """Reset the pending threshold to the new method's default."""
        self._threshold_spin.blockSignals(True)
        try:
            self._threshold_spin.setValue(DEFAULT_THRESHOLDS[self.current_method()])
        finally:
            self._threshold_spin.blockSignals(False)
        self._update_threshold_texts()
        self._on_configuration_changed()

    def _on_apply_clicked(self) -> None:
        """Apply the pending method and threshold, and request a new summary."""
        self._applied_configuration = (self.current_method(), self.current_threshold())
        self._configuration_revision += 1
        self.summary_requested.emit()

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

    def current_method(self) -> OutlierMethod:
        """Return the selected (possibly not yet applied) detection method."""
        return OutlierMethod(self._method_combo.currentData())

    def current_threshold(self) -> float:
        """Return the selected (possibly not yet applied) threshold."""
        return self._threshold_spin.value()

    def summary_configuration(self) -> tuple[OutlierMethod, float]:
        """Return the applied ``(method, threshold)`` that determine the summary."""
        return self._applied_configuration

    def configuration_revision(self) -> int:
        """Return the generation advanced by every edit and Apply."""
        return self._configuration_revision
