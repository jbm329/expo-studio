from __future__ import annotations

import pandas as pd
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel

from expo_jbm329.gui.dialogs.analysis.chi_square_config import ChiSquareConfigWidget
from expo_jbm329.gui.dialogs.analysis.group_comparison_config import GroupComparisonConfigWidget
from expo_jbm329.gui.dialogs.analysis.hypothesis_tests_config import (
    HypothesisTestsConfigWidget,
    PairedComparisonConfigWidget,
)
from expo_jbm329.services.analysis.categories import HypothesisTest
from expo_jbm329.services.analysis.chi_square import analyze_chi_square
from expo_jbm329.services.analysis.group_comparison import analyze_group_comparison
from expo_jbm329.services.analysis.paired_comparison import initialize_paired_comparison


def _df() -> pd.DataFrame:
    return pd.DataFrame({
        "value": [float(i) for i in range(24)],
        "other": [float(i) * 10 for i in range(24)],
        "grp": ["A", "B"] * 12,
        "color": ["r", "g", "b"] * 8,
    })


def _widget(df: pd.DataFrame | None = None) -> HypothesisTestsConfigWidget:
    data = _df() if df is None else df
    return HypothesisTestsConfigWidget(
        analyze_group_comparison(data),
        analyze_chi_square(data),
        initialize_paired_comparison(data),
    )


def _record(signal) -> list[None]:
    received: list[None] = []
    signal.connect(lambda: received.append(None))
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
    assert isinstance(stack.widget(2), PairedComparisonConfigWidget)
    assert stack.currentIndex() == 0


def test_switching_test_shows_its_page_and_emits_test_changed_once():
    widget = _widget()
    test_changes = _record(widget.test_changed)
    applies = _record(widget.apply_requested)

    _select_test(widget, HypothesisTest.CHI_SQUARE)

    assert widget._stack.currentIndex() == 1  # noqa: SLF001
    assert widget.current_configuration() == (HypothesisTest.CHI_SQUARE, ("grp", "color"))
    assert test_changes == [None]
    assert applies == []
    assert widget.applied_configuration() is None


def test_inner_selection_changes_are_pending_until_applied():
    widget = _widget()
    test_changes = _record(widget.test_changed)
    applies = _record(widget.apply_requested)
    gc_config = widget._group_comparison_config  # noqa: SLF001
    assert gc_config is not None

    gc_config._numeric_combo.setCurrentIndex(1)  # noqa: SLF001

    assert test_changes == []
    assert applies == []
    assert widget.group_comparison_selection() == ("other", "grp")
    assert widget.applied_configuration() is None


def test_apply_stores_the_current_configuration_and_emits():
    widget = _widget()
    applies = _record(widget.apply_requested)
    _select_test(widget, HypothesisTest.CHI_SQUARE)

    widget._apply_button.click()  # noqa: SLF001

    assert applies == [None]
    assert widget.applied_configuration() == (HypothesisTest.CHI_SQUARE, ("grp", "color"))


def test_applied_configuration_is_kept_while_the_selection_changes():
    widget = _widget()
    widget._apply_button.click()  # noqa: SLF001
    gc_config = widget._group_comparison_config  # noqa: SLF001
    assert gc_config is not None

    gc_config._numeric_combo.setCurrentIndex(1)  # noqa: SLF001

    assert widget.applied_configuration() == (HypothesisTest.GROUP_COMPARISON, ("value", "grp"))
    assert widget.current_configuration() == (HypothesisTest.GROUP_COMPARISON, ("other", "grp"))


def test_construction_does_not_emit():
    widget = _widget()

    assert _record(widget.test_changed) == []
    assert _record(widget.apply_requested) == []


def test_unavailable_tests_get_a_notice_page_and_no_selection():
    widget = _widget(pd.DataFrame({"a": ["x", "y", "z"]}))
    stack = widget._stack  # noqa: SLF001

    assert isinstance(stack.widget(0), QLabel)
    assert isinstance(stack.widget(1), QLabel)
    assert isinstance(stack.widget(2), QLabel)
    assert widget.group_comparison_selection() is None
    assert widget.chi_square_selection() is None
    assert widget.paired_comparison_selection() is None
    assert widget.current_configuration() == (HypothesisTest.GROUP_COMPARISON, None)
    assert not widget.is_selected_test_available()
    assert not widget._apply_button.isEnabled()  # noqa: SLF001

    _select_test(widget, HypothesisTest.CHI_SQUARE)

    assert widget.current_configuration() == (HypothesisTest.CHI_SQUARE, None)
    _select_test(widget, HypothesisTest.PAIRED_COMPARISON)
    assert widget.current_configuration() == (HypothesisTest.PAIRED_COMPARISON, None)
    assert not widget._apply_button.isEnabled()  # noqa: SLF001


def test_only_one_test_may_be_unavailable():
    # Numeric column + a single categorical column: Group Comparison works, chi-square doesn't.
    widget = _widget(pd.DataFrame({"value": [float(i) for i in range(24)], "grp": ["A", "B"] * 12}))
    stack = widget._stack  # noqa: SLF001

    assert isinstance(stack.widget(0), GroupComparisonConfigWidget)
    assert isinstance(stack.widget(1), QLabel)
    assert isinstance(stack.widget(2), QLabel)
    assert widget._apply_button.isEnabled()  # noqa: SLF001

    _select_test(widget, HypothesisTest.CHI_SQUARE)

    assert not widget.is_selected_test_available()
    assert not widget._apply_button.isEnabled()  # noqa: SLF001

    _select_test(widget, HypothesisTest.PAIRED_COMPARISON)

    assert not widget.is_selected_test_available()
    assert not widget._apply_button.isEnabled()  # noqa: SLF001

    _select_test(widget, HypothesisTest.GROUP_COMPARISON)

    assert widget._apply_button.isEnabled()  # noqa: SLF001


def test_paired_selection_requires_two_columns_and_is_applied_in_dataset_order():
    data = _df()
    data["third"] = [float(i) * 20 for i in range(len(data))]
    widget = _widget(data)
    _select_test(widget, HypothesisTest.PAIRED_COMPARISON)
    config = widget._paired_comparison_config  # noqa: SLF001
    assert config is not None
    received = _record(widget.apply_requested)

    assert widget.current_configuration() == (
        HypothesisTest.PAIRED_COMPARISON,
        ("value", "other"),
    )
    assert widget._apply_button.isEnabled()  # noqa: SLF001

    config._columns_list.item(0).setCheckState(Qt.CheckState.Unchecked)  # noqa: SLF001
    assert widget.current_configuration() == (HypothesisTest.PAIRED_COMPARISON, None)
    assert not widget._apply_button.isEnabled()  # noqa: SLF001

    config._columns_list.item(0).setCheckState(Qt.CheckState.Checked)  # noqa: SLF001
    config._columns_list.item(1).setCheckState(Qt.CheckState.Unchecked)  # noqa: SLF001
    config._columns_list.item(2).setCheckState(Qt.CheckState.Checked)  # noqa: SLF001
    assert widget.current_configuration() == (
        HypothesisTest.PAIRED_COMPARISON,
        ("value", "third"),
    )

    widget._apply_button.click()  # noqa: SLF001
    assert received == [None]
    assert widget.applied_configuration() == (
        HypothesisTest.PAIRED_COMPARISON,
        ("value", "third"),
    )
