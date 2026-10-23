"""Condition worker lifecycle tests without threads or timing assumptions."""

from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
from PyQt6 import sip
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QWidget

from expo_jbm329.gui.dialogs.workflows.reshape.condition_editor import ConditionEditor
from expo_jbm329.services.data_operations.reshape_condition_tree import ConditionDrop
from expo_jbm329.services.data_operations.reshape_condition_values import ValuePage, ValuePageRequest
from expo_jbm329.services.data_operations.reshape_conditions import ConditionOperator, ConditionProblem, ConditionValue
from expo_jbm329.workbench.controllers import reshape_condition_controller as module


def test_out_of_order_jobs_search_close_and_cancellation(monkeypatch) -> None:
    parent = QWidget()
    editor = ConditionEditor(parent)
    editor.text.setText("manual")
    source = pd.DataFrame({"a": ["x", "y"]})
    original = source.copy(deep=True)
    async_ops = MagicMock()
    async_ops.job_mgr.get_job_id.side_effect = ["first", "second", "third"]
    callbacks = []

    def execute(dialog):
        rule = dialog.rules[0]
        rule.column.setCurrentIndex(1)
        picker = rule.picker
        picker._timer.stop()
        dialog.page_requested.emit(picker, ValuePageRequest(0))
        first = async_ops.run_operation.call_args.kwargs
        assert first["work"]() == ValuePage((ConditionValue("string", "x"), ConditionValue("string", "y")), False)
        assert first["show_overlay"] is False
        assert first["foreground"] is False
        picker.search.setText("y")
        picker._timer.stop()
        assert first["stale_check"]()
        async_ops.job_mgr.cancel_job.assert_called_with("first")
        first["on_error"]("stale failure")
        assert not picker.error
        dialog.page_requested.emit(picker, ValuePageRequest(0, "y"))
        second = async_ops.run_operation.call_args.kwargs
        second["on_result"](second["work"]())
        first["on_result"](first["work"]())
        first["on_finished"]()
        assert picker.values_list.count() == 1
        assert picker.values_list.item(0).text() == "y"
        second["on_finished"]()
        picker.search.setText("x")
        picker._timer.stop()
        dialog.page_requested.emit(picker, ValuePageRequest(0, "x"))
        callbacks.append(async_ops.run_operation.call_args.kwargs)
        dialog.reject()
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(module.ConditionDialog, "exec", execute)
    module.ReshapeConditionController(async_ops, MagicMock()).open_dialog(parent, editor, source)
    async_ops.job_mgr.cancel_job.assert_called_with("third")
    assert callbacks[0]["stale_check"]()
    callbacks[0]["on_error"]("late failure")
    callbacks[0]["on_result"](ValuePage((), False))
    assert editor.text.text() == "manual"
    pd.testing.assert_frame_equal(source, original)


def test_apply_only_updates_target_editor_and_restores_state(monkeypatch) -> None:
    parent = QWidget()
    target = ConditionEditor(parent)
    other = ConditionEditor(parent)
    other.text.setText("unchanged")
    async_ops = MagicMock()

    def execute(dialog):
        rule = dialog.rules[0]
        rule.column.setCurrentIndex(1)
        rule.operator.setCurrentIndex(rule.operator.findData(ConditionOperator.IS_NULL))
        dialog.accept()
        return dialog.result()

    monkeypatch.setattr(module.ConditionDialog, "exec", execute)
    controller = module.ReshapeConditionController(async_ops, MagicMock())
    controller.open_dialog(parent, target, pd.DataFrame({"a": [None]}))
    assert target.text.text() == "[a] IS NULL"
    assert target.restorable_group() is not None
    assert other.text.text() == "unchanged"
    async_ops.run_operation.assert_not_called()


def test_failure_removed_rule_and_deleted_editor_are_safe(monkeypatch) -> None:
    parent = QWidget()
    editor = ConditionEditor(parent)
    async_ops = MagicMock()
    async_ops.job_mgr.get_job_id.return_value = "job"
    logger = MagicMock()

    def execute(dialog):
        rule = dialog.rules[0]
        rule.column.setCurrentIndex(1)
        rule.picker._timer.stop()
        dialog.page_requested.emit(rule.picker, ValuePageRequest(0))
        callbacks = async_ops.run_operation.call_args.kwargs
        problem = callbacks["work"]()
        assert problem == ConditionProblem.UNSUPPORTED_VALUE
        callbacks["on_result"](problem)
        assert rule.picker.error
        assert not dialog.apply_button.isEnabled()
        dialog.remove_rule(rule)
        assert callbacks["stale_check"]()
        callbacks["on_error"]("removed")
        replacement = dialog.add_rule()
        replacement.column.setCurrentIndex(1)
        replacement.operator.setCurrentIndex(replacement.operator.findData(ConditionOperator.IS_NULL))
        dialog.accept()
        sip.delete(editor)
        return dialog.result()

    monkeypatch.setattr(module.ConditionDialog, "exec", execute)
    module.ReshapeConditionController(async_ops, logger).open_dialog(parent, editor, pd.DataFrame({"a": [[1]]}))
    logger.warning.assert_called_once()
    async_ops.job_mgr.cancel_job.assert_called_with("job")


def test_independent_rule_jobs_and_destroyed_dialog(monkeypatch) -> None:
    parent = QWidget()
    editor = ConditionEditor(parent)
    async_ops = MagicMock()
    async_ops.job_mgr.get_job_id.side_effect = ["first-rule", "second-rule"]
    callbacks = []

    def execute(dialog):
        for position, rule in enumerate((dialog.rules[0], dialog.add_rule())):
            rule.column.setCurrentIndex(position + 1)
            rule.picker._timer.stop()
            dialog.page_requested.emit(rule.picker, ValuePageRequest(position))
            callbacks.append(async_ops.run_operation.call_args.kwargs)
        first, second = callbacks
        assert first["scope"] != second["scope"]
        second["on_result"](second["work"]())
        first["on_result"](first["work"]())
        assert dialog.rules[0].picker.values_list.item(0).text() == "left"
        assert dialog.rules[1].picker.values_list.item(0).text() == "right"
        dialog.rules[0].picker.search.setText("new")
        dialog.rules[0].picker._timer.stop()
        assert first["stale_check"]()
        assert not second["stale_check"]()
        sip.delete(dialog)
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(module.ConditionDialog, "exec", execute)
    module.ReshapeConditionController(async_ops, MagicMock()).open_dialog(
        parent,
        editor,
        pd.DataFrame({"a": ["left"], "b": ["right"]}),
    )
    for callback in callbacks:
        assert callback["stale_check"]()
        callback["on_result"](ValuePage((), False))
        callback["on_error"]("destroyed")
        callback["on_finished"]()
    assert editor.text.text() == ""
    assert async_ops.job_mgr.cancel_job.call_count == 2


def test_nested_loading_rules_move_without_restarting_jobs_and_close_cancels_all(monkeypatch):
    parent = QWidget()
    editor = ConditionEditor(parent)
    editor.text.setText("manual")
    async_ops = MagicMock()
    async_ops.job_mgr.get_job_id.side_effect = ["first", "second", "third"]
    callbacks = []

    def execute(dialog):
        dialog.add_rule()
        dialog.add_rule()
        for rule in dialog.rules:
            rule.column.setCurrentIndex(1)
            rule.picker._timer.stop()
            dialog.page_requested.emit(rule.picker, ValuePageRequest(0))
            callbacks.append(async_ops.run_operation.call_args.kwargs)
        tree = dialog.tree
        first, second, third = tree.model.root.children
        generations = [rule.picker.generation for rule in dialog.rules]
        tree.move_node(second, first, ConditionDrop.INTO)
        inner = tree.model.parent(first)
        tree.move_node(inner, third, ConditionDrop.INTO)
        assert [rule.picker.generation for rule in dialog.rules] == generations
        assert async_ops.run_operation.call_count == 3
        async_ops.job_mgr.cancel_job.assert_not_called()
        assert not dialog.apply_button.isEnabled()
        callbacks[0]["on_result"](callbacks[0]["work"]())
        picker = dialog.rules[0].picker
        picker.values_list.item(0).setCheckState(Qt.CheckState.Checked)
        assert picker.selected_values() == (ConditionValue("string", "x"),)
        tree.perform_action(first, "outdent")
        assert picker.selected_values() == (ConditionValue("string", "x"),)
        removed = dialog.rules[1]
        dialog.remove_rule(removed)
        async_ops.job_mgr.cancel_job.assert_called_once_with("second")
        assert callbacks[1]["stale_check"]()
        callbacks[1]["on_error"]("removed")
        dialog.reject()
        return dialog.result()

    monkeypatch.setattr(module.ConditionDialog, "exec", execute)
    module.ReshapeConditionController(async_ops, MagicMock()).open_dialog(parent, editor, pd.DataFrame({"a": ["x"]}))
    assert {call.args[0] for call in async_ops.job_mgr.cancel_job.call_args_list} == {"first", "second", "third"}
    for callback in callbacks:
        assert callback["stale_check"]()
        callback["on_result"](ValuePage((), False))
    assert editor.text.text() == "manual"
