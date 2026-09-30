from __future__ import annotations

import dataclasses

from expo_jbm329.gui.dialogs.analysis.chi_square_config import ChiSquareConfigWidget
from expo_jbm329.services.analysis.chi_square import ChiSquareResult
from expo_jbm329.services.analysis.group_comparison import ColumnExclusionReason, ExcludedColumn

_NAN = float("nan")


def _make_result(
    row_column: str = "a",
    column_column: str = "b",
    available_columns: tuple[str, ...] = ("a", "b", "c"),
) -> ChiSquareResult:
    return ChiSquareResult(
        row_column=row_column,
        column_column=column_column,
        available_columns=available_columns,
        row_labels=(),
        column_labels=(),
        observed=(),
        expected=(),
        adjusted_residuals=(),
        total=0,
        chi2_statistic=_NAN,
        p_value=_NAN,
        degrees_of_freedom=0,
        yates_correction_applied=False,
        cramers_v=_NAN,
        fisher_odds_ratio=None,
        fisher_p_value=None,
        low_expected_fraction=_NAN,
        min_expected=_NAN,
        cochran_violated=False,
        error=None,
    )


def _items(combo) -> list[str]:
    return [combo.itemText(i) for i in range(combo.count())]


def test_populates_row_combo_with_every_available_column():
    widget = ChiSquareConfigWidget(_make_result())

    assert _items(widget._row_combo) == ["a", "b", "c"]  # noqa: SLF001


def test_populates_column_combo_excluding_the_current_row_variable():
    widget = ChiSquareConfigWidget(_make_result())

    assert _items(widget._column_combo) == ["b", "c"]  # noqa: SLF001


def test_defaults_to_the_results_current_selection():
    widget = ChiSquareConfigWidget(_make_result(row_column="c", column_column="a"))

    assert widget.current_selection() == ("c", "a")


def test_changing_the_row_variable_rebuilds_the_column_combo_and_emits():
    widget = ChiSquareConfigWidget(_make_result(row_column="a", column_column="c"))
    received: list[tuple[str, str]] = []
    widget.selection_changed.connect(lambda row, column: received.append((row, column)))

    widget._row_combo.setCurrentIndex(widget._row_combo.findText("b"))  # noqa: SLF001

    assert _items(widget._column_combo) == ["a", "c"]  # noqa: SLF001
    assert widget.current_selection() == ("b", "c")  # keeps the still-valid column pick
    assert received == [("b", "c")]


def test_choosing_the_current_column_as_row_falls_back_to_the_first_other_column():
    widget = ChiSquareConfigWidget(_make_result(row_column="a", column_column="b"))
    received: list[tuple[str, str]] = []
    widget.selection_changed.connect(lambda row, column: received.append((row, column)))

    widget._row_combo.setCurrentIndex(widget._row_combo.findText("b"))  # noqa: SLF001

    assert widget.current_selection() == ("b", "a")
    assert received == [("b", "a")]


def test_changing_the_column_variable_emits_once():
    widget = ChiSquareConfigWidget(_make_result())
    received: list[tuple[str, str]] = []
    widget.selection_changed.connect(lambda row, column: received.append((row, column)))

    widget._column_combo.setCurrentIndex(widget._column_combo.findText("c"))  # noqa: SLF001

    assert received == [("a", "c")]


def test_current_selection_is_none_when_a_combo_is_empty():
    widget = ChiSquareConfigWidget(dataclasses.replace(_make_result(), available_columns=("a",)))

    assert widget.current_selection() is None


def test_clearing_the_row_combo_does_not_emit():
    widget = ChiSquareConfigWidget(_make_result())
    received: list[tuple[str, str]] = []
    widget.selection_changed.connect(lambda row, column: received.append((row, column)))

    widget._row_combo.clear()  # noqa: SLF001

    assert received == []


_EXCLUDED = (ExcludedColumn("id", 57, ColumnExclusionReason.TOO_MANY_VALUES),)


def test_excluded_columns_are_listed_as_disabled_items_in_both_combos():
    widget = ChiSquareConfigWidget(dataclasses.replace(_make_result(), excluded_columns=_EXCLUDED))

    assert _items(widget._row_combo) == ["a", "b", "c", "", "id"]  # noqa: SLF001
    assert _items(widget._column_combo) == ["b", "c", "", "id"]  # noqa: SLF001
    assert widget.current_selection() == ("a", "b")


def test_changing_the_row_variable_keeps_excluded_columns_listed():
    widget = ChiSquareConfigWidget(dataclasses.replace(_make_result(), excluded_columns=_EXCLUDED))
    received: list[tuple[str, str]] = []
    widget.selection_changed.connect(lambda row, column: received.append((row, column)))

    widget._row_combo.setCurrentIndex(widget._row_combo.findText("c"))  # noqa: SLF001

    assert _items(widget._column_combo) == ["a", "b", "", "id"]  # noqa: SLF001
    assert received == [("c", "b")]


def test_a_programmatically_selected_excluded_row_is_not_reported_or_emitted():
    widget = ChiSquareConfigWidget(dataclasses.replace(_make_result(), excluded_columns=_EXCLUDED))
    received: list[tuple[str, str]] = []
    widget.selection_changed.connect(lambda row, column: received.append((row, column)))

    widget._row_combo.setCurrentIndex(widget._row_combo.findText("id"))  # noqa: SLF001

    assert widget.current_selection() is None
    assert received == []
