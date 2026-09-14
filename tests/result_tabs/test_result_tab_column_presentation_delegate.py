from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QStandardItemModel
from PyQt6.QtWidgets import QStyleOptionViewItem

from expo_jbm329.workbench.controllers.result_tabs.result_tab_column_presentation_delegate import (
    ResultTabColumnPresentationDelegate,
)


def test_delegate_formats_value_and_handles_missing():
    model = QStandardItemModel(1, 1)
    index = model.index(0, 0)
    delegate = ResultTabColumnPresentationDelegate(
        semantics_by_column_index={0: None},
    )
    option = QStyleOptionViewItem()

    model.setData(index, "x", Qt.ItemDataRole.EditRole)
    delegate.initStyleOption(option, index)
    assert option.text == "x"
