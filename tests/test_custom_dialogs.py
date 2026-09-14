import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget

from expo_jbm329.gui.dialogs.workflows.concat.concat_dialog import (
    ConcatDialog,
    ConcatDialogResult,
)
from expo_jbm329.gui.dialogs.workflows.join.join_dialog import (
    JoinDialog,
    JoinDialogResult,
)

@pytest.fixture
def parent_widget(qt_app):
    return QWidget()

def test_concat_dialog_initialization(parent_widget):
    left_tab = "Left"
    right_tabs = ["Right1", "Right2"]
    left_cols = ["col1", "col2"]
    right_cols_map = {
        "Right1": ["r1_c1"],
        "Right2": ["r2_c1", "r2_c2"]
    }
    
    dialog = ConcatDialog(
        parent=parent_widget,
        left_tab_title=left_tab,
        right_tab_titles=right_tabs,
        left_columns=left_cols,
        right_columns_map=right_cols_map
    )
    
    assert dialog.cb_left_dataset.currentText() == "Left"
    assert dialog.cb_right_dataset.currentText() == "Right1"
    assert dialog.left_columns_list.count() == 2
    assert dialog.right_columns_list.count() == 1

    dialog.cb_right_dataset.setCurrentText("Right2")
    assert dialog.right_columns_list.count() == 2

    result = dialog.build_result()
    assert isinstance(result, ConcatDialogResult)
    assert result.left_tab_title == "Left"
    assert result.right_tab_title == "Right2"
    assert result.remove_duplicates is False


def test_join_dialog_initialization(parent_widget):
    all_tabs = ["Left", "Right"]
    columns_for_tab = {
        "Left": ["id", "val1"],
        "Right": ["id", "val2"]
    }
    joinable_map = {
        ("Left", "id", "Right"): {"id"},
        ("Right", "id", "Left"): {"id"},
    }

    dialog = JoinDialog(
        parent=parent_widget,
        all_tab_titles=all_tabs,
        left_initial="Left",
        get_columns_for_tab=columns_for_tab,
        joinable_map=joinable_map,
    )

    assert dialog._left.cb_dataset.currentText() == "Left"
    assert dialog._right.cb_dataset.currentText() == "Right"
    assert dialog._left.cb_key.currentText() == "id"
    assert dialog._right.cb_key.currentText() == "id"
    assert dialog._left.columns_list.count() == 2
    assert dialog._right.columns_list.count() == 2

    left_item = dialog._left.columns_list.item(1)
    right_item = dialog._right.columns_list.item(1)
    assert left_item is not None
    assert right_item is not None
    left_item.setCheckState(Qt.CheckState.Unchecked)
    right_item.setCheckState(Qt.CheckState.Unchecked)

    result = dialog.build_result()
    assert isinstance(result, JoinDialogResult)
    assert result.left_tab_title == "Left"
    assert result.right_tab_title == "Right"
    assert result.left_on == ["id"]
    assert result.right_on == ["id"]
    assert result.left_selected_columns == ["id"]
    assert result.right_selected_columns == ["id"]
    assert result.join_type == "inner"


def test_join_dialog_updates_join_type(parent_widget):
    all_tabs = ["Left", "Right"]
    columns_for_tab = {
        "Left": ["id"],
        "Right": ["id"],
    }
    joinable_map = {
        ("Left", "id", "Right"): {"id"},
    }

    dialog = JoinDialog(
        parent=parent_widget,
        all_tab_titles=all_tabs,
        left_initial="Left",
        get_columns_for_tab=columns_for_tab,
        joinable_map=joinable_map,
    )

    dialog.rb_left.setChecked(True)
    result = dialog.build_result()

    assert result.join_type == "left"
