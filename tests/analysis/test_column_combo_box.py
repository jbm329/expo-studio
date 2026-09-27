from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QStandardItemModel

from expo_jbm329.gui.dialogs.analysis.column_combo_box import ColumnComboBox
from expo_jbm329.services.analysis.group_comparison import (
    MAX_GROUPS,
    MIN_GROUPS,
    ColumnExclusionReason,
    ExcludedColumn,
)

_TOO_MANY = ExcludedColumn("id", 57, ColumnExclusionReason.TOO_MANY_VALUES)
_TOO_FEW = ExcludedColumn("const", 1, ColumnExclusionReason.TOO_FEW_VALUES)


def _items(combo: ColumnComboBox) -> list[str]:
    return [combo.itemText(i) for i in range(combo.count())]


def _is_enabled(combo: ColumnComboBox, index: int) -> bool:
    model = combo.model()
    assert isinstance(model, QStandardItemModel)
    item = model.item(index)
    assert item is not None
    return item.isEnabled()


def _tooltip(combo: ColumnComboBox, index: int) -> str:
    return combo.itemData(index, Qt.ItemDataRole.ToolTipRole)


def test_without_excluded_columns_only_eligible_items_are_listed():
    combo = ColumnComboBox()
    combo.set_columns(["a", "b"])

    assert _items(combo) == ["a", "b"]
    assert combo.eligible_columns() == ("a", "b")
    assert combo.current_column() == "a"


def test_excluded_columns_follow_a_separator_as_disabled_items():
    combo = ColumnComboBox()
    combo.set_columns(["a", "b"], [_TOO_MANY, _TOO_FEW])

    assert _items(combo) == ["a", "b", "", "id", "const"]
    assert [_is_enabled(combo, i) for i in range(combo.count())] == [True, True, False, False, False]
    assert combo.eligible_columns() == ("a", "b")


def test_excluded_items_explain_the_reason_in_their_tooltip():
    combo = ColumnComboBox()
    combo.set_columns(["a"], [_TOO_MANY, _TOO_FEW])

    too_many = _tooltip(combo, 2)
    too_few = _tooltip(combo, 3)
    assert "57" in too_many
    assert str(MAX_GROUPS) in too_many
    assert "1" in too_few
    assert str(MIN_GROUPS) in too_few
    assert too_many != too_few
    assert _tooltip(combo, 0) is None


def test_select_picks_the_requested_eligible_column():
    combo = ColumnComboBox()
    combo.set_columns(["a", "b"], [_TOO_MANY], select="b")

    assert combo.current_column() == "b"


def test_selecting_an_excluded_or_unknown_column_falls_back_to_the_first_eligible():
    combo = ColumnComboBox()

    combo.set_columns(["a", "b"], [_TOO_MANY], select="id")
    assert combo.current_column() == "a"

    combo.set_columns(["a", "b"], [_TOO_MANY], select="missing")
    assert combo.current_column() == "a"


def test_no_eligible_columns_means_no_selection_even_with_excluded_items():
    combo = ColumnComboBox()
    combo.set_columns([], [_TOO_MANY])

    assert combo.currentIndex() == -1
    assert combo.current_column() == ""
    assert combo.eligible_columns() == ()


def test_current_column_ignores_a_programmatically_selected_disabled_item():
    combo = ColumnComboBox()
    combo.set_columns(["a"], [_TOO_MANY])

    combo.setCurrentIndex(2)  # "id", disabled

    assert combo.currentText() == "id"
    assert combo.current_column() == ""


def test_set_columns_replaces_previous_items():
    combo = ColumnComboBox()
    combo.set_columns(["a", "b"], [_TOO_MANY])

    combo.set_columns(["c"])

    assert _items(combo) == ["c"]
    assert combo.eligible_columns() == ("c",)
    assert combo.current_column() == "c"
