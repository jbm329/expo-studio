"""Correlation Explorer configuration widget (method, matrix columns, detail pair)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from expo_jbm329.gui.dialogs.analysis.column_combo_box import ColumnComboBox
from expo_jbm329.services.analysis.correlation import (
    MAX_SELECTED_COLUMNS,
    MIN_SELECTED_COLUMNS,
    CorrelationMethod,
)
from expo_jbm329.utils.format_utils import fmt_int

if TYPE_CHECKING:
    from expo_jbm329.services.analysis.correlation import CorrelationMatrixResult


class CorrelationConfigWidget(QWidget):
    """Lets the user choose the correlation method, matrix columns and detail pair.

    Two kinds of change are reported separately, because they need
    different amounts of recomputation:

    - `matrix_requested`: the method changed, or a new column selection
      was applied. The whole matrix (and the detail pair) is recomputed.
      Column checkboxes only take effect once "Apply" is clicked, so
      ticking several columns doesn't start a costly job per click.
      Apply stays enabled for an unchanged selection, so a cancelled
      computation can be rerun.
    - `pair_changed`: the X/Y pair changed. Only the pair detail is
      recomputed.

    This widget never computes anything itself and is never recreated by
    those recomputes.
    """

    matrix_requested = pyqtSignal()
    pair_changed = pyqtSignal(str, str)  # x_column, y_column

    def __init__(
        self,
        result: CorrelationMatrixResult,
        pair: tuple[str, str] | None,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the configuration widget.

        Args:
            result: The most recently computed correlation matrix, used to
                populate the method, column list and pair pickers. Must
                have at least `MIN_SELECTED_COLUMNS` available columns.
            pair: The ``(x, y)`` pair to select initially, or `None` for
                the first two available columns.
            parent: Optional parent widget.
        """
        super().__init__(parent)

        self._available_columns = result.available_columns
        self._applied_columns = result.columns

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        method_form = QFormLayout()
        self._method_combo = self._build_method_combo(result.method)
        method_form.addRow(QLabel(self.tr("Method"), self), self._method_combo)
        layout.addLayout(method_form)

        layout.addWidget(self._build_columns_group())
        layout.addWidget(self._build_pair_group(pair))

        self._update_apply_state()

        # Connected only after the initial population above, so setting up
        # the default selection never emits a spurious first signal.
        self._method_combo.currentIndexChanged.connect(self._on_method_changed)
        self._column_list.itemChanged.connect(self._on_column_check_changed)
        self._select_all_button.clicked.connect(lambda: self._set_all_columns_checked(checked=True))
        self._clear_button.clicked.connect(lambda: self._set_all_columns_checked(checked=False))
        self._apply_button.clicked.connect(self._on_apply_clicked)
        self._x_combo.currentTextChanged.connect(self._on_x_changed)
        self._y_combo.currentTextChanged.connect(self._on_y_changed)

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

        return group

    def _build_pair_group(self, pair: tuple[str, str] | None) -> QGroupBox:
        """Build the X/Y pickers for the scatterplot pair."""
        group = QGroupBox(self.tr("Scatterplot"), self)
        form = QFormLayout(group)

        x_column, y_column = pair if pair is not None else ("", "")

        self._x_combo = ColumnComboBox(group)
        self._x_combo.set_columns(self._available_columns, select=x_column)

        self._y_combo = ColumnComboBox(group)
        self._populate_y_combo(select=y_column)

        form.addRow(QLabel(self.tr("X variable"), group), self._x_combo)
        form.addRow(QLabel(self.tr("Y variable"), group), self._y_combo)
        return group

    def _populate_y_combo(self, *, select: str) -> None:
        """Rebuild the Y combo's items, excluding the current X column."""
        x_column = self._x_combo.current_column()
        self._y_combo.blockSignals(True)
        try:
            self._y_combo.set_columns(
                [column for column in self._available_columns if column != x_column],
                select=select,
            )
        finally:
            self._y_combo.blockSignals(False)

    # ------------------------------------------------------------------
    # Method and matrix columns
    # ------------------------------------------------------------------

    def _on_method_changed(self, _index: int) -> None:
        """Request a matrix recompute for the new method (with the applied columns)."""
        self.matrix_requested.emit()

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
        """Apply the checked columns and request a matrix recompute."""
        checked = self.checked_columns()
        if not self._is_valid_selection(checked):
            return
        self._applied_columns = checked
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
    # Pair
    # ------------------------------------------------------------------

    def _on_x_changed(self, _x_text: str) -> None:
        """Rebuild the Y combo (excluding the new X column) and emit the pair."""
        x_column = self._x_combo.current_column()
        if not x_column:
            return
        y_column = self._y_combo.current_column()
        self._populate_y_combo(select=y_column if y_column != x_column else "")
        self._emit_pair()

    def _on_y_changed(self, _y_text: str) -> None:
        """Emit the pair when the Y combo changes."""
        self._emit_pair()

    def _emit_pair(self) -> None:
        """Emit `pair_changed` with the current pair, if complete."""
        pair = self.current_pair()
        if pair is not None:
            self.pair_changed.emit(*pair)

    def set_pair(self, x_column: str, y_column: str) -> None:
        """Select the ``(x_column, y_column)`` pair and emit `pair_changed` if it changed.

        Emits at most once, however many combos had to change. Unknown or
        identical columns are ignored.

        Args:
            x_column: Column to select as X.
            y_column: Column to select as Y.
        """
        if (
            x_column == y_column
            or x_column not in self._available_columns
            or y_column not in self._available_columns
            or self.current_pair() == (x_column, y_column)
        ):
            return

        self._x_combo.blockSignals(True)
        try:
            self._x_combo.setCurrentIndex(self._x_combo.findText(x_column))
        finally:
            self._x_combo.blockSignals(False)
        self._populate_y_combo(select=y_column)
        self._emit_pair()

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def current_method(self) -> CorrelationMethod:
        """Return the selected correlation method."""
        return CorrelationMethod(self._method_combo.currentData())

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
        """Return the ``(method, applied_columns)`` that determine the matrix."""
        return self.current_method(), self._applied_columns

    def current_pair(self) -> tuple[str, str] | None:
        """Return the selected ``(x_column, y_column)`` pair, or `None` if incomplete."""
        x_column = self._x_combo.current_column()
        y_column = self._y_combo.current_column()
        if not x_column or not y_column:
            return None
        return x_column, y_column
