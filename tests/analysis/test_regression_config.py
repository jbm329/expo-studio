from __future__ import annotations

import numpy as np
import pandas as pd
from PyQt6.QtCore import Qt

from expo_jbm329.gui.dialogs.analysis.column_combo_box import exclusion_tooltip
from expo_jbm329.gui.dialogs.analysis.regression_config import RegressionConfigWidget
from expo_jbm329.services.analysis.regression import MAX_PREDICTORS, RegressionResult, analyze_regression
from expo_jbm329.services.analysis.regression_glm import GeneralizedTargetColumns, RegressionModel
from expo_jbm329.services.analysis.survival import SurvivalColumns


def _frame() -> pd.DataFrame:
    size = 30
    return pd.DataFrame({
        "y": np.arange(size, dtype=float),
        "x": np.arange(size, dtype=float) % 7,
        "z": np.arange(size, dtype=float) % 5,
        "g": ["a", "b", "c"] * 10,
        "id": [str(i) for i in range(size)],
        "when": pd.date_range("2024-01-01", periods=size),
    })


def _result(target: str | None = None, predictors: tuple[str, ...] = ()) -> RegressionResult:
    return analyze_regression(_frame(), target, predictors)


def _items(widget: RegressionConfigWidget) -> list:
    predictor_list = widget._predictor_list  # noqa: SLF001
    return [predictor_list.item(i) for i in range(predictor_list.count())]


def _item(widget: RegressionConfigWidget, column: str):
    return next(item for item in _items(widget) if item.data(Qt.ItemDataRole.UserRole) == column)


def _is_enabled(item) -> bool:
    return bool(item.flags() & Qt.ItemFlag.ItemIsEnabled)


def _set_checked(widget: RegressionConfigWidget, column: str, checked: bool) -> None:
    _item(widget, column).setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)


def _record(signal) -> list:
    received: list = []
    signal.connect(lambda *args: received.append(args))
    return received


# ----------------------------------------------------------------------
# Initial state
# ----------------------------------------------------------------------


def test_target_combo_lists_numeric_columns_and_selects_the_results_target():
    widget = RegressionConfigWidget(_result("x"))
    combo = widget._target_combo  # noqa: SLF001

    assert combo.eligible_columns() == ("y", "x", "z")
    assert widget.current_target() == "x"
    assert widget.current_model() is RegressionModel.LINEAR


def test_predictor_list_shows_numeric_then_categorical_then_excluded_columns():
    widget = RegressionConfigWidget(_result())

    assert [item.text() for item in _items(widget)] == ["y", "x", "z", "g (categorical)", "id (categorical)"]
    assert [item.data(Qt.ItemDataRole.UserRole) for item in _items(widget)] == ["y", "x", "z", "g", "id"]


def test_excluded_columns_show_an_unchecked_disabled_checkbox_and_tooltip():
    result = _result()
    widget = RegressionConfigWidget(result)
    item = _item(widget, "id")

    assert not _is_enabled(item)
    assert item.flags() & Qt.ItemFlag.ItemIsUserCheckable
    assert item.checkState() == Qt.CheckState.Unchecked
    assert item.toolTip() == exclusion_tooltip(result.predictor_columns.excluded[0])


def test_the_target_is_listed_disabled_and_unchecked():
    widget = RegressionConfigWidget(_result("y"))
    item = _item(widget, "y")

    assert not _is_enabled(item)
    assert item.checkState() == Qt.CheckState.Unchecked
    assert item.toolTip() == widget.tr("This column is the target.")
    assert _is_enabled(_item(widget, "x"))


def test_nothing_is_checked_initially_without_predictors():
    widget = RegressionConfigWidget(_result())

    assert widget.checked_predictors() == ()
    assert widget.applied_predictors() == ()
    assert widget.model_configuration() == (RegressionModel.LINEAR, "y", ())
    assert not widget._apply_button.isEnabled()  # noqa: SLF001
    assert widget._selection_label.text() == widget.tr("None selected - select at least one.")  # noqa: SLF001


def test_select_all_and_clear_only_toggle_eligible_non_target_predictors():
    widget = RegressionConfigWidget(_result("y"))
    received = _record(widget.model_requested)

    assert widget._select_all_button.text() == "Select all"  # noqa: SLF001
    assert widget._clear_button.text() == "Clear"  # noqa: SLF001
    group_layout = widget._select_all_button.parentWidget().layout()  # noqa: SLF001
    assert group_layout.itemAt(0).widget() is widget._predictor_list  # noqa: SLF001
    button_row = group_layout.itemAt(1).layout()
    assert button_row.indexOf(widget._select_all_button) >= 0  # noqa: SLF001
    assert button_row.indexOf(widget._clear_button) >= 0  # noqa: SLF001
    widget._select_all_button.click()  # noqa: SLF001
    assert widget.checked_predictors() == ("x", "z", "g")
    assert widget.applied_predictors() == ()
    assert _item(widget, "y").checkState() == Qt.CheckState.Unchecked
    assert _item(widget, "id").checkState() == Qt.CheckState.Unchecked

    widget._clear_button.click()  # noqa: SLF001
    assert widget.checked_predictors() == ()
    assert widget.applied_predictors() == ()
    assert received == []


def test_the_results_predictors_are_checked_and_applied():
    widget = RegressionConfigWidget(_result("y", ("g", "x")))

    assert widget.checked_predictors() == ("x", "g")  # list order
    assert widget.applied_predictors() == ("g", "x")
    assert widget.model_configuration() == (RegressionModel.LINEAR, "y", ("g", "x"))
    assert widget._apply_button.isEnabled()  # noqa: SLF001


def test_construction_does_not_emit():
    widget = RegressionConfigWidget(_result())
    received = _record(widget.model_requested)

    assert received == []


# ----------------------------------------------------------------------
# Predictors
# ----------------------------------------------------------------------


def test_checking_predictors_updates_the_count_without_emitting():
    widget = RegressionConfigWidget(_result())
    received = _record(widget.model_requested)

    _set_checked(widget, "x", True)
    _set_checked(widget, "g", True)

    assert received == []
    assert widget.checked_predictors() == ("x", "g")
    assert widget.applied_predictors() == ()
    assert widget._apply_button.isEnabled()  # noqa: SLF001
    assert widget._selection_label.text() == widget.tr("{count} selected (at most {maximum}).").format(  # noqa: SLF001
        count="2", maximum=str(MAX_PREDICTORS)
    )


def test_apply_applies_the_checked_predictors_and_emits():
    widget = RegressionConfigWidget(_result())
    received = _record(widget.model_requested)
    _set_checked(widget, "z", True)

    widget._apply_button.click()  # noqa: SLF001

    assert received == [()]
    assert widget.model_configuration() == (RegressionModel.LINEAR, "y", ("z",))


def test_apply_can_rerun_an_unchanged_selection():
    widget = RegressionConfigWidget(_result("y", ("x",)))
    received = _record(widget.model_requested)

    widget._apply_button.click()  # noqa: SLF001
    widget._apply_button.click()  # noqa: SLF001

    assert len(received) == 2


def test_invalid_selection_is_never_applied():
    widget = RegressionConfigWidget(_result("y", ("x",)))
    received = _record(widget.model_requested)
    _set_checked(widget, "x", False)

    widget._on_apply_clicked()  # noqa: SLF001

    assert received == []
    assert widget.applied_predictors() == ("x",)


def test_too_many_predictors_disables_apply_and_explains():
    df = pd.DataFrame({f"n{i}": np.arange(10, dtype=float) * i for i in range(MAX_PREDICTORS + 2)})
    widget = RegressionConfigWidget(analyze_regression(df))
    for index in range(1, MAX_PREDICTORS + 2):
        _set_checked(widget, f"n{index}", True)

    assert not widget._apply_button.isEnabled()  # noqa: SLF001
    assert widget._selection_label.text() == widget.tr("{count} selected - select at most {maximum}.").format(  # noqa: SLF001
        count=str(MAX_PREDICTORS + 1), maximum=str(MAX_PREDICTORS)
    )


# ----------------------------------------------------------------------
# Target
# ----------------------------------------------------------------------


def test_changing_the_target_swaps_the_disabled_item_and_emits():
    widget = RegressionConfigWidget(_result("y", ("x", "z")))
    received = _record(widget.model_requested)
    combo = widget._target_combo  # noqa: SLF001

    combo.setCurrentIndex(combo.findText("x"))

    assert received == [()]
    assert widget.model_configuration() == (RegressionModel.LINEAR, "x", ("z",))
    assert widget.checked_predictors() == ("z",)
    assert not _is_enabled(_item(widget, "x"))
    assert _item(widget, "x").checkState() == Qt.CheckState.Unchecked
    y_item = _item(widget, "y")
    assert _is_enabled(y_item)
    assert y_item.toolTip() == ""
    assert y_item.checkState() == Qt.CheckState.Unchecked


def test_changing_target_before_predictors_are_applied_does_not_request_a_model():
    widget = RegressionConfigWidget(_result())
    received = _record(widget.model_requested)
    combo = widget._target_combo  # noqa: SLF001

    combo.setCurrentIndex(combo.findText("x"))

    assert received == []
    assert widget.model_configuration() == (RegressionModel.LINEAR, "x", ())


def test_clearing_the_target_is_ignored():
    widget = RegressionConfigWidget(_result("y", ("x",)))
    received = _record(widget.model_requested)

    widget._target_combo.setCurrentIndex(-1)  # noqa: SLF001

    assert received == []
    assert widget.applied_predictors() == ("x",)


def test_model_selector_updates_target_eligibility_and_remembers_each_model_target():
    targets = GeneralizedTargetColumns(binary=("g",), count=("x", "z"))
    widget = RegressionConfigWidget(_result("y"), targets)
    changed = _record(widget.configuration_changed)
    model_combo = widget._model_combo  # noqa: SLF001
    target_combo = widget._target_combo  # noqa: SLF001

    model_combo.setCurrentIndex(model_combo.findData(RegressionModel.LOGISTIC.value))

    assert widget.model_configuration() == (RegressionModel.LOGISTIC, "g", ())
    assert target_combo.eligible_columns() == ("g",)
    assert changed == [()]

    model_combo.setCurrentIndex(model_combo.findData(RegressionModel.POISSON.value))

    assert widget.model_configuration() == (RegressionModel.POISSON, "x", ())
    assert target_combo.eligible_columns() == ("x", "z")

    model_combo.setCurrentIndex(model_combo.findData(RegressionModel.LOGISTIC.value))

    assert widget.current_target() == "g"


def test_model_without_eligible_targets_disables_target_and_apply():
    widget = RegressionConfigWidget(_result("y"), GeneralizedTargetColumns(binary=(), count=()))
    combo = widget._model_combo  # noqa: SLF001
    combo.setCurrentIndex(combo.findData(RegressionModel.LOGISTIC.value))

    assert widget.current_target() == ""
    assert not widget._target_combo.isEnabled()  # noqa: SLF001
    assert widget._target_notice.text() == widget.tr("No eligible target columns are available for this model.")  # noqa: SLF001
    assert not widget._apply_button.isEnabled()  # noqa: SLF001


def test_changing_model_refits_when_predictors_are_already_applied():
    widget = RegressionConfigWidget(
        _result("y", ("x", "g")),
        GeneralizedTargetColumns(binary=("g",), count=("x", "z")),
    )
    requested = _record(widget.model_requested)
    changed = _record(widget.configuration_changed)

    widget._model_combo.setCurrentIndex(  # noqa: SLF001
        widget._model_combo.findData(RegressionModel.LOGISTIC.value)  # noqa: SLF001
    )

    assert widget.model_configuration() == (RegressionModel.LOGISTIC, "g", ("x",))
    assert requested == [()]
    assert changed == []


def test_cox_selectors_exclude_both_outcomes_and_wait_for_apply():
    columns = SurvivalColumns(durations=("duration", "event"), events=("event", "flag"))
    df = _frame()
    df["duration"] = np.arange(1, len(df) + 1, dtype=float)
    df["event"] = np.arange(len(df)) % 2
    df["flag"] = np.arange(len(df)) % 2 == 0
    result = analyze_regression(df)
    widget = RegressionConfigWidget(result, survival_columns=columns)
    requested = _record(widget.model_requested)
    changed = _record(widget.configuration_changed)
    model_combo = widget._model_combo  # noqa: SLF001
    model_combo.setCurrentIndex(model_combo.findData(RegressionModel.COX.value))

    assert requested == []
    assert widget.current_model() is RegressionModel.COX
    assert widget.current_duration() == "duration"
    assert widget.current_event() == "event"
    assert not _is_enabled(_item(widget, "duration"))
    assert not _is_enabled(_item(widget, "event"))
    assert widget.current_duration() not in widget._event_combo.eligible_columns()  # noqa: SLF001
    assert changed == [()]

    _set_checked(widget, "x", True)
    assert requested == []
    widget._apply_button.click()  # noqa: SLF001
    assert requested == [()]


def test_changing_cox_outcomes_invalidates_configuration_without_starting_a_fit():
    columns = SurvivalColumns(durations=("duration", "duration2"), events=("event", "flag"))
    df = _frame()
    df["duration"] = np.arange(1, len(df) + 1, dtype=float)
    df["duration2"] = np.arange(2, len(df) + 2, dtype=float)
    df["event"] = np.arange(len(df)) % 2
    df["flag"] = np.arange(len(df)) % 2 == 0
    widget = RegressionConfigWidget(analyze_regression(df), survival_columns=columns)
    widget._model_combo.setCurrentIndex(widget._model_combo.findData(RegressionModel.COX.value))  # noqa: SLF001
    revision = widget.configuration_revision()
    requested = _record(widget.model_requested)
    widget._duration_combo.setCurrentIndex(widget._duration_combo.findText("duration2"))  # noqa: SLF001

    assert widget.current_duration() == "duration2"
    assert widget.configuration_revision() > revision
    assert requested == []
