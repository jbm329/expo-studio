"""Configuration widget for principal component analysis."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from expo_jbm329.services.analysis.pca import MIN_SELECTED_COLUMNS
from expo_jbm329.utils.format_utils import fmt_int

if TYPE_CHECKING:
    from expo_jbm329.services.analysis.pca import PCAResult


class PCAConfigWidget(QWidget):
    """Lets users select PCA features and whether to standardize them.

    Checking features or changing the scaling preference only changes the
    pending configuration. The expensive fit is requested once the user
    presses Apply, so several changes don't queue several background jobs.
    Every edit emits `configuration_changed` to replace outdated results
    with the Apply prompt.
    """

    analysis_requested = pyqtSignal()
    configuration_changed = pyqtSignal()

    def __init__(self, result: PCAResult, parent: QWidget | None = None) -> None:
        """Initialize the widget from the currently displayed PCA result.

        Args:
            result: PCA result supplying selectable columns and the applied
                feature/scaling configuration.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._configuration_revision = 0
        self._available_columns = result.available_columns
        self._applied_columns = result.columns
        self._applied_standardize = result.standardize

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._standardize_checkbox = QCheckBox(self.tr("Standardize features"), self)
        self._standardize_checkbox.setChecked(result.standardize)
        self._standardize_checkbox.setToolTip(
            self.tr("Scale each selected feature to zero mean and unit variance before fitting PCA.")
        )
        layout.addWidget(self._standardize_checkbox)

        group = QGroupBox(self.tr("Features"), self)
        group_layout = QVBoxLayout(group)
        self._column_list = QListWidget(group)
        applied = set(result.columns)
        for column in result.available_columns:
            item = QListWidgetItem(column, self._column_list)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if column in applied else Qt.CheckState.Unchecked)
        group_layout.addWidget(self._column_list)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self._select_all_button = QPushButton(self.tr("Select all"), group)
        self._clear_button = QPushButton(self.tr("Clear"), group)
        actions.addWidget(self._select_all_button)
        actions.addWidget(self._clear_button)
        group_layout.addLayout(actions)

        self._selection_label = QLabel(group)
        self._selection_label.setWordWrap(True)
        group_layout.addWidget(self._selection_label)

        self._apply_button = QPushButton(self.tr("Apply"), group)
        group_layout.addWidget(self._apply_button)
        layout.addWidget(group, 1)

        self._update_apply_state()
        self._column_list.itemChanged.connect(self._on_column_check_changed)
        self._select_all_button.clicked.connect(lambda: self._set_all_columns_checked(checked=True))
        self._clear_button.clicked.connect(lambda: self._set_all_columns_checked(checked=False))
        self._apply_button.clicked.connect(self._on_apply_clicked)
        self._standardize_checkbox.toggled.connect(self._on_configuration_changed)

    def _on_configuration_changed(self) -> None:
        """Invalidate the displayed fit after a pending configuration edit."""
        self._configuration_revision += 1
        self.configuration_changed.emit()

    def _on_column_check_changed(self, _item: QListWidgetItem) -> None:
        """Refresh the pending selection feedback."""
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
        """Store a valid pending configuration and request a new PCA fit."""
        columns = self.checked_columns()
        if len(columns) < MIN_SELECTED_COLUMNS:
            return
        self._applied_columns = columns
        self._applied_standardize = self._standardize_checkbox.isChecked()
        self._configuration_revision += 1
        self._update_apply_state()
        self.analysis_requested.emit()

    def _update_apply_state(self) -> None:
        """Enable Apply for at least two selected features and show the count."""
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

    def checked_columns(self) -> tuple[str, ...]:
        """Return pending checked features in their dataset order."""
        return tuple(
            item.text()
            for index in range(self._column_list.count())
            if (item := self._column_list.item(index)) is not None and item.checkState() == Qt.CheckState.Checked
        )

    def analysis_configuration(self) -> tuple[tuple[str, ...], bool]:
        """Return the applied ``(columns, standardize)`` configuration."""
        return self._applied_columns, self._applied_standardize

    def configuration_revision(self) -> int:
        """Return the generation advanced by every edit and valid Apply."""
        return self._configuration_revision
