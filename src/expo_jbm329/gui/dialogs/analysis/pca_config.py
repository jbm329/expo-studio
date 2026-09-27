"""Configuration widget for principal component analysis."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QGroupBox,
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
    """

    analysis_requested = pyqtSignal()

    def __init__(self, result: PCAResult, parent: QWidget | None = None) -> None:
        """Initialize the widget from the currently displayed PCA result.

        Args:
            result: PCA result supplying selectable columns and the applied
                feature/scaling configuration.
            parent: Optional parent widget.
        """
        super().__init__(parent)
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

        self._selection_label = QLabel(group)
        self._selection_label.setWordWrap(True)
        group_layout.addWidget(self._selection_label)

        self._apply_button = QPushButton(self.tr("Apply"), group)
        group_layout.addWidget(self._apply_button)
        layout.addWidget(group, 1)

        self._update_apply_state()
        self._column_list.itemChanged.connect(self._on_column_check_changed)
        self._apply_button.clicked.connect(self._on_apply_clicked)

    def _on_column_check_changed(self, _item: QListWidgetItem) -> None:
        """Refresh the pending selection feedback."""
        self._update_apply_state()

    def _on_apply_clicked(self) -> None:
        """Store a valid pending configuration and request a new PCA fit."""
        columns = self.checked_columns()
        if len(columns) < MIN_SELECTED_COLUMNS:
            return
        self._applied_columns = columns
        self._applied_standardize = self._standardize_checkbox.isChecked()
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
