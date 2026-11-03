from __future__ import annotations

from pathlib import Path
from string import Formatter
from unittest.mock import MagicMock

import pandas as pd
import pytest
from PyQt6.QtCore import QTranslator
from PyQt6.QtWidgets import QDialog, QTableView, QWidget

from expo_jbm329.services.data_operations.derived_column.derived_column_parser import DerivedColumnFormulaError
from expo_jbm329.services.data_operations.derived_column.derived_column_service import (
    DerivedColumnSpec,
)
from expo_jbm329.services.data_operations.derived_column.derived_column_time import MonthLabels
from expo_jbm329.workbench.controllers.derived_column_controller import (
    DerivedColumnController,
)


class DummyDialogService:
    def __init__(self) -> None:
        self.info_calls = []
        self.critical_calls = []

    def info(self, parent, title, text):
        self.info_calls.append((parent, title, text))

    def critical(self, parent, title, text):
        self.critical_calls.append((parent, title, text))


class DummyAsyncOps:
    def __init__(self) -> None:
        self.calls = []

    def run_dataframe_operation(self, **kwargs):
        self.calls.append(kwargs)
        self.last_kwargs = kwargs
        return object()


@pytest.fixture
def controller():
    dialogs = DummyDialogService()
    async_ops = DummyAsyncOps()
    apply_to_view = MagicMock()
    source = pd.DataFrame({"n": [1, 2]})
    view = QTableView()

    ctrl = DerivedColumnController(
        async_ops=async_ops,
        apply_to_view=apply_to_view,
        dialogs=dialogs,
        main_window=QWidget(),
    )
    return ctrl, async_ops, dialogs, apply_to_view, source, view


def test_create_derived_column_runs_async(controller, monkeypatch):
    ctrl, async_ops, _, _, source, view = controller

    monkeypatch.setattr(
        "expo_jbm329.workbench.controllers.derived_column_controller.DerivedColumnDialog",
        lambda **kwargs: type(
            "Dlg",
            (),
            {
                "exec": lambda self: QDialog.DialogCode.Accepted,
                "get_result": lambda self: DerivedColumnSpec(
                    column_name="derived",
                    formula="n + 1",
                    overwrite_existing=False,
                ),
            },
        )(),
    )

    ctrl.create_derived_column(view, source, 0)

    assert async_ops.calls
    assert async_ops.last_kwargs["view"] is view


def test_apply_result_calls_originating_view(controller):
    ctrl, _, _, apply_to_view, _, view = controller
    result = pd.DataFrame({"n": [1]})

    ctrl._apply_result(view, result, DerivedColumnSpec("derived", "n+1"))

    assert apply_to_view.call_args.args[0] is view
    assert apply_to_view.call_args.args[1] is result


@pytest.mark.parametrize(
    ("frame", "formula", "expected"),
    [
        (
            pd.DataFrame({"Vehicle": ["BMW", "Volvo", "Ford", None]}),
            "IF([Vehicle] IN('BMW', 'Volvo'); 'Cars'; 'Other')",
            ["Cars", "Cars", "Other", "Other"],
        ),
        (
            pd.DataFrame({"Column1": pd.Series(["x", None, ""], dtype="string")}),
            "IF([Column1] IS NULL; 'Empty'; [Column1])",
            ["x", "Empty", ""],
        ),
        (pd.DataFrame({"Age": pd.Series([18, None, 0], dtype="Int64")}), "IF([Age] IS NULL; 0; [Age])", [18, 0, 0]),
    ],
)
def test_conditional_workflow_validates_dispatches_and_applies(controller, monkeypatch, frame, formula, expected):
    ctrl, async_ops, dialogs, apply, _, view = controller
    original = frame.copy(deep=True)
    spec = DerivedColumnSpec(" Group ", formula)
    captured = {}

    def dialog(**kwargs):
        captured.update(kwargs)
        return type(
            "Dialog",
            (),
            {
                "exec": lambda self: QDialog.DialogCode.Accepted,
                "get_result": lambda self: spec,
            },
        )()

    monkeypatch.setattr(
        "expo_jbm329.workbench.controllers.derived_column_controller.DerivedColumnDialog",
        dialog,
    )
    ctrl.create_derived_column(view, frame, 0)
    assert captured["validate_callback"]("Group", formula)[0].ok
    assert "numeric_columns" not in captured
    assert not dialogs.info_calls
    operation = async_ops.last_kwargs
    assert operation["runner"] == "pool"
    assert operation["scope"] == "derived_column:Group"
    assert operation["corr_id"]
    result = operation["work"]()
    assert result[0]
    operation["apply_result"](result)
    assert apply.call_args.args[0] is view
    assert apply.call_args.args[1]["Group"].tolist() == expected
    pd.testing.assert_frame_equal(frame, original)
    assert not dialogs.critical_calls


@pytest.mark.parametrize("accepted_spec", [None, DerivedColumnSpec("Result", "1")])
def test_dialog_rejection_or_missing_spec_does_not_dispatch(controller, monkeypatch, accepted_spec):
    ctrl, async_ops, _, _, source, view = controller
    monkeypatch.setattr(
        "expo_jbm329.workbench.controllers.derived_column_controller.DerivedColumnDialog",
        lambda **kwargs: type(
            "Dialog",
            (),
            {
                "exec": lambda self: QDialog.DialogCode.Rejected if accepted_spec else QDialog.DialogCode.Accepted,
                "get_result": lambda self: accepted_spec,
            },
        )(),
    )
    ctrl.create_derived_column(view, source, 0)
    assert not async_ops.calls


def test_conditional_worker_cancellation_does_not_apply(controller):
    ctrl, async_ops, dialogs, apply, _, view = controller
    ctrl._run_create_derived_column(
        view, pd.DataFrame({"Age": [1]}), DerivedColumnSpec("Result", "IF(TRUE; 1; 0)"), insertion_index=1
    )
    operation = async_ops.last_kwargs
    result = operation["work"](cancel_cb=lambda: True)
    assert result is None
    operation["apply_result"](result)
    apply.assert_not_called()
    assert not dialogs.critical_calls


def test_worker_returns_formula_failure_for_localized_presentation(controller):
    ctrl, async_ops, dialogs, apply, _, view = controller
    source = pd.DataFrame({"Text": pd.Series(["text", 123], dtype=object)})
    ctrl._run_create_derived_column(
        view, source, DerivedColumnSpec("Result", "IF([Text] IS NULL; 'Empty'; [Text])"), insertion_index=1
    )
    operation = async_ops.last_kwargs
    result = operation["work"]()
    assert result[:2] == (False, None)
    assert isinstance(result[2], DerivedColumnFormulaError)
    assert result[2].code == "non_text_column"
    operation["apply_result"](result)
    apply.assert_not_called()
    assert len(dialogs.critical_calls) == 1
    assert "Text" in dialogs.critical_calls[0][2]
    assert dialogs.critical_calls[0][2] != ctrl._tr(ctrl.TR_UNKNOWN)


@pytest.mark.parametrize(
    "code",
    [
        "unclosed_string_literal",
        "invalid_number_literal",
        "expected_token",
        "expected_expression",
        "expected_literal",
        "unexpected_token",
        "expression_nesting_limit",
        "invalid_operand_type",
        "incompatible_operand_types",
        "incompatible_branch_types",
        "invalid_result_type",
        "unsupported_column_type",
        "non_text_column",
        "expression_evaluation_failed",
        "datetime_operand_required",
    ],
)
def test_every_new_error_has_translatable_actionable_message(controller, code, widget_language):
    ctrl, *_ = controller
    error = DerivedColumnFormulaError(
        code,
        context={
            "position": 12,
            "expected": ";",
            "token": "bad",
            "limit": 64,
            "column": "Age",
        },
    )
    message = ctrl._format_error(error)
    assert message
    assert message != ctrl._tr(ctrl.TR_UNKNOWN)
    assert "{" not in message and "}" not in message


def test_controller_keeps_requested_output_policy_when_dispatching(controller, monkeypatch):
    ctrl, async_ops, _, _, source, view = controller
    monkeypatch.setattr(
        "expo_jbm329.workbench.controllers.derived_column_controller.DerivedColumnDialog",
        lambda **kwargs: type(
            "Dialog",
            (),
            {
                "exec": lambda self: QDialog.DialogCode.Accepted,
                "get_result": lambda self: DerivedColumnSpec(
                    "Result",
                    "IF(TRUE; 1/0; 0)",
                    output_dtype="Float64",
                    replace_inf_with_na=False,
                ),
            },
        )(),
    )
    ctrl.create_derived_column(view, source, 0)
    result = async_ops.last_kwargs["work"]()
    assert result[0]
    assert result[1]["Result"].iloc[0] == float("inf")


@pytest.mark.parametrize("language", ["sv", "de", "fr", "it", "es", "pl"])
def test_new_errors_are_present_in_compiled_locales_with_matching_placeholders(language):
    translator = QTranslator()
    catalog = Path(__file__).parents[2] / "src" / "expo_jbm329" / "i18n" / "locales" / f"app_{language}.qm"
    assert translator.load(str(catalog))
    markers = [
        "TR_UNCLOSED_STRING",
        "TR_INVALID_NUMBER",
        "TR_EXPECTED_TOKEN",
        "TR_EXPECTED_EXPRESSION",
        "TR_EXPECTED_LITERAL",
        "TR_UNEXPECTED_TOKEN",
        "TR_NESTING_LIMIT",
        "TR_INVALID_OPERAND_TYPE",
        "TR_INCOMPATIBLE_OPERANDS",
        "TR_INCOMPATIBLE_BRANCHES",
        "TR_INVALID_RESULT_TYPE",
        "TR_UNSUPPORTED_COLUMN_TYPE",
        "TR_NON_TEXT_COLUMN",
        "TR_EXPRESSION_EVALUATION_FAILED",
        "TR_DATETIME_OPERAND_REQUIRED",
    ]
    for marker in markers:
        source = getattr(DerivedColumnController, marker)
        translated = translator.translate("DerivedColumnController", source)
        assert translated and translated != source
        assert {field for _, field, _, _ in Formatter().parse(source) if field} == {
            field for _, field, _, _ in Formatter().parse(translated) if field
        }


@pytest.mark.parametrize("column", [-1, 1])
def test_invalid_clicked_column_does_not_dispatch_or_apply(controller, column):
    ctrl, async_ops, _, apply, source, view = controller
    with pytest.raises(IndexError, match="Invalid source column index"):
        ctrl.create_derived_column(view, source, column)
    assert not async_ops.calls
    apply.assert_not_called()


def test_invalid_condition_is_presented_in_validation_without_dispatch(controller, widget_language):
    ctrl, async_ops, _, _, _, _ = controller
    result, message = ctrl._validate(pd.DataFrame({"Age": [1]}), "Result", "IF([Age] IS NULL; 'Empty'; [Age])")
    assert not result.ok
    assert result.error.code == "incompatible_branch_types"
    assert message == ctrl._tr(ctrl.TR_INCOMPATIBLE_BRANCHES)
    assert not async_ops.calls


def test_nondatetime_time_operand_has_localized_validation_error(controller, widget_language):
    ctrl, async_ops, _, _, source, _ = controller
    result, message = ctrl._validate(source, "Year", "YEAR([n])")
    assert not result.ok
    assert result.error.code == "datetime_operand_required"
    assert message == ctrl._tr_fmt(ctrl.TR_DATETIME_OPERAND_REQUIRED, token="YEAR", position="0")
    assert not async_ops.calls


def test_time_workflow_preserves_captured_month_labels_during_spec_normalization(controller, monkeypatch):
    ctrl, async_ops, dialogs, apply, _, view = controller
    source = pd.DataFrame({"When": pd.to_datetime(["2026-01-01", None])})
    labels = MonthLabels(full=tuple(f"Month {month}" for month in range(1, 13)))
    spec = DerivedColumnSpec(" Group ", " MONTH([When]) ", month_labels=labels)
    monkeypatch.setattr(
        "expo_jbm329.workbench.controllers.derived_column_controller.DerivedColumnDialog",
        lambda **kwargs: type(
            "Dialog",
            (),
            {"exec": lambda self: QDialog.DialogCode.Accepted, "get_result": lambda self: spec},
        )(),
    )
    ctrl.create_derived_column(view, source, 0)
    result = async_ops.last_kwargs["work"]()
    assert result[0]
    assert result[1]["Group"].iloc[0] == "Month 1"
    assert pd.isna(result[1]["Group"].iloc[1])
    async_ops.last_kwargs["apply_result"](result)
    assert apply.called
    assert not dialogs.critical_calls
