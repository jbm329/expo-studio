from __future__ import annotations

import pytest
from PyQt6.QtCore import Qt

from expo_jbm329.gui.dialogs.analysis.correlation_config import CorrelationConfigWidget
from expo_jbm329.services.analysis.correlation import (
    MAX_SELECTED_COLUMNS,
    CorrelationError,
    CorrelationMatrixResult,
    CorrelationMethod,
)


def _make_result(
    columns: tuple[str, ...] = ("a", "b"),
    available_columns: tuple[str, ...] = ("a", "b", "c", "d"),
    method: CorrelationMethod = CorrelationMethod.PEARSON,
) -> CorrelationMatrixResult:
    return CorrelationMatrixResult(
        method=method,
        columns=columns,
        available_columns=available_columns,
        coefficients=(),
        pairs=(),
        error=None,
    )


def _items(combo) -> list[str]:
    return [combo.itemText(i) for i in range(combo.count())]


def _set_checked(widget: CorrelationConfigWidget, column: str, checked: bool) -> None:
    items = widget._column_list.findItems(column, Qt.MatchFlag.MatchExactly)  # noqa: SLF001
    assert len(items) == 1
    items[0].setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)


def _record(signal) -> list:
    received: list = []
    signal.connect(lambda *args: received.append(args))
    return received


# ----------------------------------------------------------------------
# Initial state
# ----------------------------------------------------------------------


def test_method_combo_lists_every_method_and_selects_the_results():
    widget = CorrelationConfigWidget(_make_result(method=CorrelationMethod.SPEARMAN), ("a", "b"))
    combo = widget._method_combo  # noqa: SLF001

    assert [combo.itemData(i) for i in range(combo.count())] == list(CorrelationMethod)
    assert widget.current_method() is CorrelationMethod.SPEARMAN


def test_column_list_checks_the_results_columns():
    widget = CorrelationConfigWidget(_make_result(columns=("b", "d")), ("b", "d"))

    assert widget._column_list.count() == 4  # noqa: SLF001
    assert widget.checked_columns() == ("b", "d")
    assert widget.applied_columns() == ("b", "d")
    assert widget.matrix_configuration() == (CorrelationMethod.PEARSON, ("b", "d"))


def test_select_all_and_clear_update_pending_matrix_columns_without_applying():
    widget = CorrelationConfigWidget(_make_result(columns=("a", "b")), ("a", "b"))
    received = _record(widget.matrix_requested)

    assert widget._select_all_button.text() == "Select all"  # noqa: SLF001
    assert widget._clear_button.text() == "Clear"  # noqa: SLF001
    group_layout = widget._select_all_button.parentWidget().layout()  # noqa: SLF001
    assert group_layout.itemAt(0).widget() is widget._column_list  # noqa: SLF001
    button_row = group_layout.itemAt(1).layout()
    assert button_row.indexOf(widget._select_all_button) >= 0  # noqa: SLF001
    assert button_row.indexOf(widget._clear_button) >= 0  # noqa: SLF001
    widget._clear_button.click()  # noqa: SLF001
    assert widget.checked_columns() == ()
    assert widget.applied_columns() == ("a", "b")
    assert not widget._apply_button.isEnabled()  # noqa: SLF001

    widget._select_all_button.click()  # noqa: SLF001
    assert widget.checked_columns() == ("a", "b", "c", "d")
    assert widget.applied_columns() == ("a", "b")
    assert widget._apply_button.isEnabled()  # noqa: SLF001
    assert received == []


def test_pair_combos_list_only_matrix_columns_excluding_x_from_y():
    widget = CorrelationConfigWidget(_make_result(), ("c", "a"))

    assert _items(widget._x_combo) == ["a", "b"]  # noqa: SLF001
    assert _items(widget._y_combo) == ["b"]  # noqa: SLF001
    assert widget.current_pair() == ("a", "b")


def test_without_a_pair_defaults_to_the_first_two_columns():
    widget = CorrelationConfigWidget(_make_result(), None)

    assert widget.current_pair() == ("a", "b")


# ----------------------------------------------------------------------
# Method
# ----------------------------------------------------------------------


def test_method_change_is_pending_until_applied():
    widget = CorrelationConfigWidget(_make_result(), ("a", "b"))
    received = _record(widget.matrix_requested)
    _set_checked(widget, "c", checked=True)

    widget._method_combo.setCurrentIndex(widget._method_combo.findData(CorrelationMethod.KENDALL))  # noqa: SLF001

    assert received == []
    assert widget.current_method() is CorrelationMethod.KENDALL
    assert widget.applied_method() is CorrelationMethod.PEARSON
    assert widget.matrix_configuration() == (CorrelationMethod.PEARSON, ("a", "b"))

    widget._apply_button.click()  # noqa: SLF001

    assert received == [()]
    assert widget.matrix_configuration() == (CorrelationMethod.KENDALL, ("a", "b", "c"))


# ----------------------------------------------------------------------
# Pair selection availability
# ----------------------------------------------------------------------


def test_pair_selection_is_disabled_until_enabled():
    widget = CorrelationConfigWidget(_make_result(), None)

    assert widget.is_pair_selection_enabled() is False
    assert widget._pair_group.isEnabled() is False  # noqa: SLF001

    widget.set_pair_selection_enabled(enabled=True)

    assert widget.is_pair_selection_enabled() is True


def test_set_pair_without_notify_selects_the_pair_silently():
    widget = CorrelationConfigWidget(_make_result(columns=("a", "b", "c")), ("a", "b"))
    received = _record(widget.pair_changed)

    widget.set_pair("c", "a", notify=False)

    assert widget.current_pair() == ("c", "a")
    assert received == []


# ----------------------------------------------------------------------
# Columns and Apply
# ----------------------------------------------------------------------


def test_checking_a_column_does_not_request_a_matrix_until_applied():
    widget = CorrelationConfigWidget(_make_result(), ("a", "b"))
    received = _record(widget.matrix_requested)

    _set_checked(widget, "c", checked=True)

    assert received == []
    assert widget.checked_columns() == ("a", "b", "c")
    assert widget.applied_columns() == ("a", "b")

    widget._apply_button.click()  # noqa: SLF001

    assert received == [()]
    assert widget.applied_columns() == ("a", "b", "c")


def test_apply_reruns_an_unchanged_selection():
    widget = CorrelationConfigWidget(_make_result(), ("a", "b"))
    received = _record(widget.matrix_requested)

    assert widget._apply_button.isEnabled()  # noqa: SLF001
    widget._apply_button.click()  # noqa: SLF001

    assert received == [()]


def test_too_few_checked_columns_disable_apply_with_a_hint():
    widget = CorrelationConfigWidget(_make_result(), ("a", "b"))
    received = _record(widget.matrix_requested)

    _set_checked(widget, "b", checked=False)

    assert not widget._apply_button.isEnabled()  # noqa: SLF001
    assert "at least" in widget._selection_label.text()  # noqa: SLF001
    widget._on_apply_clicked()  # noqa: SLF001
    assert received == []
    assert widget.applied_columns() == ("a", "b")


def test_too_many_checked_columns_disable_apply_with_a_hint():
    available = tuple(f"c{i}" for i in range(MAX_SELECTED_COLUMNS + 1))
    widget = CorrelationConfigWidget(_make_result(columns=available[:2], available_columns=available), None)

    for column in available:
        _set_checked(widget, column, checked=True)

    assert not widget._apply_button.isEnabled()  # noqa: SLF001
    assert "at most" in widget._selection_label.text()  # noqa: SLF001

    _set_checked(widget, available[0], checked=False)

    assert widget._apply_button.isEnabled()  # noqa: SLF001


def test_selection_label_shows_the_checked_count():
    widget = CorrelationConfigWidget(_make_result(columns=("a", "b", "c")), ("a", "b"))

    assert widget._selection_label.text().startswith("3 selected")  # noqa: SLF001


# ----------------------------------------------------------------------
# Pair
# ----------------------------------------------------------------------


def test_changing_x_rebuilds_y_and_emits_the_pair():
    widget = CorrelationConfigWidget(_make_result(columns=("a", "b", "c", "d")), ("a", "b"))
    received = _record(widget.pair_changed)

    widget._x_combo.setCurrentIndex(widget._x_combo.findText("c"))  # noqa: SLF001

    assert _items(widget._y_combo) == ["a", "b", "d"]  # noqa: SLF001
    assert received == [("c", "b")]


def test_choosing_y_as_x_falls_back_to_first_remaining_y():
    widget = CorrelationConfigWidget(_make_result(), ("a", "b"))
    received = _record(widget.pair_changed)

    widget._x_combo.setCurrentIndex(widget._x_combo.findText("b"))  # noqa: SLF001

    assert received == [("b", "a")]


def test_changing_y_emits_the_pair():
    widget = CorrelationConfigWidget(_make_result(columns=("a", "b", "d")), ("a", "b"))
    received = _record(widget.pair_changed)

    widget._y_combo.setCurrentIndex(widget._y_combo.findText("d"))  # noqa: SLF001

    assert received == [("a", "d")]


def test_set_pair_selects_both_columns_and_emits_once():
    widget = CorrelationConfigWidget(_make_result(columns=("a", "b", "c", "d")), ("a", "b"))
    received = _record(widget.pair_changed)

    widget.set_pair("d", "c")

    assert widget.current_pair() == ("d", "c")
    assert received == [("d", "c")]


def test_set_pair_ignores_unchanged_identical_or_unknown_pairs():
    widget = CorrelationConfigWidget(_make_result(), ("a", "b"))
    received = _record(widget.pair_changed)

    widget.set_pair("a", "b")
    widget.set_pair("a", "a")
    widget.set_pair("a", "missing")
    widget.set_pair("missing", "a")
    widget.set_pair("a", "c")

    assert received == []
    assert widget.current_pair() == ("a", "b")


def test_current_pair_is_none_when_incomplete():
    widget = CorrelationConfigWidget(_make_result(columns=("a", "b"), available_columns=("a", "b")), ("a", "b"))
    widget._y_combo.clear()  # noqa: SLF001

    assert widget.current_pair() is None
    widget._emit_pair()  # noqa: SLF001 - must not raise nor emit


def test_x_change_to_nothing_is_ignored():
    widget = CorrelationConfigWidget(_make_result(), ("a", "b"))
    received = _record(widget.pair_changed)

    widget._x_combo.setCurrentIndex(-1)  # noqa: SLF001

    assert received == []


def test_pending_and_requested_columns_do_not_change_displayed_pair_choices():
    widget = CorrelationConfigWidget(_make_result(), ("a", "b"))
    received = _record(widget.pair_changed)
    _set_checked(widget, "c", checked=True)
    _set_checked(widget, "a", checked=False)
    widget._apply_button.click()  # noqa: SLF001

    assert widget.applied_columns() == ("b", "c")
    assert _items(widget._x_combo) == ["a", "b"]  # noqa: SLF001
    assert widget.current_pair() == ("a", "b")
    assert received == []


@pytest.mark.parametrize("pair", [("b", "c"), ("a", "d"), None])
def test_displayed_matrix_syncs_pair_scope_silently(pair):
    widget = CorrelationConfigWidget(_make_result(), ("a", "b"))
    received = _record(widget.pair_changed)

    widget.set_displayed_matrix(_make_result(columns=("b", "c")), pair)

    assert _items(widget._x_combo) == ["b", "c"]  # noqa: SLF001
    assert _items(widget._y_combo) == ["c"]  # noqa: SLF001
    assert widget.current_pair() == ("b", "c")
    assert widget.is_pair_selection_enabled()
    assert received == []


def test_displayed_matrix_sync_preserves_preferred_pair_orientation():
    widget = CorrelationConfigWidget(_make_result(), ("a", "b"))
    received = _record(widget.pair_changed)
    widget.set_displayed_matrix(_make_result(columns=("a", "b", "c")), ("c", "a"))

    assert widget.current_pair() == ("c", "a")
    assert _items(widget._y_combo) == ["a", "b"]  # noqa: SLF001
    assert received == []


@pytest.mark.parametrize("failed", [True, False])
def test_invalid_displayed_matrix_does_not_change_choices(failed):
    widget = CorrelationConfigWidget(_make_result(), ("a", "b"))
    result = CorrelationMatrixResult(
        method=CorrelationMethod.PEARSON,
        columns=("b", "c") if failed else ("b",),
        available_columns=("a", "b", "c"),
        coefficients=(),
        pairs=(),
        error=CorrelationError.INVALID_COLUMN if failed else None,
    )

    with pytest.raises(ValueError, match="successful correlation matrix"):
        widget.set_displayed_matrix(result, None)

    assert widget.current_pair() == ("a", "b")
    assert _items(widget._x_combo) == ["a", "b"]  # noqa: SLF001
