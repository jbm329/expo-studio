"""Nested tree interactions through Qt events and keyboard-accessible actions."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QEvent, QMimeData, QPoint, QPointF, Qt
from PyQt6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDragMoveEvent, QDropEvent, QMouseEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QPushButton, QWidget

from expo_jbm329.gui.dialogs.workflows.reshape import condition_tree_widget as module
from expo_jbm329.gui.dialogs.workflows.reshape.condition_dialog import ConditionDialog
from expo_jbm329.gui.dialogs.workflows.reshape.condition_editor import ConditionEditor
from expo_jbm329.services.data_operations.reshape_condition_tree import ConditionDrop
from expo_jbm329.services.data_operations.reshape_condition_values import ValuePage
from expo_jbm329.services.data_operations.reshape_conditions import (
    ConditionColumn,
    ConditionGroup,
    ConditionMatch,
    ConditionOperator,
    ConditionRule,
    ConditionValue,
    format_condition,
)


@pytest.fixture
def dialog(qt_app):
    parent = QWidget()
    builder = ConditionDialog(parent=parent, columns=(ConditionColumn(0, "a", True),))
    for _ in range(2):
        builder.add_rule()
    for editor in builder.rules:
        editor.column.setCurrentIndex(1)
        editor.operator.setCurrentIndex(editor.operator.findData(ConditionOperator.IS_NULL))
    builder.resize(1050, 600)
    builder.show()
    qt_app.processEvents()
    yield builder
    builder.reject()


def send_drop(tree, source, target, placement=ConditionDrop.INTO):
    row = tree.rows[target.key]
    if placement == ConditionDrop.BEFORE:
        point = QPoint(row.width() - 5, 1)
    elif placement == ConditionDrop.AFTER:
        point = QPoint(row.width() - 5, row.height() - 1)
    else:
        point = QPoint(row.width() - 5, row.height() // 2)
    mime = tree.mime_data(source)
    enter = QDragEnterEvent(
        point, Qt.DropAction.MoveAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier
    )
    QApplication.sendEvent(row, enter)
    if not enter.isAccepted():
        return False
    move = QDragMoveEvent(
        point, Qt.DropAction.MoveAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier
    )
    QApplication.sendEvent(row, move)
    assert move.isAccepted()
    assert row.indicator == placement
    drop = QDropEvent(
        QPointF(point), Qt.DropAction.MoveAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier
    )
    QApplication.sendEvent(row, drop)
    return drop.isAccepted()


def test_rule_drop_groups_and_group_drop_reorders_without_replacing_editors(dialog, qt_app):
    tree = dialog.tree
    first, second, third = tree.model.root.children
    original = tuple(dialog.rules)
    rows = dict(tree.rows)
    generations = [editor.picker.generation for editor in original]
    assert send_drop(tree, second, first)
    group = tree.model.parent(first)
    assert group.children == [first, second]
    assert group.match == ConditionMatch.ALL
    assert tree.rows[first.key] is rows[first.key]
    assert tree.rows[first.key].level == 2
    assert tree.rows[third.key].level == 1
    assert send_drop(tree, group, third, ConditionDrop.AFTER)
    assert tree.model.root.children == [third, group]
    assert tuple(dialog.rules) == original
    assert [editor.picker.generation for editor in original] == generations
    qt_app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert all(not sip.isdeleted(editor) for editor in original)
    assert all(not sip.isdeleted(editor.picker) for editor in original)
    assert dialog.apply_button.isEnabled()


def test_group_connectors_restore_and_apply_nested_state(dialog):
    tree = dialog.tree
    first, second, third = tree.model.root.children
    tree.move_node(second, first, ConditionDrop.INTO)
    nested = tree.model.parent(first)
    tree.connectors[nested.key].setCurrentIndex(tree.connectors[nested.key].findData(ConditionMatch.ANY))
    dialog.match.setCurrentIndex(dialog.match.findData(ConditionMatch.ALL))
    captured = dialog.build_group()
    assert captured == ConditionGroup((
        ConditionGroup(
            (
                ConditionRule(ConditionColumn(0, "a", True), ConditionOperator.IS_NULL),
                ConditionRule(ConditionColumn(0, "a", True), ConditionOperator.IS_NULL),
            ),
            ConditionMatch.ANY,
        ),
        ConditionRule(ConditionColumn(0, "a", True), ConditionOperator.IS_NULL),
    ))
    assert format_condition(captured) == "(([a] IS NULL OR [a] IS NULL) AND [a] IS NULL)"
    dialog.accept()
    assert dialog.applied_group == captured
    editor = ConditionEditor(dialog)
    editor.apply_group(captured)
    assert editor.restorable_group() == captured
    reopened = ConditionDialog(
        parent=dialog, columns=(ConditionColumn(0, "a", True),), initial=editor.restorable_group()
    )
    assert reopened.build_group() == captured, [
        (widget.column.currentIndex(), widget.operator.currentData(), widget.build_rule()) for widget in reopened.rules
    ]
    reopened.tree.connectors[reopened.tree.model.root.children[0].key].setCurrentIndex(0)
    reopened.reject()
    assert editor.restorable_group() == captured


def test_context_actions_group_ungroup_outdent_and_root_guards(dialog):
    tree = dialog.tree
    first, second, third = tree.model.root.children
    root_menu = tree.action_menu(tree.model.root)
    assert all(not action.isEnabled() for action in root_menu.actions())
    root_menu.deleteLater()
    menu = tree.action_menu(second)
    actions = {action.data(): action for action in menu.actions()}
    assert not actions["outdent"].isEnabled()
    actions["indent"].trigger()
    group = tree.model.parent(first)
    assert group.children == [first, second]
    menu.deleteLater()
    tree.perform_action(second, "outdent")
    assert tree.model.root.children == [first, second, third]
    tree.perform_action(third, "up")
    assert tree.model.root.children == [first, third, second]
    tree.perform_action(third, "down")
    assert tree.model.root.children == [first, second, third]
    tree.perform_action(second, "indent")
    group = tree.model.parent(first)
    menu = tree.action_menu(group)
    next(action for action in menu.actions() if action.data() == "ungroup").trigger()
    assert tree.model.root.children == [first, second, third]
    menu.deleteLater()


def test_group_into_group_then_add_remove_and_simplify(dialog, qt_app):
    tree = dialog.tree
    first, second, third = tree.model.root.children
    fourth_editor = dialog.add_rule()
    fourth = tree.model.root.children[-1]
    tree.move_node(second, first, ConditionDrop.INTO)
    left = tree.model.parent(first)
    tree.move_node(fourth, third, ConditionDrop.INTO)
    right = tree.model.parent(third)
    assert send_drop(tree, right, left)
    assert left.children == [first, second, right]
    tree.select(right)
    added = dialog.add_rule()
    assert len(right.children) == 3
    dialog.remove_rule(added)
    assert len(right.children) == 2
    surviving_row = tree.rows[third.key]
    dialog.remove_rule(fourth_editor)
    assert left.children == [first, second, third]
    assert tree.rows[third.key] is surviving_row
    qt_app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert sip.isdeleted(fourth_editor)
    assert right.key not in tree.rows
    assert not sip.isdeleted(dialog.rules[2])


def test_rejected_external_self_and_descendant_drops_leave_tree_unchanged(dialog):
    tree = dialog.tree
    first, second, _third = tree.model.root.children
    assert not send_drop(tree, first, first)
    tree.move_node(second, first, ConditionDrop.INTO)
    group = tree.model.parent(first)
    snapshot = tree.model.nodes()
    assert not send_drop(tree, group, first)
    row = tree.rows[first.key]
    mime = QMimeData()
    mime.setText("external")
    event = QDragEnterEvent(
        QPoint(10, 10), Qt.DropAction.MoveAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier
    )
    QApplication.sendEvent(row, event)
    assert not event.isAccepted()
    assert tree.model.nodes() == snapshot


def test_drag_leave_and_canceled_drag_do_not_change_structure(dialog, monkeypatch):
    tree = dialog.tree
    first, second, _third = tree.model.root.children
    row = tree.rows[first.key]
    mime = tree.mime_data(second)
    event = QDragEnterEvent(
        QPoint(row.width() - 5, row.height() // 2),
        Qt.DropAction.MoveAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(row, event)
    assert row.indicator == ConditionDrop.INTO
    QApplication.sendEvent(row, QDragLeaveEvent())
    assert row.indicator is None
    before = tree.model.nodes()
    drag = MagicMock()
    drag.exec.return_value = Qt.DropAction.IgnoreAction
    drag_class = MagicMock(return_value=drag)
    monkeypatch.setattr(module, "QDrag", drag_class)
    handle = tree.rows[second.key].handle
    QTest.mousePress(handle, Qt.MouseButton.LeftButton, pos=QPoint(2, 2))
    event = QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(100, 2),
        QPointF(100, 2),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(handle, event)
    drag_class.assert_called_once_with(handle)
    drag.exec.assert_called_once_with(Qt.DropAction.MoveAction)
    assert tree.drag_source(drag.setMimeData.call_args.args[0]) is second
    assert tree.model.nodes() == before


def test_editor_click_selects_add_destination_but_does_not_start_drag(dialog, monkeypatch):
    tree = dialog.tree
    first, second, _third = tree.model.root.children
    tree.move_node(second, first, ConditionDrop.INTO)
    group = tree.model.parent(first)
    drag_class = MagicMock()
    monkeypatch.setattr(module, "QDrag", drag_class)
    rule = dialog.rules[0]
    QTest.mouseClick(rule.column, Qt.MouseButton.LeftButton)
    rule.column.hidePopup()
    assert tree.selected is first
    group_button = tree.rows[group.key].findChild(QPushButton)
    assert group_button is not None
    group_button.click()
    assert len(group.children) == 3
    drag_class.assert_not_called()
    assert not dialog.apply_button.isEnabled()


def test_add_rule_buttons_only_belong_to_groups_and_root_survives_empty_tree(dialog):
    tree = dialog.tree
    buttons = [button for button in dialog.findChildren(QPushButton) if button.text() == "Add rule"]
    assert len(buttons) == 1
    assert tree.rows[tree.model.root.key].isAncestorOf(buttons[0])
    for rule in tuple(dialog.rules):
        dialog.remove_rule(rule)
    assert tree.model.root.children == []
    buttons[0].click()
    assert len(dialog.rules) == 1
    assert len(tree.model.root.children) == 1


def test_drag_edge_scrolling_stops_on_leave_and_close(dialog, qt_app):
    tree = dialog.tree
    for _ in range(20):
        dialog.add_rule(tree.model.root)
    qt_app.processEvents()
    viewport = tree.viewport()
    scrollbar = tree.verticalScrollBar()
    assert scrollbar.maximum() > 0
    tree.track_drag(viewport.mapToGlobal(QPoint(10, viewport.height() - 2)))
    assert tree._scroll_timer.isActive()
    tree._scroll_timer.timeout.emit()
    assert scrollbar.value() > 0
    tree.stop_drag_scroll()
    assert not tree._scroll_timer.isActive()
    tree.track_drag(viewport.mapToGlobal(QPoint(10, 1)))
    before = scrollbar.value()
    tree._scroll_timer.timeout.emit()
    assert scrollbar.value() < before
    dialog.reject()
    assert not tree._scroll_timer.isActive()


def test_mockup_with_distinct_rules_restores_and_reorders_exact_expression(qt_app):
    parent = QWidget()
    columns = tuple(ConditionColumn(index, name, True) for index, name in enumerate(("Year", "Klinik", "Yrkesroll")))
    rules = tuple(
        ConditionRule(column, ConditionOperator.EQUAL, (ConditionValue("string", value),))
        for column, value in zip(columns, ("2019", "Medicin", "Läkare"), strict=True)
    )
    initial = ConditionGroup((ConditionGroup(rules[:2]), rules[2]), ConditionMatch.ANY)
    dialog = ConditionDialog(parent=parent, columns=columns, initial=initial)
    for rule_widget in dialog.rules:
        rule_widget.picker._timer.stop()
        rule_widget.picker.receive_page(ValuePage(rule_widget.picker.selected_values(), False))
    assert dialog.build_group() == initial
    tree = dialog.tree
    group, role = tree.model.root.children
    tree.move_node(role, group, ConditionDrop.BEFORE)
    assert format_condition(dialog.build_group()) == (
        "([Yrkesroll] = 'Läkare' OR ([Year] = '2019' AND [Klinik] = 'Medicin'))"
    )
    dialog.accept()
    assert dialog.applied_group == dialog.build_group()
    dialog.deleteLater()
