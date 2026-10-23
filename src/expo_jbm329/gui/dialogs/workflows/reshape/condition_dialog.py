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
    QVBoxLayout,
    QWidget,
)

from expo_jbm329.gui.dialogs.service.common.localization import localize_dialog_buttons
from expo_jbm329.gui.dialogs.workflows.reshape.condition_tree_widget import ConditionTreeWidget
from expo_jbm329.gui.dialogs.workflows.reshape.condition_value_picker import ConditionValuePicker
from expo_jbm329.services.data_operations.reshape_condition_tree import ConditionNode
from expo_jbm329.services.data_operations.reshape_conditions import (
    ConditionColumn,
    ConditionError,
    ConditionGroup,
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
        index = next((index for index in range(self.column.count()) if self.column.itemData(index) == rule.column), -1)
        self.column.setCurrentIndex(index)
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
        self._rule_nodes: dict[str, ConditionRuleWidget] = {}
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
        self.tree = ConditionTreeWidget(self)
        self.match = self.tree.connectors[self.tree.model.root.key]
        guidance = QLabel(
            self.tr(
                "Drag a handle onto a rule to create an AND group. "
                "Drop onto a group to add to it; use row edges to reorder."
            ),
            self,
        )
        guidance.setWordWrap(True)
        root.addWidget(guidance)
        root.addWidget(self.tree, 1)
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
        self.tree.add_requested.connect(self._add_to_group)
        self.tree.changed.connect(self._validate)
        self.finished.connect(self._invalidate_all)
        if initial is not None:
            self.tree.model.root.match = initial.match
            self.match.setCurrentIndex(self.match.findData(initial.match))
            self._restore(initial, self.tree.model.root)
            self.tree.refresh()
        else:
            self.add_rule()
        self._validate()

    def _add_to_group(self, candidate: object) -> None:
        if not isinstance(candidate, ConditionNode):
            message = "A condition rule requires a group destination."
            raise TypeError(message)
        self.add_rule(candidate)

    def _restore(self, group: ConditionGroup, parent: ConditionNode) -> None:
        for child in group.rules:
            if isinstance(child, ConditionGroup):
                node = ConditionNode(child.match)
                parent.children.append(node)
                self._restore(child, node)
            else:
                node = self.tree.model.add_rule(parent)
                self._create_rule(node).restore(child)

    def add_rule(self, parent: ConditionNode | None = None) -> ConditionRuleWidget:
        """Append an independent rule and connect its request signals."""
        node = self.tree.model.add_rule(parent if parent is not None else self.tree.insertion_group())
        rule = self._create_rule(node)
        self.tree.refresh()
        return rule

    def _create_rule(self, node: ConditionNode) -> ConditionRuleWidget:
        rule = ConditionRuleWidget(self._columns, self.tree.panel)
        self.rules.append(rule)
        self._rule_nodes[node.key] = rule
        self.tree.attach_rule(node, rule)

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
        key = next(key for key, editor in self._rule_nodes.items() if editor is rule)
        node = next(node for node in self.tree.model.nodes() if node.key == key)
        self.tree.model.remove_rule(node)
        del self._rule_nodes[key]
        self.tree.refresh()

    def build_group(self) -> ConditionGroup | None:
        """Capture complete rules without accepting incomplete/loading state."""

        def capture(node: ConditionNode) -> ConditionRule | ConditionGroup | None:
            if node.match is None:
                return self._rule_nodes[node.key].build_rule()
            children: list[ConditionRule | ConditionGroup] = []
            for child in node.children:
                value = capture(child)
                if value is None:
                    return None
                children.append(value)
            return ConditionGroup(tuple(children), node.match) if children else None

        group = capture(self.tree.model.root)
        return group if isinstance(group, ConditionGroup) else None

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
        self.tree.stop_drag_scroll()
        for rule in self.rules:
            rule.picker.invalidate()
