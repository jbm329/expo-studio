"""Linear Regression configuration widget (target and predictors)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
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

from expo_jbm329.gui.dialogs.analysis.column_combo_box import ColumnComboBox, exclusion_tooltip
from expo_jbm329.services.analysis.regression import MAX_PREDICTORS
from expo_jbm329.utils.format_utils import fmt_int

if TYPE_CHECKING:
    from expo_jbm329.services.analysis.regression import RegressionResult

# The column name of a predictor list item (its text may carry a suffix).
_COLUMN_ROLE = Qt.ItemDataRole.UserRole
_ELIGIBLE_ROLE = Qt.ItemDataRole.UserRole + 1


class RegressionConfigWidget(QWidget):
    """Lets the user choose the regression target and predictors.

    `model_requested` is emitted when the model should be refitted:

    - when the target changes; the new target is removed from the applied
      predictors, since a column can't predict itself;
    - when a predictor selection is applied. Predictor checkboxes only
      take effect once "Apply" is clicked, so ticking several predictors
      doesn't start a fit per click. Apply stays enabled for an unchanged
      selection, so a fit can always be rerun.

    Numeric predictors are listed first, then categorical ones, then
    categorical columns with an unsuitable number of levels, disabled
    with a tooltip explaining why. The current target is listed disabled
    and unchecked. This widget never computes anything itself and is
    never recreated by a refit.
    """

    model_requested = pyqtSignal()

    def __init__(self, result: RegressionResult, parent: QWidget | None = None) -> None:
        """Initialize the configuration widget.

        Args:
            result: The most recently computed regression, used to
                populate the target and predictor pickers. Must have at
                least one available target.
            parent: Optional parent widget.
        """
        super().__init__(parent)

        self._applied_predictors = tuple(p for p in result.predictors if p != result.target)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        target_form = QFormLayout()
        self._target_combo = ColumnComboBox(self)
        self._target_combo.set_columns(result.available_targets, select=result.target)
        target_form.addRow(QLabel(self.tr("Target"), self), self._target_combo)
        layout.addLayout(target_form)

        layout.addWidget(self._build_predictors_group(result))

        self._sync_target_item()
        self._update_apply_state()

        # Connected only after the initial population above, so setting up
        # the default selection never emits a spurious first signal.
        self._target_combo.currentTextChanged.connect(self._on_target_changed)
        self._predictor_list.itemChanged.connect(self._on_predictor_check_changed)
        self._select_all_button.clicked.connect(lambda: self._set_all_predictors_checked(checked=True))
        self._clear_button.clicked.connect(lambda: self._set_all_predictors_checked(checked=False))
        self._apply_button.clicked.connect(self._on_apply_clicked)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _build_predictors_group(self, result: RegressionResult) -> QGroupBox:
        """Build the checkable predictor list with its count label and Apply button."""
        group = QGroupBox(self.tr("Predictors"), self)
        group_layout = QVBoxLayout(group)

        self._predictor_list = QListWidget(group)
        applied = set(self._applied_predictors)
        columns = result.predictor_columns
        for column in columns.numeric:
            self._add_checkable_item(column, column, checked=column in applied)
        for column in columns.categorical:
            self._add_checkable_item(self._categorical_text(column), column, checked=column in applied)
        for excluded in columns.excluded:
            item = self._add_item(self._categorical_text(excluded.name), excluded.name)
            item.setFlags((item.flags() | Qt.ItemFlag.ItemIsUserCheckable) & ~Qt.ItemFlag.ItemIsEnabled)
            item.setCheckState(Qt.CheckState.Unchecked)
            item.setData(_ELIGIBLE_ROLE, False)
            item.setToolTip(exclusion_tooltip(excluded))
        group_layout.addWidget(self._predictor_list)

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

    def _categorical_text(self, column: str) -> str:
        """Return the list text marking `column` as categorical."""
        return self.tr("{column} (categorical)").format(column=column)

    def _add_item(self, text: str, column: str) -> QListWidgetItem:
        """Append a list item showing `text` for `column`."""
        item = QListWidgetItem(text, self._predictor_list)
        item.setData(_COLUMN_ROLE, column)
        return item

    def _add_checkable_item(self, text: str, column: str, *, checked: bool) -> None:
        """Append a checkable predictor item for `column`."""
        item = self._add_item(text, column)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        item.setData(_ELIGIBLE_ROLE, True)

    # ------------------------------------------------------------------
    # Target
    # ------------------------------------------------------------------

    def _on_target_changed(self, _text: str) -> None:
        """Disable the new target and refit an already-applied model."""
        if not self.current_target():
            return
        self._sync_target_item()
        self._applied_predictors = tuple(p for p in self._applied_predictors if p != self.current_target())
        self._update_apply_state()
        if self._applied_predictors:
            self.model_requested.emit()

    def _sync_target_item(self) -> None:
        """Make the target's predictor item disabled and unchecked, and re-enable the others."""
        target = self.current_target()
        tooltip = self.tr("This column is the target.")
        self._predictor_list.blockSignals(True)
        try:
            for item in self._checkable_items():
                if not item.data(_ELIGIBLE_ROLE):
                    continue
                is_target = item.data(_COLUMN_ROLE) == target
                if is_target:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
                    item.setCheckState(Qt.CheckState.Unchecked)
                    item.setToolTip(tooltip)
                elif not item.flags() & Qt.ItemFlag.ItemIsEnabled:
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEnabled)
                    item.setToolTip("")
        finally:
            self._predictor_list.blockSignals(False)

    # ------------------------------------------------------------------
    # Predictors
    # ------------------------------------------------------------------

    def _on_predictor_check_changed(self, _item: QListWidgetItem) -> None:
        """Refresh the selection count and Apply button after a checkbox toggle."""
        self._update_apply_state()

    def _set_all_predictors_checked(self, *, checked: bool) -> None:
        """Set every enabled predictor to the same pending check state."""
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        self._predictor_list.blockSignals(True)
        try:
            for item in self._checkable_items():
                if item.data(_ELIGIBLE_ROLE) and item.flags() & Qt.ItemFlag.ItemIsEnabled:
                    item.setCheckState(state)
        finally:
            self._predictor_list.blockSignals(False)
        self._update_apply_state()

    def _on_apply_clicked(self) -> None:
        """Apply the checked predictors and request a refit."""
        checked = self.checked_predictors()
        if not self._is_valid_selection(checked):
            return
        self._applied_predictors = checked
        self._update_apply_state()
        self.model_requested.emit()

    def _update_apply_state(self) -> None:
        """Enable Apply only for a valid selection and explain the count."""
        checked = self.checked_predictors()
        self._apply_button.setEnabled(self._is_valid_selection(checked))
        self._selection_label.setText(self._selection_text(len(checked)))

    def _selection_text(self, count: int) -> str:
        """Return the translated selection count, with a hint when it is out of range."""
        if count == 0:
            return self.tr("None selected - select at least one.")
        if count > MAX_PREDICTORS:
            return self.tr("{count} selected - select at most {maximum}.").format(
                count=fmt_int(count), maximum=fmt_int(MAX_PREDICTORS)
            )
        return self.tr("{count} selected (at most {maximum}).").format(
            count=fmt_int(count), maximum=fmt_int(MAX_PREDICTORS)
        )

    @staticmethod
    def _is_valid_selection(predictors: tuple[str, ...]) -> bool:
        """Return whether `predictors` has an allowed number of columns."""
        return 1 <= len(predictors) <= MAX_PREDICTORS

    def _checkable_items(self) -> list[QListWidgetItem]:
        """Return all predictor items rendered with checkboxes."""
        return [
            item
            for index in range(self._predictor_list.count())
            if (item := self._predictor_list.item(index)) is not None and item.flags() & Qt.ItemFlag.ItemIsUserCheckable
        ]

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def current_target(self) -> str:
        """Return the selected target column, or ``""`` if there is none."""
        return self._target_combo.current_column()

    def applied_predictors(self) -> tuple[str, ...]:
        """Return the predictors of the most recently applied selection, in list order."""
        return self._applied_predictors

    def checked_predictors(self) -> tuple[str, ...]:
        """Return the currently checked predictors (applied or not), in list order."""
        return tuple(
            str(item.data(_COLUMN_ROLE))
            for item in self._checkable_items()
            if item.data(_ELIGIBLE_ROLE) and item.checkState() == Qt.CheckState.Checked
        )

    def model_configuration(self) -> tuple[str, tuple[str, ...]]:
        """Return the ``(target, applied_predictors)`` that determine the model."""
        return self.current_target(), self._applied_predictors
