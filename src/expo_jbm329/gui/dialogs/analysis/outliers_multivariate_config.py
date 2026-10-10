"""Configuration widget for multivariate Outlier Explorer screening."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from expo_jbm329.services.analysis.multivariate_outliers import (
    MAX_CONTAMINATION,
    MAX_LOF_NEIGHBORS,
    MIN_CONTAMINATION,
    MIN_LOF_NEIGHBORS,
    MIN_SELECTED_COLUMNS,
    MultivariateOutlierMethod,
)
from expo_jbm329.utils.format_utils import fmt_int

if TYPE_CHECKING:
    from expo_jbm329.services.analysis.multivariate_outliers import MultivariateOutlierResult


class MultivariateOutliersConfigWidget(QWidget):
    """Lets users configure Isolation Forest or LOF multivariate screening.

    Every edit replaces outdated results with the Apply prompt; only Apply
    requests a new fit.
    """

    analysis_requested = pyqtSignal()
    configuration_changed = pyqtSignal()
    univariate_requested = pyqtSignal()

    def __init__(self, result: MultivariateOutlierResult, parent: QWidget | None = None) -> None:
        """Initialize pending and applied controls from a displayed result."""
        super().__init__(parent)
        self._configuration_revision = 0
        self._applied_configuration = self._configuration_from_result(result)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        form = QFormLayout()

        self._mode_combo = QComboBox(self)
        self._mode_combo.addItem(self.tr("Univariate (by column)"), False)
        self._mode_combo.addItem(self.tr("Multivariate (by row)"), True)
        self._mode_combo.setCurrentIndex(1)
        form.addRow(QLabel(self.tr("Mode"), self), self._mode_combo)

        self._method_combo = QComboBox(self)
        self._method_combo.addItem(self.tr("Isolation Forest"), MultivariateOutlierMethod.ISOLATION_FOREST)
        self._method_combo.addItem(self.tr("Local Outlier Factor"), MultivariateOutlierMethod.LOCAL_OUTLIER_FACTOR)
        self._method_combo.setCurrentIndex(self._method_combo.findData(result.method))
        form.addRow(QLabel(self.tr("Method"), self), self._method_combo)

        self._standardize_checkbox = QCheckBox(self.tr("Standardize features"), self)
        self._standardize_checkbox.setChecked(result.standardize)
        form.addRow(self._standardize_checkbox)

        self._contamination_spin = QDoubleSpinBox(self)
        self._contamination_spin.setRange(MIN_CONTAMINATION * 100, MAX_CONTAMINATION * 100)
        self._contamination_spin.setSuffix(self.tr("%"))
        self._contamination_spin.setDecimals(1)
        self._contamination_spin.setSingleStep(1.0)
        self._contamination_spin.setValue(result.contamination * 100)
        self._contamination_spin.setKeyboardTracking(False)
        form.addRow(QLabel(self.tr("Expected outliers"), self), self._contamination_spin)

        self._neighbors_spin = QSpinBox(self)
        self._neighbors_spin.setRange(MIN_LOF_NEIGHBORS, MAX_LOF_NEIGHBORS)
        self._neighbors_spin.setValue(result.lof_neighbors)
        self._neighbors_spin.setKeyboardTracking(False)
        form.addRow(QLabel(self.tr("LOF neighbors"), self), self._neighbors_spin)
        layout.addLayout(form)
        self._update_method_controls()

        features = QGroupBox(self.tr("Features"), self)
        features_layout = QVBoxLayout(features)
        self._column_list = QListWidget(features)
        selected = set(result.columns)
        for column in result.available_columns:
            item = QListWidgetItem(column, self._column_list)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if column in selected else Qt.CheckState.Unchecked)
        features_layout.addWidget(self._column_list)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self._select_all_button = QPushButton(self.tr("Select all"), features)
        self._clear_button = QPushButton(self.tr("Clear"), features)
        actions.addWidget(self._select_all_button)
        actions.addWidget(self._clear_button)
        features_layout.addLayout(actions)
        self._selection_label = QLabel(features)
        features_layout.addWidget(self._selection_label)
        self._apply_button = QPushButton(self.tr("Apply"), features)
        features_layout.addWidget(self._apply_button)
        layout.addWidget(features, 1)

        self._update_apply_state()
        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        self._method_combo.currentIndexChanged.connect(self._on_method_changed)
        self._column_list.itemChanged.connect(self._on_column_changed)
        self._select_all_button.clicked.connect(lambda: self._set_all_columns_checked(checked=True))
        self._clear_button.clicked.connect(lambda: self._set_all_columns_checked(checked=False))
        self._apply_button.clicked.connect(self._on_apply_clicked)
        self._standardize_checkbox.toggled.connect(self._on_configuration_changed)
        self._contamination_spin.valueChanged.connect(self._on_configuration_changed)
        self._neighbors_spin.valueChanged.connect(self._on_configuration_changed)

    def _on_configuration_changed(self) -> None:
        """Invalidate displayed results without requesting a new analysis."""
        self._configuration_revision += 1
        self.configuration_changed.emit()

    @staticmethod
    def _configuration_from_result(
        result: MultivariateOutlierResult,
    ) -> tuple[tuple[str, ...], MultivariateOutlierMethod, bool, float, int]:
        """Return the applied fit inputs represented by `result`."""
        return result.columns, result.method, result.standardize, result.contamination, result.lof_neighbors

    def _on_mode_changed(self, _index: int) -> None:
        """Return to the univariate explorer when its mode is selected."""
        self._on_configuration_changed()
        if not self._mode_combo.currentData():
            self.univariate_requested.emit()

    def _on_method_changed(self, _index: int) -> None:
        """Show LOF's neighbor count only for Local Outlier Factor."""
        self._update_method_controls()
        self._on_configuration_changed()

    def _update_method_controls(self) -> None:
        """Toggle the LOF-only neighbor control."""
        self._neighbors_spin.setVisible(self.current_method() is MultivariateOutlierMethod.LOCAL_OUTLIER_FACTOR)

    def _on_column_changed(self, _item: QListWidgetItem) -> None:
        """Refresh feature-selection feedback."""
        self._update_apply_state()
        self._on_configuration_changed()

    def _set_all_columns_checked(self, *, checked: bool) -> None:
        """Set every feature to the same pending check state."""
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        changed = False
        self._column_list.blockSignals(True)
        try:
            for index in range(self._column_list.count()):
                item = self._column_list.item(index)
                if item is not None and item.checkState() != state:
                    item.setCheckState(state)
                    changed = True
        finally:
            self._column_list.blockSignals(False)
        self._update_apply_state()
        if changed:
            self._on_configuration_changed()

    def _on_apply_clicked(self) -> None:
        """Store a valid pending configuration and request one refit."""
        columns = self.checked_columns()
        if len(columns) < MIN_SELECTED_COLUMNS:
            return
        self._applied_configuration = self.pending_configuration()
        self._configuration_revision += 1
        self._update_apply_state()
        self.analysis_requested.emit()

    def _update_apply_state(self) -> None:
        """Enable Apply only if enough feature columns are selected."""
        count = len(self.checked_columns())
        self._apply_button.setEnabled(count >= MIN_SELECTED_COLUMNS)
        if count >= MIN_SELECTED_COLUMNS:
            self._selection_label.setText(self.tr("{count} selected.").format(count=fmt_int(count)))
        else:
            self._selection_label.setText(
                self.tr("{count} selected - select at least {minimum}.").format(
                    count=fmt_int(count),
                    minimum=fmt_int(MIN_SELECTED_COLUMNS),
                )
            )

    def current_method(self) -> MultivariateOutlierMethod:
        """Return the pending detection method."""
        return MultivariateOutlierMethod(self._method_combo.currentData())

    def checked_columns(self) -> tuple[str, ...]:
        """Return pending selected features in dataset order."""
        return tuple(
            item.text()
            for index in range(self._column_list.count())
            if (item := self._column_list.item(index)) is not None and item.checkState() == Qt.CheckState.Checked
        )

    def pending_configuration(self) -> tuple[tuple[str, ...], MultivariateOutlierMethod, bool, float, int]:
        """Return controls' current, not-yet-applied fit configuration."""
        return (
            self.checked_columns(),
            self.current_method(),
            self._standardize_checkbox.isChecked(),
            self._contamination_spin.value() / 100,
            self._neighbors_spin.value(),
        )

    def analysis_configuration(self) -> tuple[tuple[str, ...], MultivariateOutlierMethod, bool, float, int]:
        """Return the latest applied fit configuration."""
        return self._applied_configuration

    def configuration_revision(self) -> int:
        """Return the generation advanced by every edit and valid Apply."""
        return self._configuration_revision
