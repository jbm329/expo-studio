"""Linear Regression configuration widget (target and predictors)."""

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

from expo_jbm329.gui.dialogs.analysis.column_combo_box import ColumnComboBox, exclusion_tooltip
from expo_jbm329.services.analysis.regression import MAX_PREDICTORS
from expo_jbm329.services.analysis.regression_glm import GeneralizedTargetColumns, RegressionModel
from expo_jbm329.services.analysis.survival import SurvivalColumns
from expo_jbm329.utils.format_utils import fmt_int

if TYPE_CHECKING:
    from expo_jbm329.services.analysis.regression import RegressionResult

# The column name of a predictor list item (its text may carry a suffix).
_COLUMN_ROLE = Qt.ItemDataRole.UserRole
_ELIGIBLE_ROLE = Qt.ItemDataRole.UserRole + 1


class RegressionConfigWidget(QWidget):
    """Lets the user choose the regression target and predictors.

    `model_requested` is emitted when the model should be refitted:

    Only clicking Apply emits `model_requested`, capturing the pending
    model, outcomes and predictors. Every configuration edit emits
    `configuration_changed` so the controller can show the Apply prompt.
    Apply stays enabled for an unchanged valid selection, so a fit can
    always be rerun.

    Numeric predictors are listed first, then categorical ones, then
    categorical columns with an unsuitable number of levels, disabled
    with a tooltip explaining why. The current target is listed disabled
    and unchecked. This widget never computes anything itself and is
    never recreated by a refit.
    """

    model_requested = pyqtSignal()
    configuration_changed = pyqtSignal()

    def __init__(
        self,
        result: RegressionResult,
        generalized_targets: GeneralizedTargetColumns | None = None,
        survival_columns: SurvivalColumns | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the configuration widget.

        Args:
            result: The most recently computed regression, used to
                populate the target and predictor pickers. Must have at
                least one available target.
            generalized_targets: Binary and count target metadata.
            survival_columns: Eligible Cox duration and event columns.
            parent: Optional parent widget.
        """
        super().__init__(parent)

        self._applied_predictors = tuple(p for p in result.predictors if p != result.target)
        self._applied_model = RegressionModel.LINEAR
        self._applied_target = result.target
        self._applied_event = ""
        self._linear_targets = result.available_targets
        self._generalized_targets = (
            generalized_targets if generalized_targets is not None else GeneralizedTargetColumns(binary=(), count=())
        )
        self._survival_columns = survival_columns if survival_columns is not None else SurvivalColumns((), ())
        self._configuration_revision = 0
        self._targets_by_model: dict[RegressionModel, str] = {RegressionModel.LINEAR: result.target}
        self._model_combo = QComboBox(self)
        self._model_combo.addItem(self.tr("Linear regression"), RegressionModel.LINEAR.value)
        self._model_combo.addItem(self.tr("Logistic regression"), RegressionModel.LOGISTIC.value)
        self._model_combo.addItem(self.tr("Poisson regression"), RegressionModel.POISSON.value)
        self._model_combo.addItem(self.tr("Negative binomial regression"), RegressionModel.NEGATIVE_BINOMIAL.value)
        self._model_combo.addItem(self.tr("Cox proportional-hazards regression"), RegressionModel.COX.value)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        target_form = QFormLayout()
        target_form.addRow(QLabel(self.tr("Model"), self), self._model_combo)
        self._target_combo = ColumnComboBox(self)
        self._target_combo.set_columns(result.available_targets, select=result.target)
        self._target_label = QLabel(self.tr("Target"), self)
        target_form.addRow(self._target_label, self._target_combo)
        self._duration_combo = ColumnComboBox(self)
        first_duration = next(
            (column for column in self._survival_columns.durations if column not in self._survival_columns.events),
            self._survival_columns.durations[0] if self._survival_columns.durations else "",
        )
        self._duration_combo.set_columns(self._survival_columns.durations, select=first_duration)
        self._duration_label = QLabel(self.tr("Duration"), self)
        target_form.addRow(self._duration_label, self._duration_combo)
        self._event_combo = ColumnComboBox(self)
        first_event = next((column for column in self._survival_columns.events if column != first_duration), "")
        self._event_combo.set_columns(self._survival_columns.events, select=first_event)
        self._event_label = QLabel(self.tr("Event (1 = event; 0 = censored)"), self)
        target_form.addRow(self._event_label, self._event_combo)
        layout.addLayout(target_form)
        self._target_notice = QLabel(self)
        self._target_notice.setWordWrap(True)
        layout.addWidget(self._target_notice)

        layout.addWidget(self._build_predictors_group(result))

        self._sync_target_item()
        self._update_cox_controls()
        self._update_target_notice()
        self._update_apply_state()

        # Connected only after the initial population above, so setting up
        # the default selection never emits a spurious first signal.
        self._model_combo.currentIndexChanged.connect(self._on_model_changed)
        self._target_combo.currentTextChanged.connect(self._on_target_changed)
        self._duration_combo.currentTextChanged.connect(self._on_duration_changed)
        self._event_combo.currentTextChanged.connect(self._on_event_changed)
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
        """Update pending target exclusions without requesting a fit."""
        model = self.current_model()
        self._configuration_revision += 1
        self._targets_by_model[model] = self.current_target()
        self._sync_target_item()
        self._update_apply_state()
        self.configuration_changed.emit()

    def _on_model_changed(self, _index: int) -> None:
        """Update pending model choices and exclusions without requesting a fit."""
        model = self.current_model()
        self._configuration_revision += 1
        self._update_cox_controls()
        if model is RegressionModel.COX:
            self._update_cox_choices()
            self._sync_target_item()
            self._update_target_notice()
            self._update_apply_state()
            self.configuration_changed.emit()
            return
        targets = self._available_targets(model)
        selected = self._targets_by_model.get(model, "")
        self._target_combo.blockSignals(True)
        try:
            self._target_combo.set_columns(targets, select=selected)
        finally:
            self._target_combo.blockSignals(False)
        self._targets_by_model[model] = self.current_target()
        self._sync_target_item()
        self._update_target_notice()
        self._update_apply_state()
        self.configuration_changed.emit()

    def _available_targets(self, model: RegressionModel) -> tuple[str, ...]:
        """Return the suitable outcome columns for `model`."""
        if model is RegressionModel.LINEAR:
            return self._linear_targets
        if model is RegressionModel.LOGISTIC:
            return self._generalized_targets.binary
        if model is RegressionModel.COX:
            return ()
        return self._generalized_targets.count

    def _update_cox_controls(self) -> None:
        """Show survival outcomes only while Cox regression is selected."""
        is_cox = self.current_model() is RegressionModel.COX
        self._target_label.setVisible(not is_cox)
        self._target_combo.setVisible(not is_cox)
        self._duration_label.setVisible(is_cox)
        self._duration_combo.setVisible(is_cox)
        self._event_label.setVisible(is_cox)
        self._event_combo.setVisible(is_cox)

    def _update_cox_choices(self) -> None:
        """Keep duration and event selections distinct when they share columns."""
        duration = self.current_duration()
        event = self.current_event()
        duration_choices = tuple(column for column in self._survival_columns.durations if column != event)
        event_choices = tuple(column for column in self._survival_columns.events if column != duration)
        self._duration_combo.blockSignals(True)
        self._event_combo.blockSignals(True)
        try:
            self._duration_combo.set_columns(duration_choices, select=duration)
            self._event_combo.set_columns(event_choices, select=event)
        finally:
            self._duration_combo.blockSignals(False)
            self._event_combo.blockSignals(False)

    def _on_duration_changed(self, _text: str) -> None:
        """Update Cox outcome exclusions without fitting before Apply."""
        self._configuration_revision += 1
        self._update_cox_choices()
        self._sync_target_item()
        self._update_target_notice()
        self._update_apply_state()
        self.configuration_changed.emit()

    def _on_event_changed(self, _text: str) -> None:
        """Update Cox outcome exclusions without fitting before Apply."""
        self._configuration_revision += 1
        self._update_cox_choices()
        self._sync_target_item()
        self._update_target_notice()
        self._update_apply_state()
        self.configuration_changed.emit()

    def _update_target_notice(self) -> None:
        """Explain when the selected model has no eligible target columns."""
        if self.current_model() is RegressionModel.COX:
            has_duration = bool(self._duration_combo.eligible_columns())
            has_event = bool(self._event_combo.eligible_columns())
            has_distinct_pair = any(
                duration != event
                for duration in self._survival_columns.durations
                for event in self._survival_columns.events
            )
            available = has_duration and has_event and has_distinct_pair
            message = (
                "" if available else self.tr("Cox regression needs distinct numeric duration and binary event columns.")
            )
            self._target_notice.setText(message)
            self._duration_combo.setEnabled(has_duration and has_distinct_pair)
            self._event_combo.setEnabled(has_event and has_distinct_pair)
            return
        available = bool(self._available_targets(self.current_model()))
        message = "" if available else self.tr("No eligible target columns are available for this model.")
        self._target_notice.setText(message)
        self._target_combo.setEnabled(available)
        self._duration_combo.setEnabled(True)
        self._event_combo.setEnabled(True)

    def _sync_target_item(self) -> None:
        """Make the target's predictor item disabled and unchecked, and re-enable the others."""
        outcomes = set(self._outcome_columns())
        tooltip = (
            self.tr("This column is an outcome and cannot be a predictor.")
            if self.current_model() is RegressionModel.COX
            else self.tr("This column is the target.")
        )
        self._predictor_list.blockSignals(True)
        try:
            for item in self._checkable_items():
                if not item.data(_ELIGIBLE_ROLE):
                    continue
                is_outcome = item.data(_COLUMN_ROLE) in outcomes
                if is_outcome:
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
        """Invalidate the displayed fit after a pending predictor edit."""
        self._configuration_revision += 1
        self._update_apply_state()
        self.configuration_changed.emit()

    def _set_all_predictors_checked(self, *, checked: bool) -> None:
        """Set every enabled predictor to the same pending check state."""
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        changed = False
        self._predictor_list.blockSignals(True)
        try:
            for item in self._checkable_items():
                if (
                    item.data(_ELIGIBLE_ROLE)
                    and item.flags() & Qt.ItemFlag.ItemIsEnabled
                    and item.checkState() != state
                ):
                    item.setCheckState(state)
                    changed = True
        finally:
            self._predictor_list.blockSignals(False)
        self._update_apply_state()
        if changed:
            self._configuration_revision += 1
            self.configuration_changed.emit()

    def _on_apply_clicked(self) -> None:
        """Capture the complete pending configuration and request one refit."""
        checked = self.checked_predictors()
        if not self._has_valid_outcomes() or not self._is_valid_selection(checked):
            return
        self._applied_predictors = checked
        self._applied_model = self.current_model()
        self._applied_target = (
            self.current_duration() if self._applied_model is RegressionModel.COX else self.current_target()
        )
        self._applied_event = self.current_event() if self._applied_model is RegressionModel.COX else ""
        self._configuration_revision += 1
        self._update_apply_state()
        self.model_requested.emit()

    def _update_apply_state(self) -> None:
        """Enable Apply only for a valid selection and explain the count."""
        checked = self.checked_predictors()
        self._apply_button.setEnabled(self._has_valid_outcomes() and self._is_valid_selection(checked))
        self._selection_label.setText(self._selection_text(len(checked)))

    def _has_valid_outcomes(self) -> bool:
        """Return whether the selected model has its required outcome columns."""
        if self.current_model() is RegressionModel.COX:
            return bool(
                self.current_duration() and self.current_event() and self.current_duration() != self.current_event()
            )
        return bool(self.current_target())

    def _outcome_columns(self) -> tuple[str, ...]:
        """Return the columns that cannot be used as predictors."""
        if self.current_model() is RegressionModel.COX:
            return tuple(column for column in (self.current_duration(), self.current_event()) if column)
        target = self.current_target()
        return (target,) if target else ()

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

    def current_model(self) -> RegressionModel:
        """Return the selected regression model."""
        return RegressionModel(self._model_combo.currentData())

    def model_configuration(self) -> tuple[RegressionModel, str, tuple[str, ...]]:
        """Return the model, target and applied predictors that determine the fit."""
        return self._applied_model, self._applied_target, self._applied_predictors

    def applied_event(self) -> str:
        """Return the Cox event column captured by the most recent Apply."""
        return self._applied_event

    def current_duration(self) -> str:
        """Return the selected Cox duration column, or ``""`` if none is available."""
        return self._duration_combo.current_column()

    def current_event(self) -> str:
        """Return the selected Cox event column, or ``""`` if none is available."""
        return self._event_combo.current_column()

    def configuration_revision(self) -> int:
        """Return a generation advanced by every configuration edit and Apply."""
        return self._configuration_revision
