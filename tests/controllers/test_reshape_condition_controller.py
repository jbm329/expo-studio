"""Condition worker lifecycle tests without threads or timing assumptions."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pandas as pd
import pytest
from PyQt6 import sip
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QWidget

from expo_jbm329.gui.dialogs.workflows.reshape.condition_editor import ConditionEditor
from expo_jbm329.services.data_operations.reshape_condition_import import condition_group_from_text
from expo_jbm329.services.data_operations.reshape_condition_lint import parse_condition
from expo_jbm329.services.data_operations.reshape_condition_tree import ConditionDrop
from expo_jbm329.services.data_operations.reshape_condition_values import ValuePage, ValuePageRequest
from expo_jbm329.services.data_operations.reshape_conditions import (
    ConditionOperator,
    ConditionProblem,
    ConditionValue,
    condition_columns,
)
from expo_jbm329.workbench.controllers import reshape_condition_controller as module


def test_builder_captures_dtype_and_applies_unquoted_numeric_literal(monkeypatch):
    parent = QWidget()
    source = pd.DataFrame({"age": pd.Series([18], dtype="Int64")})
    editor = ConditionEditor(parent, condition_columns(list(source.columns), list(source.dtypes)))
    async_ops = MagicMock()
    async_ops.job_mgr.get_job_id.return_value = "typed"

    def execute(dialog):
        rule = dialog.rules[0]
        rule.column.setCurrentIndex(1)
        rule.picker._timer.stop()
        dialog.page_requested.emit(rule.picker, ValuePageRequest(0))
        callbacks = async_ops.run_operation.call_args.kwargs
        callbacks["on_result"](callbacks["work"]())
        rule.picker.values_list.item(0).setCheckState(Qt.CheckState.Checked)
        dialog.accept()
        return dialog.result()

    monkeypatch.setattr(module.ConditionDialog, "exec", execute)
    module.ReshapeConditionController(async_ops, MagicMock()).open_dialog(parent, editor, source)
    assert editor.text.text() == "[age] = 18"
    assert editor.condition_valid
    assert editor.restorable_group() is not None


def test_out_of_order_jobs_search_close_and_cancellation(monkeypatch, caplog) -> None:
    caplog.set_level(logging.DEBUG, logger="applogger.service")
    parent = QWidget()
    editor = ConditionEditor(parent)
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
        assert first["log_error_tracebacks"] is False
        assert any(
            f"corr={first['corr_id']}, page=0, source_rows=2" in record.getMessage() for record in caplog.records
        )
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
    assert editor.text.text() == ""
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


def test_failure_removed_rule_and_deleted_editor_are_safe(monkeypatch, caplog) -> None:
    parent = QWidget()
    editor = ConditionEditor(parent)
    async_ops = MagicMock()
    async_ops.job_mgr.get_job_id.return_value = "job"
    logger = MagicMock()
    caplog.set_level(logging.DEBUG, logger="applogger.service")

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
    logger.warning.assert_not_called()
    assert any("problem=unsupported_value" in record.getMessage() for record in caplog.records)
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
    assert editor.text.text() == ""


@pytest.mark.parametrize(
    "text",
    ["[a] = 'unfinished", "[missing] = 'x'", "[dup] IS NULL", "[a] IN ('x', 'x')", "[a] LIKE 'x'"],
)
def test_invalid_conditions_block_builder_show_error_and_preserve_text(monkeypatch, text):
    parent = QWidget()
    source = pd.DataFrame([["x", 1, 2]], columns=["a", "dup", "dup"])
    columns = condition_columns(list(source.columns), list(source.dtypes))
    editor = ConditionEditor(parent, columns)
    editor.text.setText(text)
    state = editor.builder_state()
    assert state.diagnostic is not None
    warning = MagicMock()
    dialog = MagicMock()
    focus = MagicMock()
    monkeypatch.setattr(module.QMessageBox, "warning", warning)
    monkeypatch.setattr(module, "ConditionDialog", dialog)
    monkeypatch.setattr(editor, "focus_builder_diagnostic", focus)
    async_ops = MagicMock()
    module.ReshapeConditionController(async_ops, MagicMock()).open_dialog(parent, editor, source)
    dialog.assert_not_called()
    async_ops.run_operation.assert_not_called()
    warning.assert_called_once_with(
        parent, editor.button.accessibleName(), editor.builder_diagnostic_message(state.diagnostic)
    )
    focus.assert_called_once_with(state.diagnostic)
    assert editor.text.text() == editor.expanded_text.toPlainText() == text
    parent.close()


def test_import_uses_current_source_metadata_not_stale_editor_columns(monkeypatch):
    parent = QWidget()
    editor = ConditionEditor(parent, condition_columns(["a"]))
    editor.text.setText("[a] IS NULL")
    monkeypatch.setattr(module.QMessageBox, "warning", MagicMock())
    dialog = MagicMock()
    monkeypatch.setattr(module, "ConditionDialog", dialog)
    module.ReshapeConditionController(MagicMock(), MagicMock()).open_dialog(parent, editor, pd.DataFrame({"b": [1]}))
    dialog.assert_not_called()
    assert editor.text.text() == "[a] IS NULL"
    parent.close()


@pytest.mark.parametrize("accepted", [False, True])
def test_manual_nested_condition_imports_and_cancel_preserves_exact_text(monkeypatch, accepted):
    parent = QWidget()
    source = pd.DataFrame({"a": [None], "b": ["x"], "c": [None]})
    columns = condition_columns(list(source.columns), list(source.dtypes))
    editor = ConditionEditor(parent, columns)
    text = " [a] is null or ([b] is not null and [c] is null) "
    editor.text.setText(text)
    expected = condition_group_from_text(text, columns).group
    assert expected is not None

    def execute(dialog):
        assert dialog.build_group() == expected
        assert len(dialog.rules) == 3
        if accepted:
            dialog.accept()
        else:
            dialog.reject()
        return dialog.result()

    monkeypatch.setattr(module.ConditionDialog, "exec", execute)
    async_ops = MagicMock()
    module.ReshapeConditionController(async_ops, MagicMock()).open_dialog(parent, editor, source)
    if accepted:
        assert editor.text.text() == "([a] IS NULL OR ([b] IS NOT NULL AND [c] IS NULL))"
        assert editor.restorable_group() == expected
    else:
        assert editor.text.text() == text
    async_ops.run_operation.assert_not_called()
    parent.close()


@pytest.mark.parametrize(
    ("series", "text", "selected"),
    [
        (pd.Series([1.0], dtype="Float64"), "[a] = 1.00", ConditionValue("decimal", "1.00")),
        (pd.Series([True], dtype="boolean"), "[a] = true", ConditionValue("boolean", "True")),
        (
            pd.Series(pd.to_datetime(["2026-10-31"])),
            "[a] = '2026-10-31T00:00:00'",
            ConditionValue("string", "2026-10-31T00:00:00"),
        ),
        (pd.Series([1], dtype="category"), "[a] = '1'", ConditionValue("string", "1")),
        (pd.Series(["x"], dtype="object"), "[a] = 'x'", ConditionValue("string", "x")),
    ],
)
def test_imported_values_are_selected_on_loaded_pages_and_accept_preserves_literals(
    monkeypatch, series, text, selected
):
    parent = QWidget()
    source = pd.DataFrame({"a": series})
    columns = condition_columns(list(source.columns), list(source.dtypes))
    editor = ConditionEditor(parent, columns)
    editor.text.setText(text)
    async_ops = MagicMock()
    async_ops.job_mgr.get_job_id.return_value = "import-page"

    def execute(dialog):
        rule = dialog.rules[0]
        picker = rule.picker
        assert picker.selected_values() == (selected,)
        assert picker.loading
        assert not dialog.apply_button.isEnabled()
        picker._timer.stop()
        dialog.page_requested.emit(picker, ValuePageRequest(0))
        callbacks = async_ops.run_operation.call_args.kwargs
        callbacks["on_result"](callbacks["work"]())
        assert picker.values_list.item(0).checkState() == Qt.CheckState.Checked
        assert picker.selected_values() == (selected,)
        assert dialog.apply_button.isEnabled()
        dialog.accept()
        return dialog.result()

    monkeypatch.setattr(module.ConditionDialog, "exec", execute)
    controller = module.ReshapeConditionController(async_ops, MagicMock())
    controller.open_dialog(parent, editor, source)
    assert parse_condition(editor.text.text(), columns) == parse_condition(text, columns)
    # Reopening accepted text must keep restored selections, too.
    controller.open_dialog(parent, editor, source)
    assert editor.restorable_group() is not None
    parent.close()
