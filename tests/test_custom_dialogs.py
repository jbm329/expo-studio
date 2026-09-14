import pytest
from PyQt6.QtWidgets import QWidget
from gui.dialogs.workflows.concat.concat_dialog import ConcatDialog, ConcatDialogResult
from gui.dialogs.workflows.join.join_dialog import JoinDialog, JoinDialogResult

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
    
    # Check column counts
    assert dialog.left_columns_list.count() == 2
    assert dialog.right_columns_list.count() == 1
    
    # Change selection
    dialog.cb_right_dataset.setCurrentText("Right2")
    assert dialog.right_columns_list.count() == 2
    
    # Build result
    result = dialog.build_result()
    assert isinstance(result, ConcatDialogResult)
    assert result.left_tab_title == "Left"
    assert result.right_tab_title == "Right2"

def test_join_dialog_initialization(parent_widget):
    all_tabs = ["Left", "Right"]
    left_initial = "Left"
    columns_for_tab = {
        "Left": ["id", "val1"],
        "Right": ["id", "val2"]
    }
    dtypes_for_tab = {
        "Left": {"id": "int64", "val1": "object"},
        "Right": {"id": "int64", "val2": "object"}
    }
    
    dialog = JoinDialog(
        parent=parent_widget,
        all_tab_titles=all_tabs,
        left_initial=left_initial,
        get_columns_for_tab=columns_for_tab,
        dtypes_for_tab=dtypes_for_tab
    )
    
    assert dialog.cb_left_dataset.currentText() == "Left"
    assert dialog.cb_right_dataset.currentText() == "Right"
    
    # Check current selection (it might auto-select first available if they match)
    # The test showed it auto-selected 'id'
    assert dialog.cb_left_key.currentText() == "id"
    assert dialog.cb_right_key.currentText() == "id"
    
    # Select keys (re-select to be sure)
    dialog.cb_left_key.setCurrentText("id")
    dialog.cb_right_key.setCurrentText("id")
    
    # Select columns to keep
    # In JoinDialog, _populate_left_side/_populate_right_side create QListWidgetItems with checkboxes
    # (assuming they have checkboxes based on _get_checked and previous knowledge of such dialogs)
    # Let's check if the list widgets are populated
    assert dialog.left_columns_list.count() == 2
    assert dialog.right_columns_list.count() == 2
    
    # Build result
    result = dialog.build_result()
    assert isinstance(result, JoinDialogResult)
    assert result.left_tab_title == "Left"
    assert result.right_tab_title == "Right"
    assert result.left_on == ["id"]
    assert result.right_on == ["id"]
    assert result.join_type == "inner"  # default
