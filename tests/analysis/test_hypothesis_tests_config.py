from __future__ import annotations

import pandas as pd
from PyQt6.QtWidgets import QLabel

from expo_jbm329.gui.dialogs.analysis.chi_square_config import ChiSquareConfigWidget
from expo_jbm329.gui.dialogs.analysis.group_comparison_config import GroupComparisonConfigWidget
from expo_jbm329.gui.dialogs.analysis.hypothesis_tests_config import HypothesisTestsConfigWidget
from expo_jbm329.services.analysis.categories import HypothesisTest
from expo_jbm329.services.analysis.chi_square import analyze_chi_square
from expo_jbm329.services.analysis.group_comparison import analyze_group_comparison


def _df() -> pd.DataFrame:
    return pd.DataFrame({
        "value": [float(i) for i in range(24)],
        "other": [float(i) * 10 for i in range(24)],
        "grp": ["A", "B"] * 12,
        "color": ["r", "g", "b"] * 8,
    })


def _widget(df: pd.DataFrame | None = None) -> HypothesisTestsConfigWidget:
    data = _df() if df is None else df
    return HypothesisTestsConfigWidget(analyze_group_comparison(data), analyze_chi_square(data))


def _received(widget: HypothesisTestsConfigWidget) -> list[None]:
    received: list[None] = []
    widget.configuration_changed.connect(lambda: received.append(None))
    return received


def _select_test(widget: HypothesisTestsConfigWidget, test: HypothesisTest) -> None:
    widget._test_combo.setCurrentIndex(widget._test_combo.findData(test.value))  # noqa: SLF001


def test_offers_every_hypothesis_test_in_enum_order():
    widget = _widget()
    combo = widget._test_combo  # noqa: SLF001

    assert [combo.itemData(i) for i in range(combo.count())] == [test.value for test in HypothesisTest]
    assert all(combo.itemText(i) for i in range(combo.count()))


def test_defaults_to_group_comparison_with_its_default_selection():
    widget = _widget()

    assert widget.selected_test() is HypothesisTest.GROUP_COMPARISON
    assert widget.current_configuration() == (HypothesisTest.GROUP_COMPARISON, ("value", "grp"))
    assert widget.chi_square_selection() == ("grp", "color")


def test_stack_pages_hold_each_tests_config_widget():
    widget = _widget()
    stack = widget._stack  # noqa: SLF001

    assert isinstance(stack.widget(0), GroupComparisonConfigWidget)
    assert isinstance(stack.widget(1), ChiSquareConfigWidget)
    assert stack.currentIndex() == 0


def test_switching_test_shows_its_page_and_emits_once():
    widget = _widget()
    received = _received(widget)

    _select_test(widget, HypothesisTest.CHI_SQUARE)

    assert widget._stack.currentIndex() == 1  # noqa: SLF001
    assert widget.current_configuration() == (HypothesisTest.CHI_SQUARE, ("grp", "color"))
    assert received == [None]


def test_inner_selection_changes_are_forwarded_as_configuration_changes():
    widget = _widget()
    received = _received(widget)
    gc_config = widget._group_comparison_config  # noqa: SLF001
    chi_config = widget._chi_square_config  # noqa: SLF001
    assert gc_config is not None
    assert chi_config is not None

    gc_config._numeric_combo.setCurrentIndex(1)  # noqa: SLF001
    chi_config._column_combo.clear()  # noqa: SLF001 - an incomplete selection is not emitted
    chi_config._row_combo.setCurrentIndex(1)  # noqa: SLF001

    assert len(received) == 2
    assert widget.group_comparison_selection() == ("other", "grp")


def test_construction_does_not_emit():
    widget = _widget()

    assert _received(widget) == []


def test_unavailable_tests_get_a_notice_page_and_no_selection():
    widget = _widget(pd.DataFrame({"a": ["x", "y", "z"]}))
    stack = widget._stack  # noqa: SLF001

    assert isinstance(stack.widget(0), QLabel)
    assert isinstance(stack.widget(1), QLabel)
    assert widget.group_comparison_selection() is None
    assert widget.chi_square_selection() is None
    assert widget.current_configuration() == (HypothesisTest.GROUP_COMPARISON, None)

    _select_test(widget, HypothesisTest.CHI_SQUARE)

    assert widget.current_configuration() == (HypothesisTest.CHI_SQUARE, None)


def test_only_one_test_may_be_unavailable():
    # Numeric column + a single categorical column: Group Comparison works, chi-square doesn't.
    widget = _widget(pd.DataFrame({"value": [float(i) for i in range(24)], "grp": ["A", "B"] * 12}))
    stack = widget._stack  # noqa: SLF001

    assert isinstance(stack.widget(0), GroupComparisonConfigWidget)
    assert isinstance(stack.widget(1), QLabel)
