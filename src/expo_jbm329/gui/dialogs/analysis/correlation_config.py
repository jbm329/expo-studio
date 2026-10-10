"""Correlation Explorer configuration widget (method and matrix columns)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from expo_jbm329.services.analysis.correlation import (
    MAX_SELECTED_COLUMNS,
    MIN_SELECTED_COLUMNS,
    CorrelationMethod,
)
from expo_jbm329.utils.format_utils import fmt_int

if TYPE_CHECKING:
    from expo_jbm329.services.analysis.correlation import CorrelationMatrixResult


class CorrelationConfigWidget(QWidget):
    """Lets the user choose the correlation method and matrix columns.

    `matrix_requested` is emitted when Apply is clicked. The method and
    checked columns only take effect then, avoiding a costly job per
    change. Apply stays enabled for unchanged valid settings so cancelled
    computations can be rerun. Pair selection belongs to the results table.
    Method edits emit `configuration_changed` so displayed results can be
    replaced by the Apply prompt.

    This widget never computes anything itself and is never recreated by
    those recomputes.
    """

    matrix_requested = pyqtSignal()
    configuration_changed = pyqtSignal()

    def __init__(
        self,
        result: CorrelationMatrixResult,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the configuration widget.

        Args:
            result: The default or most recently computed correlation
                matrix, used to populate the method and column list.
                Must have at least `MIN_SELECTED_COLUMNS`
                available columns.
            parent: Optional parent widget.
        """
        super().__init__(parent)

        self._available_columns = result.available_columns
        self._applied_columns = result.columns
        self._applied_method = result.method

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        method_form = QFormLayout()
        self._method_combo = self._build_method_combo(result.method)
        method_form.addRow(QLabel(self.tr("Method"), self), self._method_combo)
        layout.addLayout(method_form)

        layout.addWidget(self._build_columns_group())

        self._update_apply_state()

        # Connected only after the initial population above, so setting up
        # the default selection never emits a spurious first signal.
        self._column_list.itemChanged.connect(self._on_column_check_changed)
        self._select_all_button.clicked.connect(lambda: self._set_all_columns_checked(checked=True))
        self._clear_button.clicked.connect(lambda: self._set_all_columns_checked(checked=False))
        self._apply_button.clicked.connect(self._on_apply_clicked)
        self._method_combo.currentIndexChanged.connect(self._on_method_changed)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _build_method_combo(self, method: CorrelationMethod) -> QComboBox:
        """Build the method picker with `method` selected."""
        combo = QComboBox(self)
        combo.addItem(self.tr("Pearson"), CorrelationMethod.PEARSON)
        combo.addItem(self.tr("Spearman"), CorrelationMethod.SPEARMAN)
        combo.addItem(self.tr("Kendall's tau-b"), CorrelationMethod.KENDALL)
        combo.setCurrentIndex(combo.findData(method))
        return combo

    def _build_columns_group(self) -> QGroupBox:
        """Build the checkable matrix-column list with its count label and Apply button."""
        group = QGroupBox(self.tr("Columns in matrix"), self)
        group_layout = QVBoxLayout(group)

        self._column_list = QListWidget(group)
        applied = set(self._applied_columns)
        for column in self._available_columns:
            item = QListWidgetItem(column, self._column_list)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if column in applied else Qt.CheckState.Unchecked)

        group_layout.addWidget(self._column_list)

        actions = QFormLayout()
        actions.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        actions.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self._select_all_button = QPushButton(self.tr("Select all"), group)
        self._clear_button = QPushButton(self.tr("Clear"), group)
        actions.addRow(self._select_all_button, self._clear_button)
        group_layout.addLayout(actions)

        self._selection_label = QLabel(group)
        self._selection_label.setWordWrap(True)
        group_layout.addWidget(self._selection_label)

        self._apply_button = QPushButton(self.tr("Apply"), group)
        group_layout.addWidget(self._apply_button)

        return group

    # ------------------------------------------------------------------
    # Method and matrix columns
    # ------------------------------------------------------------------

    def _on_method_changed(self, _index: int) -> None:
        """Invalidate displayed results without requesting a matrix computation."""
        self.configuration_changed.emit()

    def _on_column_check_changed(self, _item: QListWidgetItem) -> None:
        """Refresh the selection count and Apply button after a checkbox toggle."""
        self._update_apply_state()

    def _set_all_columns_checked(self, *, checked: bool) -> None:
        """Set every matrix column to the same pending check state."""
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        self._column_list.blockSignals(True)
        try:
            for index in range(self._column_list.count()):
                item = self._column_list.item(index)
                if item is not None:
                    item.setCheckState(state)
        finally:
            self._column_list.blockSignals(False)
        self._update_apply_state()

    def _on_apply_clicked(self) -> None:
        """Apply the selected method and checked columns, and request a matrix recompute."""
        checked = self.checked_columns()
        if not self._is_valid_selection(checked):
            return
        self._applied_columns = checked
        self._applied_method = self.current_method()
        self._update_apply_state()
        self.matrix_requested.emit()

    def _update_apply_state(self) -> None:
        """Enable Apply only for a valid selection and explain the count."""
        checked = self.checked_columns()
        self._apply_button.setEnabled(self._is_valid_selection(checked))
        self._selection_label.setText(self._selection_text(len(checked)))

    def _selection_text(self, count: int) -> str:
        """Return the translated selection count, with a hint when it is out of range."""
        if count < MIN_SELECTED_COLUMNS:
            return self.tr("{count} selected - select at least {minimum}.").format(
                count=fmt_int(count), minimum=fmt_int(MIN_SELECTED_COLUMNS)
            )
        if count > MAX_SELECTED_COLUMNS:
            return self.tr("{count} selected - select at most {maximum}.").format(
                count=fmt_int(count), maximum=fmt_int(MAX_SELECTED_COLUMNS)
            )
        return self.tr("{count} selected (at most {maximum}).").format(
            count=fmt_int(count), maximum=fmt_int(MAX_SELECTED_COLUMNS)
        )

    @staticmethod
    def _is_valid_selection(columns: tuple[str, ...]) -> bool:
        """Return whether `columns` has an allowed number of columns."""
        return MIN_SELECTED_COLUMNS <= len(columns) <= MAX_SELECTED_COLUMNS

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def current_method(self) -> CorrelationMethod:
        """Return the selected (possibly not yet applied) correlation method."""
        return CorrelationMethod(self._method_combo.currentData())

    def applied_method(self) -> CorrelationMethod:
        """Return the method of the most recently applied configuration."""
        return self._applied_method

    def applied_columns(self) -> tuple[str, ...]:
        """Return the columns of the most recently applied selection, in matrix order."""
        return self._applied_columns

    def checked_columns(self) -> tuple[str, ...]:
        """Return the currently checked columns (applied or not), in dataset order."""
        return tuple(
            item.text()
            for index in range(self._column_list.count())
            if (item := self._column_list.item(index)) is not None and item.checkState() == Qt.CheckState.Checked
        )

    def matrix_configuration(self) -> tuple[CorrelationMethod, tuple[str, ...]]:
        """Return the applied ``(method, columns)`` that determine the matrix."""
        return self._applied_method, self._applied_columns
