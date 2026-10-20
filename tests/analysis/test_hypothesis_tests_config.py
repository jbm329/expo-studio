from __future__ import annotations

import pandas as pd
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QGroupBox, QLabel

from expo_jbm329.gui.dialogs.analysis.chi_square_config import ChiSquareConfigWidget
from expo_jbm329.gui.dialogs.analysis.group_comparison_config import GroupComparisonConfigWidget
from expo_jbm329.gui.dialogs.analysis.hypothesis_tests_config import (
    HypothesisTestsConfigWidget,
    PairedComparisonConfigWidget,
)
from expo_jbm329.services.analysis.categories import HypothesisTest
from expo_jbm329.services.analysis.chi_square import analyze_chi_square
from expo_jbm329.services.analysis.group_comparison import analyze_group_comparison
from expo_jbm329.services.analysis.limits import CATEGORICAL_MAX_DISTINCT_VALUES
from expo_jbm329.services.analysis.paired_comparison import initialize_paired_comparison


def _df() -> pd.DataFrame:
    size = (CATEGORICAL_MAX_DISTINCT_VALUES // 6 + 1) * 6
    return pd.DataFrame({
        "value": [float(i) for i in range(size)],
        "other": [float(i) * 10 for i in range(size)],
        "grp": ["A", "B"] * (size // 2),
        "color": ["r", "g", "b"] * (size // 3),
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
    edits = _record(widget.configuration_changed)
    applies = _record(widget.apply_requested)
    gc_config = widget._group_comparison_config  # noqa: SLF001
    assert gc_config is not None
    revision = widget.configuration_revision()

    gc_config._numeric_combo.setCurrentIndex(1)  # noqa: SLF001

    assert test_changes == []
    assert edits == [None]
    assert widget.configuration_revision() == revision + 1
    assert applies == []
    assert widget.group_comparison_selection() == ("other", "grp")
    assert widget.applied_configuration() is None


def test_every_test_edit_emits_configuration_changed_once():
    widget = _widget()
    edits = _record(widget.configuration_changed)
    chi = widget._chi_square_config  # noqa: SLF001
    paired = widget._paired_comparison_config  # noqa: SLF001
    assert chi is not None
    assert paired is not None

    _select_test(widget, HypothesisTest.CHI_SQUARE)
    assert edits == []
    chi._row_combo.setCurrentIndex(chi._row_combo.findText("color"))  # noqa: SLF001
    assert edits == [None]

    _select_test(widget, HypothesisTest.PAIRED_COMPARISON)
    paired._columns_list.item(0).setCheckState(Qt.CheckState.Unchecked)  # noqa: SLF001
    paired._select_all_button.click()  # noqa: SLF001
    paired._select_all_button.click()  # noqa: SLF001
    assert edits == [None, None, None]


def test_test_switch_and_apply_advance_the_revision():
    widget = _widget()
    revision = widget.configuration_revision()

    _select_test(widget, HypothesisTest.CHI_SQUARE)
    assert widget.configuration_revision() == revision + 1

    widget._apply_button.click()  # noqa: SLF001
    assert widget.configuration_revision() == revision + 2


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
    assert _record(widget.configuration_changed) == []
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
    widget = _widget(_df()[["value", "grp"]])
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
    assert widget._apply_button.parentWidget() is widget  # noqa: SLF001


def test_apply_stays_below_the_paired_frame_for_every_test():
    widget = _widget()
    paired = widget._paired_comparison_config  # noqa: SLF001
    assert paired is not None
    frame = paired.findChild(QGroupBox)
    apply_button = widget._apply_button  # noqa: SLF001
    received = _record(widget.apply_requested)

    for test in (*HypothesisTest, HypothesisTest.GROUP_COMPARISON, HypothesisTest.PAIRED_COMPARISON):
        _select_test(widget, test)
        assert apply_button.parentWidget() is widget
        assert widget.layout().indexOf(apply_button) == widget.layout().count() - 1
        assert frame.layout().indexOf(apply_button) == -1

    apply_button.click()

    assert received == [None]
    assert widget.applied_configuration() == (HypothesisTest.PAIRED_COMPARISON, ("value", "other"))


def test_paired_select_all_and_clear_update_columns_and_apply_once():
    data = _df()
    data["third"] = [float(i) * 20 for i in range(len(data))]
    widget = _widget(data)
    _select_test(widget, HypothesisTest.PAIRED_COMPARISON)
    paired = widget._paired_comparison_config  # noqa: SLF001
    assert paired is not None
    received = _record(paired.selection_changed)
    frame = paired.findChild(QGroupBox)
    buttons = [paired._select_all_button, paired._clear_button]  # noqa: SLF001
    layout = frame.layout()

    assert all(button.parentWidget() is frame for button in buttons)
    assert layout.indexOf(paired._selection_label) == layout.count() - 1  # noqa: SLF001

    paired._select_all_button.click()  # noqa: SLF001
    assert widget.current_configuration() == (HypothesisTest.PAIRED_COMPARISON, ("value", "other", "third"))
    assert received == [None]

    paired._select_all_button.click()  # noqa: SLF001
    assert received == [None]

    paired._clear_button.click()  # noqa: SLF001
    assert widget.current_configuration() == (HypothesisTest.PAIRED_COMPARISON, None)
    assert not widget._apply_button.isEnabled()  # noqa: SLF001
    assert received == [None, None]

    paired._clear_button.click()  # noqa: SLF001
    assert received == [None, None]


def test_paired_selection_label_guides_count_and_resulting_test():
    data = _df()
    data["third"] = [float(i) * 20 for i in range(len(data))]
    widget = _widget(data)
    paired = widget._paired_comparison_config  # noqa: SLF001
    assert paired is not None
    label = paired._selection_label  # noqa: SLF001
    columns = paired._columns_list  # noqa: SLF001
    frame = paired.findChild(QGroupBox)
    layout = frame.layout()
    _select_test(widget, HypothesisTest.PAIRED_COMPARISON)

    assert label.parentWidget() is frame
    assert layout.indexOf(label) == layout.count() - 1
    assert label.text() == "2 selected - Wilcoxon signed-rank test."

    columns.item(2).setCheckState(Qt.CheckState.Checked)
    assert label.text() == "3 selected - Friedman test."

    columns.item(0).setCheckState(Qt.CheckState.Unchecked)
    columns.item(1).setCheckState(Qt.CheckState.Unchecked)
    assert label.text() == "1 selected - select at least 2."

    paired._clear_button.click()  # noqa: SLF001
    assert label.text() == "None selected - select at least 2."

    paired._select_all_button.click()  # noqa: SLF001
    assert label.text() == "3 selected - Friedman test."


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
