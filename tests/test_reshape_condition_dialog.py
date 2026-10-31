"""Condition builder widget behavior with deterministic page delivery."""

from __future__ import annotations

import pytest
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QLabel, QPushButton, QWidget

from expo_jbm329.gui.dialogs.workflows.reshape.condition_dialog import ConditionDialog
from expo_jbm329.gui.dialogs.workflows.reshape.condition_editor import ConditionEditor
from expo_jbm329.gui.dialogs.workflows.reshape.condition_value_picker import ConditionValuePicker
from expo_jbm329.gui.dialogs.workflows.reshape.reshape_dialog import ReshapeDialog
from expo_jbm329.services.data_operations.reshape_condition_values import ValuePage, ValuePageRequest
from expo_jbm329.services.data_operations.reshape_conditions import (
    ConditionColumn,
    ConditionGroup,
    ConditionLiteralType,
    ConditionMatch,
    ConditionOperator,
    ConditionRule,
    ConditionValue,
)
from expo_jbm329.utils.dataset_ref import DatasetRef


@pytest.mark.parametrize(
    ("literal_type", "selected", "entry"),
    [
        (ConditionLiteralType.NUMBER, ConditionValue("decimal", "1.00"), ConditionValue("float", "1.0")),
        (ConditionLiteralType.QUOTED, ConditionValue("string", "1"), ConditionValue("integer", "1")),
        (ConditionLiteralType.QUOTED, ConditionValue("string", "2026-10-31"), ConditionValue("date", "2026-10-31")),
    ],
)
def test_imported_picker_selection_matches_page_identity_and_can_be_unchecked(literal_type, selected, entry):
    parent = QWidget()
    picker = ConditionValuePicker(parent)
    picker.configure(0, multiple=True, enabled=True, values=(selected,), literal_type=literal_type)
    picker._timer.stop()
    picker.receive_page(ValuePage((), True))
    assert picker.selected_values() == (selected,)
    picker.receive_page(ValuePage((entry,), False))
    assert picker.values_list.item(0).checkState() == Qt.CheckState.Checked
    assert picker.selected_values() == (selected,)
    picker.values_list.item(0).setCheckState(Qt.CheckState.Unchecked)
    assert picker.selected_values() == ()
    picker.values_list.item(0).setCheckState(Qt.CheckState.Checked)
    assert picker.selected_values() == (entry,)
    parent.close()


def test_quoted_picker_values_do_not_use_numeric_equivalence():
    parent = QWidget()
    picker = ConditionValuePicker(parent)
    selected = ConditionValue("string", "1.00")
    picker.configure(0, multiple=True, enabled=True, values=(selected,))
    picker._timer.stop()
    picker.receive_page(ValuePage((ConditionValue("float", "1.0"),), False))
    assert picker.values_list.item(0).checkState() == Qt.CheckState.Unchecked
    assert picker.selected_values() == (selected,)
    parent.close()


def test_picker_uses_standard_button_height_and_opens_value_popup(qt_app) -> None:
    parent = QWidget()
    dialog = ConditionDialog(parent=parent, columns=(ConditionColumn(0, "a", True),))
    rule = dialog.rules[0]
    rule.column.setCurrentIndex(1)
    rule.picker._timer.stop()
    rule.picker.receive_page(ValuePage((ConditionValue("string", "x"),), False))
    dialog.show()
    qt_app.processEvents()
    button = rule.picker.button
    assert isinstance(button, QPushButton)
    assert not button.autoDefault()
    assert button.height() == rule.remove_button.height()
    menu = button.menu()
    assert menu is not None
    opened: list[bool] = []

    def select_value() -> None:
        opened.append(menu.isVisible())
        rule.picker.values_list.item(0).setCheckState(Qt.CheckState.Checked)
        menu.close()

    QTimer.singleShot(0, select_value)
    button.showMenu()
    qt_app.processEvents()
    assert opened == [True]
    assert rule.picker.selected_values() == (ConditionValue("string", "x"),)
    assert dialog.result() == 0
    dialog.reject()


def test_rules_validation_null_operators_and_apply_capture() -> None:
    parent = QWidget()
    dialog = ConditionDialog(parent=parent, columns=(ConditionColumn(0, "a", True),))
    assert not dialog.apply_button.isEnabled()
    dialog.accept()
    assert dialog.applied_group is None
    first = dialog.rules[0]
    assert first.operator.count() == 10
    first.column.setCurrentIndex(1)
    assert first.picker.loading
    first.operator.setCurrentIndex(first.operator.findData(ConditionOperator.IS_NULL))
    assert not first.picker.isEnabled()
    assert dialog.apply_button.isEnabled()
    second = dialog.add_rule()
    assert not dialog.apply_button.isEnabled()
    second.column.setCurrentIndex(1)
    second.operator.setCurrentIndex(second.operator.findData(ConditionOperator.IN))
    second.picker.receive_page(ValuePage((ConditionValue("string", "x"),), False))
    second.picker.values_list.item(0).setCheckState(Qt.CheckState.Checked)
    assert dialog.apply_button.isEnabled()
    dialog.match.setCurrentIndex(dialog.match.findData(ConditionMatch.ANY))
    dialog.accept()
    assert dialog.applied_group == ConditionGroup(
        (
            ConditionRule(ConditionColumn(0, "a", True), ConditionOperator.IS_NULL),
            ConditionRule(ConditionColumn(0, "a", True), ConditionOperator.IN, (ConditionValue("string", "x"),)),
        ),
        ConditionMatch.ANY,
    )


def test_picker_retains_selections_across_pages_and_search() -> None:
    parent = QWidget()
    picker = ConditionValuePicker(parent)
    picker.configure(0, multiple=True, enabled=True)
    requests: list[object] = []
    picker.page_requested.connect(requests.append)
    picker.receive_page(ValuePage((ConditionValue("string", ""), ConditionValue("string", "a")), True))
    picker.values_list.item(0).setCheckState(Qt.CheckState.Checked)
    picker.next_button.click()
    picker._timer.stop()
    picker._timer.timeout.emit()
    assert requests[-1] == ValuePageRequest(0, page=1)
    picker.receive_page(ValuePage((ConditionValue("string", "b"),), False))
    picker.values_list.item(0).setCheckState(Qt.CheckState.Checked)
    generation = picker.generation
    picker.search.setText("other")
    assert picker.generation > generation
    assert picker.loading
    assert picker.page == 0
    assert picker.selected_values() == (ConditionValue("string", ""), ConditionValue("string", "b"))
    picker.receive_page(ValuePage((), False))
    picker.selected_list.item(0).setSelected(True)
    picker.remove_button.click()
    assert picker.selected_values() == (ConditionValue("string", "b"),)
    picker.configure(0, multiple=False, enabled=True)
    assert picker.selected_values() == (ConditionValue("string", "b"),)
    picker.configure(1, multiple=False, enabled=True)
    assert picker.selected_values() == ()
    assert picker.search.text() == ""
    picker.invalidate()


def test_single_selection_and_multi_to_single_reset() -> None:
    parent = QWidget()
    picker = ConditionValuePicker(parent)
    picker.configure(0, multiple=True, enabled=True)
    picker.receive_page(ValuePage((ConditionValue("integer", "1"), ConditionValue("integer", "2")), False))
    picker.values_list.item(0).setCheckState(Qt.CheckState.Checked)
    picker.values_list.item(1).setCheckState(Qt.CheckState.Checked)
    picker.configure(0, multiple=False, enabled=True)
    assert picker.selected_values() == ()
    picker.receive_page(ValuePage((ConditionValue("integer", "1"), ConditionValue("integer", "2")), False))
    picker.values_list.item(0).setCheckState(Qt.CheckState.Checked)
    picker.values_list.item(1).setCheckState(Qt.CheckState.Checked)
    assert picker.selected_values() == (ConditionValue("integer", "2"),)
    assert picker.values_list.item(0).checkState() == Qt.CheckState.Unchecked
    picker.invalidate()


def test_editor_restore_manual_warning_cancel_and_rule_removal() -> None:
    parent = QWidget()
    editor = ConditionEditor(parent)
    column = ConditionColumn(0, "a", True)
    group = ConditionGroup((ConditionRule(column, ConditionOperator.IS_NOT_NULL),))
    editor.apply_group(group)
    assert editor.restorable_group() == group
    dialog = ConditionDialog(parent=parent, columns=(column,), initial=editor.restorable_group())
    assert dialog.build_group() == group
    removed = dialog.add_rule()
    invalidations: list[object] = []
    dialog.request_invalidated.connect(invalidations.append)
    dialog.remove_rule(removed)
    assert invalidations == [removed.picker]
    assert dialog.build_group() == group
    dialog.reject()
    assert editor.text.text() == "[a] IS NOT NULL"
    editor.text.setText("a > 1")
    assert editor.restorable_group() is None
    fresh = ConditionDialog(parent=parent, columns=(column,), replaces_manual_text=True)
    assert any("Cancel keeps" in label.text() for label in fresh.findChildren(QLabel))
    fresh.reject()
    assert editor.text.text() == "a > 1"


def test_ambiguous_column_is_disabled_and_failed_values_block_apply() -> None:
    parent = QWidget()
    dialog = ConditionDialog(parent=parent, columns=(ConditionColumn(0, "a", False), ConditionColumn(1, "b", True)))
    rule = dialog.rules[0]
    assert not rule.column.model().item(1).isEnabled()
    rule.column.setCurrentIndex(2)
    rule.picker.receive_page(ValuePage((ConditionValue("string", "x"),), False))
    rule.picker.values_list.item(0).setCheckState(Qt.CheckState.Checked)
    assert dialog.apply_button.isEnabled()
    rule.picker.show_error("Failure")
    assert not dialog.apply_button.isEnabled()
    assert rule.picker.status.text() == "Failure"
    dialog.reject()


def test_literal_names_and_value_tooltips_do_not_interpret_markup() -> None:
    parent = QWidget()
    dialog = ConditionDialog(parent=parent, columns=(ConditionColumn(0, "<b>Name</b>", True),))
    rule = dialog.rules[0]
    rule.column.setCurrentIndex(1)
    assert rule.column.currentText() == "<b>Name</b>"
    assert rule.column.toolTip() == "<qt>&lt;b&gt;Name&lt;/b&gt;</qt>"
    rule.picker.receive_page(ValuePage((ConditionValue("string", "<b>value</b>"),), False))
    item = rule.picker.values_list.item(0)
    assert item.text() == "<b>value</b>"
    assert item.toolTip() == "<qt>&lt;b&gt;value&lt;/b&gt;</qt>"
    item.setCheckState(Qt.CheckState.Checked)
    assert rule.picker.selected_list.item(0).toolTip() == item.toolTip()
    dialog.reject()


def test_metric_button_follows_editor_identity_after_row_deletion_and_resize(qt_app) -> None:
    dialog = ReshapeDialog(
        parent=None,
        source_dataset=DatasetRef("source", "Source", 2, 1),
        source_columns=("a",),
        source_dtypes=("int64",),
        numeric_column_positions=(0,),
        datetime_column_positions=(),
    )
    dialog.metrics.item(0, 0).setText("First")
    dialog.metrics.cellWidget(0, 2).value.setCurrentIndex(1)
    dialog.add_metric_button.click()
    dialog.metrics.item(1, 0).setText("Second")
    dialog.metrics.cellWidget(1, 2).value.setCurrentIndex(1)
    editor = dialog.metrics.cellWidget(1, 3)
    assert isinstance(editor, ConditionEditor)
    group = ConditionGroup((ConditionRule(ConditionColumn(0, "a", True), ConditionOperator.IS_NULL),))
    editor.apply_group(group)
    requests: list[object] = []
    dialog.condition_requested.connect(requests.append)
    dialog.metrics.selectRow(0)
    dialog.remove_metric_button.click()
    assert dialog.metrics.cellWidget(0, 3) is editor
    editor.button.click()
    assert requests == [editor]
    assert editor.restorable_group() == group
    dialog.show()
    for width in (1280, 1500):
        dialog.resize(width, dialog.height())
        qt_app.processEvents()
        assert editor.button.geometry().right() == editor.width() - 1
        assert editor.text.geometry().right() < editor.button.geometry().left()
    assert dialog.apply_button.isEnabled()
    dialog.close()
