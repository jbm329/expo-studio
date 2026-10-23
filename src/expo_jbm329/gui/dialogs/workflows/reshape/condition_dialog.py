"""Multi-rule condition builder, independent of DataFrames and worker jobs."""

from __future__ import annotations

import html
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QStandardItemModel
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from expo_jbm329.gui.dialogs.service.common.localization import localize_dialog_buttons
from expo_jbm329.gui.dialogs.workflows.reshape.condition_value_picker import ConditionValuePicker
from expo_jbm329.services.data_operations.reshape_conditions import (
    ConditionColumn,
    ConditionError,
    ConditionGroup,
    ConditionMatch,
    ConditionOperator,
    ConditionRule,
    format_condition,
)

if TYPE_CHECKING:
    from collections.abc import Sequence


class ConditionRuleWidget(QWidget):
    """One column/operator/value rule, with stable identity across removals."""

    changed = pyqtSignal()

    def __init__(self, columns: Sequence[ConditionColumn], parent: QWidget) -> None:
        """Build one initially incomplete rule."""
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.column = QComboBox(self)
        self.column.addItem(self.tr("Select column"), None)
        for column in columns:
            self.column.addItem(column.name, column)
            index = self.column.count() - 1
            self.column.setItemData(index, f"<qt>{html.escape(column.name)}</qt>", Qt.ItemDataRole.ToolTipRole)
            if not column.available:
                model = self.column.model()
                if isinstance(model, QStandardItemModel):
                    item = model.item(index)
                    if item is not None:
                        item.setEnabled(False)
                self.column.setItemData(
                    index, self.tr("Ambiguous column name. Rename this column first."), Qt.ItemDataRole.ToolTipRole
                )
        self.column.setAccessibleName(self.tr("Column"))
        self.operator = QComboBox(self)
        labels = (
            self.tr("Equal to"),
            self.tr("Not equal to"),
            self.tr("In"),
            self.tr("Not in"),
            self.tr("Greater than"),
            self.tr("Greater than or equal to"),
            self.tr("Less than"),
            self.tr("Less than or equal to"),
            self.tr("Is missing"),
            self.tr("Is not missing"),
        )
        for operator, label in zip(ConditionOperator, labels, strict=True):
            self.operator.addItem(label, operator)
        self.operator.setAccessibleName(self.tr("Operator"))
        self.picker = ConditionValuePicker(self)
        self.remove_button = QPushButton(self.tr("Remove rule"), self)
        self.remove_button.setAutoDefault(False)
        layout.addWidget(self.column, 2)
        layout.addWidget(self.operator, 2)
        layout.addWidget(self.picker, 3)
        layout.addWidget(self.remove_button)
        self.column.currentIndexChanged.connect(self._configure)
        self.operator.currentIndexChanged.connect(self._configure)
        self.picker.changed.connect(self.changed)
        self._configure()

    def selected_operator(self) -> ConditionOperator:
        """Return the stable operator token, never translated label text."""
        value = self.operator.currentData()
        if not isinstance(value, ConditionOperator):
            message = "Condition operator is missing."
            raise TypeError(message)
        return value

    def build_rule(self) -> ConditionRule | None:
        """Return a complete typed rule, or None for an unfinished UI row."""
        column = self.column.currentData()
        if not isinstance(column, ConditionColumn) or not column.available:
            return None
        operator = self.selected_operator()
        if not operator.is_null_test and (self.picker.loading or self.picker.error):
            return None
        rule = ConditionRule(column, operator, () if operator.is_null_test else self.picker.selected_values())
        try:
            format_condition(ConditionGroup((rule,)))
        except ConditionError:
            return None
        return rule

    def restore(self, rule: ConditionRule) -> None:
        """Restore an applied rule without parsing its generated expression."""
        self.column.setCurrentIndex(self.column.findData(rule.column))
        self.operator.setCurrentIndex(self.operator.findData(rule.operator))
        self._configure()
        self.picker.configure(
            rule.column.position,
            multiple=rule.operator.is_membership,
            enabled=not rule.operator.is_null_test,
            values=rule.operands,
        )

    def _configure(self) -> None:
        column = self.column.currentData()
        operator = self.selected_operator()
        position = column.position if isinstance(column, ConditionColumn) and column.available else None
        self.picker.configure(position, multiple=operator.is_membership, enabled=not operator.is_null_test)
        self.column.setToolTip(f"<qt>{html.escape(self.column.currentText())}</qt>")
        self.changed.emit()


class ConditionDialog(QDialog):
    """Edit builder rules and emit requests for external asynchronous loading."""

    page_requested = pyqtSignal(object, object)  # picker, ValuePageRequest
    request_invalidated = pyqtSignal(object)  # picker

    def __init__(
        self,
        *,
        parent: QWidget,
        columns: Sequence[ConditionColumn],
        initial: ConditionGroup | None = None,
        replaces_manual_text: bool = False,
    ) -> None:
        """Initialize the builder from metadata and optional applied state."""
        super().__init__(parent)
        self.setWindowTitle(self.tr("Build condition"))
        self.resize(750, 500)
        self._columns = tuple(columns)
        self.applied_group: ConditionGroup | None = None
        self.rules: list[ConditionRuleWidget] = []
        root = QVBoxLayout(self)
        if replaces_manual_text:
            warning = QLabel(
                self.tr("This text was edited manually. Apply will replace it. Cancel keeps the original text."), self
            )
            warning.setWordWrap(True)
            root.addWidget(warning)
        if any(not column.available for column in columns):
            warning = QLabel(
                self.tr("Ambiguous column names are unavailable. Rename them before building conditions."), self
            )
            warning.setWordWrap(True)
            root.addWidget(warning)
        self.match = QComboBox(self)
        self.match.addItem(self.tr("All rules (AND)"), ConditionMatch.ALL)
        self.match.addItem(self.tr("Any rule (OR)"), ConditionMatch.ANY)
        root.addWidget(self.match)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        self._rule_panel = QWidget(scroll)
        self._rule_layout = QVBoxLayout(self._rule_panel)
        self._rule_layout.addStretch()
        scroll.setWidget(self._rule_panel)
        root.addWidget(scroll, 1)
        self.add_button = QPushButton(self.tr("Add rule"), self)
        self.add_button.setAutoDefault(False)
        root.addWidget(self.add_button)
        self.validation = QLabel(self)
        self.validation.setWordWrap(True)
        root.addWidget(self.validation)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel, self)
        self.apply_button = QPushButton(self.tr("Apply"), self)
        buttons.addButton(self.apply_button, QDialogButtonBox.ButtonRole.AcceptRole)
        localize_dialog_buttons(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self.add_button.clicked.connect(self.add_rule)
        self.match.currentIndexChanged.connect(self._validate)
        self.finished.connect(self._invalidate_all)
        if initial is not None:
            self.match.setCurrentIndex(self.match.findData(initial.match))
            for rule in initial.rules:
                self.add_rule().restore(rule)
        else:
            self.add_rule()
        self._validate()

    def add_rule(self) -> ConditionRuleWidget:
        """Append an independent rule and connect its request signals."""
        rule = ConditionRuleWidget(self._columns, self._rule_panel)
        self.rules.append(rule)
        self._rule_layout.insertWidget(self._rule_layout.count() - 1, rule)

        def request_page(request: object) -> None:
            self.page_requested.emit(rule.picker, request)

        rule.picker.page_requested.connect(request_page)
        rule.picker.invalidated.connect(lambda: self.request_invalidated.emit(rule.picker))
        rule.changed.connect(self._validate)
        rule.remove_button.clicked.connect(lambda: self.remove_rule(rule))
        self._validate()
        return rule

    def remove_rule(self, rule: ConditionRuleWidget) -> None:
        """Remove a rule and invalidate its outstanding requests immediately."""
        rule.picker.invalidate()
        self.rules.remove(rule)
        self._rule_layout.removeWidget(rule)
        rule.deleteLater()
        self._validate()

    def build_group(self) -> ConditionGroup | None:
        """Capture complete rules without accepting incomplete/loading state."""
        rules: list[ConditionRule] = []
        for widget in self.rules:
            rule = widget.build_rule()
            if rule is None:
                return None
            rules.append(rule)
        mode = self.match.currentData()
        if not rules or not isinstance(mode, ConditionMatch):
            return None
        return ConditionGroup(tuple(rules), mode)

    def accept(self) -> None:
        """Capture valid state before closing invalidates pending requests."""
        group = self.build_group()
        if group is None:
            self._validate()
            return
        self.applied_group = group
        super().accept()

    def _validate(self) -> None:
        group = self.build_group()
        self.apply_button.setEnabled(group is not None)
        self.validation.setText("" if group is not None else self.tr("Complete every rule before applying."))

    def _invalidate_all(self) -> None:
        for rule in self.rules:
            rule.picker.invalidate()
