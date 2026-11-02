from __future__ import annotations

from pathlib import Path
from string import Formatter
from unittest.mock import MagicMock

import pandas as pd
import pytest
from PyQt6.QtCore import QTranslator
from PyQt6.QtWidgets import QDialog, QWidget

from expo_jbm329.services.data_operations.derived_column.derived_column_parser import DerivedColumnFormulaError
from expo_jbm329.services.data_operations.derived_column.derived_column_service import (
    DerivedColumnSpec,
)
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
    apply_to_active_tab = MagicMock()
    current_df = MagicMock(return_value=pd.DataFrame({"n": [1, 2]}))
    active_view = MagicMock(return_value=QWidget())

    ctrl = DerivedColumnController(
        async_ops=async_ops,
        current_df=current_df,
        get_active_view=active_view,
        apply_to_active_tab=apply_to_active_tab,
        dialogs=dialogs,
        main_window=QWidget(),
    )
    return ctrl, async_ops, dialogs, apply_to_active_tab, current_df, active_view


def test_validate_reports_missing_active_dataframe():
    ctrl = DerivedColumnController(
        async_ops=DummyAsyncOps(),
        current_df=MagicMock(return_value=None),
        get_active_view=MagicMock(return_value=QWidget()),
        apply_to_active_tab=MagicMock(),
        dialogs=DummyDialogService(),
        main_window=QWidget(),
    )

    ok, message = ctrl._validate("new_col", "n + 1")

    assert ok is False
    assert message


def test_get_active_dataframe_missing_tab_shows_info():
    dialogs = DummyDialogService()
    ctrl = DerivedColumnController(
        async_ops=DummyAsyncOps(),
        current_df=MagicMock(return_value=None),
        get_active_view=MagicMock(return_value=QWidget()),
        apply_to_active_tab=MagicMock(),
        dialogs=dialogs,
        main_window=QWidget(),
    )

    assert ctrl._get_active_dataframe() is None
    assert dialogs.info_calls


def test_create_derived_column_runs_async(controller, monkeypatch):
    ctrl, async_ops, _, _, _, _ = controller

    monkeypatch.setattr(
        "expo_jbm329.workbench.controllers.derived_column_controller.get_numeric_columns",
        lambda df: ["n"],
    )
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

    ctrl.create_derived_column()

    assert async_ops.calls


def test_apply_result_calls_active_tab(controller):
    ctrl, _, _, apply_to_active_tab, _, _ = controller

    ctrl._apply_result(pd.DataFrame({"n": [1]}), DerivedColumnSpec("derived", "n+1"))

    assert apply_to_active_tab.called


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
    ctrl, async_ops, dialogs, apply, current_df, _ = controller
    current_df.return_value = frame
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
    ctrl.create_derived_column()
    assert captured["validate_callback"]("Group", formula)[0]
    if "Age" not in frame.columns:
        assert captured["numeric_columns"] == []
    assert not dialogs.info_calls
    operation = async_ops.last_kwargs
    assert operation["runner"] == "pool"
    assert operation["scope"] == "derived_column:Group"
    assert operation["corr_id"]
    result = operation["work"]()
    assert result[0]
    operation["apply_result"](result)
    assert apply.call_args.kwargs["df"]["Group"].tolist() == expected
    pd.testing.assert_frame_equal(frame, original)
    assert not dialogs.critical_calls


@pytest.mark.parametrize("accepted_spec", [None, DerivedColumnSpec("Result", "1")])
def test_dialog_rejection_or_missing_spec_does_not_dispatch(controller, monkeypatch, accepted_spec):
    ctrl, async_ops, _, _, _, _ = controller
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
    ctrl.create_derived_column()
    assert not async_ops.calls


def test_conditional_worker_cancellation_does_not_apply(controller):
    ctrl, async_ops, dialogs, apply, _, _ = controller
    ctrl._run_create_derived_column(pd.DataFrame({"Age": [1]}), DerivedColumnSpec("Result", "IF(TRUE; 1; 0)"))
    operation = async_ops.last_kwargs
    result = operation["work"](cancel_cb=lambda: True)
    assert result is None
    operation["apply_result"](result)
    apply.assert_not_called()
    assert not dialogs.critical_calls


def test_worker_returns_formula_failure_for_localized_presentation(controller):
    ctrl, async_ops, dialogs, apply, _, _ = controller
    source = pd.DataFrame({"Text": pd.Series(["text", 123], dtype=object)})
    ctrl._run_create_derived_column(source, DerivedColumnSpec("Result", "IF([Text] IS NULL; 'Empty'; [Text])"))
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
    ctrl, async_ops, _, _, _, _ = controller
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
    ctrl.create_derived_column()
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
    ]
    for marker in markers:
        source = getattr(DerivedColumnController, marker)
        translated = translator.translate("DerivedColumnController", source)
        assert translated and translated != source
        assert {field for _, field, _, _ in Formatter().parse(source) if field} == {
            field for _, field, _, _ in Formatter().parse(translated) if field
        }


def test_missing_active_view_does_not_dispatch_or_apply(controller):
    ctrl, async_ops, dialogs, apply, _, active_view = controller
    active_view.return_value = None
    ctrl._run_create_derived_column(pd.DataFrame({"Vehicle": ["BMW"]}), DerivedColumnSpec("Result", "'Cars'"))
    assert not async_ops.calls
    assert dialogs.info_calls
    apply.assert_not_called()


def test_invalid_condition_is_presented_in_validation_without_dispatch(controller, widget_language):
    ctrl, async_ops, _, _, current_df, _ = controller
    current_df.return_value = pd.DataFrame({"Age": [1]})
    ok, message = ctrl._validate("Result", "IF([Age] IS NULL; 'Empty'; [Age])")
    assert not ok
    assert message == ctrl._tr(ctrl.TR_INCOMPATIBLE_BRANCHES)
    assert not async_ops.calls
