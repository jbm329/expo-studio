"""Configuration widget for K-Means, DBSCAN and Agglomerative clustering."""

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

from expo_jbm329.services.analysis.clustering import (
    MAX_CLUSTER_COUNT,
    MAX_DBSCAN_EPSILON,
    MAX_DBSCAN_MIN_SAMPLES,
    MIN_CLUSTER_COUNT,
    MIN_DBSCAN_EPSILON,
    MIN_DBSCAN_MIN_SAMPLES,
    MIN_SELECTED_COLUMNS,
    ClusteringMethod,
)
from expo_jbm329.utils.format_utils import fmt_int

if TYPE_CHECKING:
    from expo_jbm329.services.analysis.clustering import ClusteringResult


class ClusteringConfigWidget(QWidget):
    """Lets users configure a clustering fit before applying it.

    Every edit emits `configuration_changed` to replace outdated results
    with the Apply prompt. Only Apply requests a fit.
    """

    analysis_requested = pyqtSignal()
    configuration_changed = pyqtSignal()

    def __init__(self, result: ClusteringResult, parent: QWidget | None = None) -> None:
        """Initialize the pending configuration from the displayed result."""
        super().__init__(parent)
        self._configuration_revision = 0
        self._applied_columns = result.columns
        self._applied_method = result.method
        self._applied_standardize = result.standardize
        self._applied_cluster_count = result.cluster_count
        self._applied_dbscan_epsilon = result.dbscan_epsilon
        self._applied_dbscan_min_samples = result.dbscan_min_samples

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        form = QFormLayout()
        self._method_combo = self._build_method_combo(result.method)
        form.addRow(QLabel(self.tr("Method"), self), self._method_combo)
        self._standardize_checkbox = QCheckBox(self.tr("Standardize features"), self)
        self._standardize_checkbox.setChecked(result.standardize)
        self._standardize_checkbox.setToolTip(
            self.tr("Scale each selected feature to zero mean and unit variance before clustering.")
        )
        form.addRow(self._standardize_checkbox)
        layout.addLayout(form)

        self._cluster_count_spin = QSpinBox(self)
        self._cluster_count_spin.setRange(MIN_CLUSTER_COUNT, MAX_CLUSTER_COUNT)
        self._cluster_count_spin.setValue(result.cluster_count)
        self._cluster_count_spin.setKeyboardTracking(False)

        self._epsilon_spin = QDoubleSpinBox(self)
        self._epsilon_spin.setRange(MIN_DBSCAN_EPSILON, MAX_DBSCAN_EPSILON)
        self._epsilon_spin.setDecimals(2)
        self._epsilon_spin.setSingleStep(0.1)
        self._epsilon_spin.setValue(result.dbscan_epsilon)
        self._epsilon_spin.setKeyboardTracking(False)

        self._min_samples_spin = QSpinBox(self)
        self._min_samples_spin.setRange(MIN_DBSCAN_MIN_SAMPLES, MAX_DBSCAN_MIN_SAMPLES)
        self._min_samples_spin.setValue(result.dbscan_min_samples)
        self._min_samples_spin.setKeyboardTracking(False)

        parameters = QGroupBox(self.tr("Parameters"), self)
        self._parameters_form = QFormLayout(parameters)
        self._parameters_form.addRow(QLabel(self.tr("Number of clusters"), parameters), self._cluster_count_spin)
        self._parameters_form.addRow(QLabel(self.tr("Neighborhood radius (eps)"), parameters), self._epsilon_spin)
        self._parameters_form.addRow(QLabel(self.tr("Minimum samples"), parameters), self._min_samples_spin)
        layout.addWidget(parameters)
        self._update_parameter_visibility()

        features = QGroupBox(self.tr("Features"), self)
        features_layout = QVBoxLayout(features)
        self._column_list = QListWidget(features)
        applied = set(result.columns)
        for column in result.available_columns:
            item = QListWidgetItem(column, self._column_list)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if column in applied else Qt.CheckState.Unchecked)
        features_layout.addWidget(self._column_list)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self._select_all_button = QPushButton(self.tr("Select all"), features)
        self._clear_button = QPushButton(self.tr("Clear"), features)
        actions.addWidget(self._select_all_button)
        actions.addWidget(self._clear_button)
        features_layout.addLayout(actions)

        self._selection_label = QLabel(features)
        self._selection_label.setWordWrap(True)
        features_layout.addWidget(self._selection_label)
        self._apply_button = QPushButton(self.tr("Apply"), features)
        features_layout.addWidget(self._apply_button)
        layout.addWidget(features, 1)

        self._update_apply_state()
        self._method_combo.currentIndexChanged.connect(self._on_method_changed)
        self._column_list.itemChanged.connect(self._on_column_check_changed)
        self._select_all_button.clicked.connect(lambda: self._set_all_columns_checked(checked=True))
        self._clear_button.clicked.connect(lambda: self._set_all_columns_checked(checked=False))
        self._apply_button.clicked.connect(self._on_apply_clicked)
        self._standardize_checkbox.toggled.connect(self._on_configuration_changed)
        self._cluster_count_spin.valueChanged.connect(self._on_configuration_changed)
        self._epsilon_spin.valueChanged.connect(self._on_configuration_changed)
        self._min_samples_spin.valueChanged.connect(self._on_configuration_changed)

    def _on_configuration_changed(self) -> None:
        """Invalidate the displayed fit after a pending configuration edit."""
        self._configuration_revision += 1
        self.configuration_changed.emit()

    def _build_method_combo(self, method: ClusteringMethod) -> QComboBox:
        """Build the algorithm selector."""
        combo = QComboBox(self)
        combo.addItem(self.tr("K-Means"), ClusteringMethod.K_MEANS)
        combo.addItem(self.tr("DBSCAN"), ClusteringMethod.DBSCAN)
        combo.addItem(self.tr("Agglomerative"), ClusteringMethod.AGGLOMERATIVE)
        combo.setCurrentIndex(combo.findData(method))
        return combo

    def _on_method_changed(self, _index: int) -> None:
        """Show only parameters that apply to the selected algorithm."""
        self._update_parameter_visibility()
        self._on_configuration_changed()

    def _update_parameter_visibility(self) -> None:
        """Show cluster count for partitioning methods and DBSCAN inputs otherwise."""
        dbscan = self.current_method() is ClusteringMethod.DBSCAN
        for index in range(self._parameters_form.rowCount()):
            label_item = self._parameters_form.itemAt(index, QFormLayout.ItemRole.LabelRole)
            field_item = self._parameters_form.itemAt(index, QFormLayout.ItemRole.FieldRole)
            visible = dbscan if index > 0 else not dbscan
            for item in (label_item, field_item):
                widget = item.widget() if item is not None else None
                if widget is not None:
                    widget.setVisible(visible)

    def _on_column_check_changed(self, _item: QListWidgetItem) -> None:
        """Update selected-feature feedback."""
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
        """Apply a valid pending configuration and request a clustering job."""
        columns = self.checked_columns()
        if len(columns) < MIN_SELECTED_COLUMNS:
            return
        self._applied_columns = columns
        self._applied_method = self.current_method()
        self._applied_standardize = self._standardize_checkbox.isChecked()
        self._applied_cluster_count = self._cluster_count_spin.value()
        self._applied_dbscan_epsilon = self._epsilon_spin.value()
        self._applied_dbscan_min_samples = self._min_samples_spin.value()
        self._configuration_revision += 1
        self._update_apply_state()
        self.analysis_requested.emit()

    def _update_apply_state(self) -> None:
        """Enable Apply with at least two selected numeric features."""
        count = len(self.checked_columns())
        valid = count >= MIN_SELECTED_COLUMNS
        self._apply_button.setEnabled(valid)
        if valid:
            self._selection_label.setText(self.tr("{count} selected.").format(count=fmt_int(count)))
        else:
            self._selection_label.setText(
                self.tr("{count} selected - select at least {minimum}.").format(
                    count=fmt_int(count), minimum=fmt_int(MIN_SELECTED_COLUMNS)
                )
            )

    def current_method(self) -> ClusteringMethod:
        """Return the pending algorithm choice."""
        return ClusteringMethod(self._method_combo.currentData())

    def configuration_revision(self) -> int:
        """Return the generation advanced by every edit and valid Apply."""
        return self._configuration_revision

    def checked_columns(self) -> tuple[str, ...]:
        """Return pending selected features in dataset order."""
        return tuple(
            item.text()
            for index in range(self._column_list.count())
            if (item := self._column_list.item(index)) is not None and item.checkState() == Qt.CheckState.Checked
        )

    def analysis_configuration(self) -> tuple[tuple[str, ...], ClusteringMethod, bool, int, float, int]:
        """Return applied columns, method, scaling and algorithm parameters."""
        return (
            self._applied_columns,
            self._applied_method,
            self._applied_standardize,
            self._applied_cluster_count,
            self._applied_dbscan_epsilon,
            self._applied_dbscan_min_samples,
        )
