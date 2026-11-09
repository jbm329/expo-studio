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
    right_cols_map = {"Right1": ["r1_c1"], "Right2": ["r2_c1", "r2_c2"]}

    dialog = ConcatDialog(
        parent=parent_widget,
        left_tab_title=left_tab,
        right_tab_titles=right_tabs,
        left_columns=left_cols,
        right_columns_map=right_cols_map,
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
    columns_for_tab = {"Left": ["id", "val1"], "Right": ["id", "val2"]}
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
    assert dialog._left.columns_table.rowCount() == 2
    assert dialog._right.columns_table.rowCount() == 2

    left_item = dialog._left.columns_table.item(1, 0)
    right_item = dialog._right.columns_table.item(1, 0)
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


def test_join_column_table_types_selection_and_resizing(parent_widget) -> None:
    columns = {"Left": ["value", "id"], "Right": ["flag", "id"]}
    dialog = JoinDialog(
        parent_widget,
        all_tab_titles=list(columns),
        left_initial="Left",
        get_columns_for_tab=columns,
        joinable_map={("Left", "id", "Right"): {"id"}},
        column_dtypes_for_tab={
            "Left": {"id": "Int64", "value": "float64"},
            "Right": {"id": "Int64", "flag": "boolean"},
        },
    )
    table = dialog._left.columns_table
    assert table.columnCount() == 2
    assert table.item(0, 0).text() == "id"
    assert table.item(0, 1).text() == "Int64"
    assert table.item(1, 1).text() == "float64"
    assert not table.item(1, 1).flags() & Qt.ItemFlag.ItemIsEditable
    table.item(1, 0).setCheckState(Qt.CheckState.Unchecked)
    assert dialog._left.cb_select_all.checkState() == Qt.CheckState.PartiallyChecked
    dialog._left.cb_select_all.click()
    assert dialog.build_result().left_selected_columns == ["id", "value"]
    dialog._left.cb_select_all.click()
    result = dialog.build_result()
    assert result.left_selected_columns == []
    assert result.left_on == ["id"]
    assert result.left_fill == {}
    assert result.right_fill == {}
    assert dialog._left.cb_select_all.checkState() == Qt.CheckState.Unchecked
    assert dialog.maximumWidth() > dialog.minimumWidth()
    dialog.resize(950, 650)
    assert dialog.width() == 950
    assert dialog.height() == 650


def test_join_column_table_reloads_dtypes_on_dataset_change(parent_widget) -> None:
    columns = {"Left": ["id", "value"], "Right": ["id", "flag"], "Third": ["id", "date"]}
    dialog = JoinDialog(
        parent_widget,
        all_tab_titles=list(columns),
        left_initial="Left",
        get_columns_for_tab=columns,
        joinable_map={("Left", "id", "Right"): {"id"}, ("Left", "id", "Third"): {"id"}},
        column_dtypes_for_tab={"Right": {"flag": "boolean"}, "Third": {"date": "datetime64[ns]"}},
    )
    table = dialog._right.columns_table
    assert table.item(0, 0).text() == "flag"
    assert table.item(0, 1).text() == "boolean"
    table.item(0, 0).setCheckState(Qt.CheckState.Unchecked)
    dialog._right.cb_dataset.setCurrentText("Third")
    assert table.rowCount() == 2
    assert table.item(0, 0).text() == "date"
    assert table.item(0, 1).text() == "datetime64[ns]"
    assert table.item(1, 1).text() == "-"
    assert dialog._right.cb_select_all.checkState() == Qt.CheckState.Checked
    assert dialog.build_result().right_selected_columns == ["date", "id"]


@pytest.mark.parametrize(
    "widget_language,headers",
    [
        ("en", ("Column", "Type")),
        ("sv", ("Kolumn", "Typ")),
        ("de", ("Spalte", "Typ")),
        ("fr", ("Colonne", "Type")),
        ("it", ("Colonna", "Tipo")),
        ("es", ("Columna", "Tipo")),
        ("pl", ("Kolumna", "Typ")),
    ],
    indirect=["widget_language"],
)
def test_join_column_table_translated_headers(parent_widget, widget_language: str, headers: tuple[str, str]) -> None:
    dialog = JoinDialog(
        parent_widget,
        all_tab_titles=["Left", "Right"],
        left_initial="Left",
        get_columns_for_tab={"Left": ["id"], "Right": ["id"]},
        joinable_map={("Left", "id", "Right"): {"id"}},
    )
    for side in (dialog._left, dialog._right):
        assert tuple(side.columns_table.horizontalHeaderItem(i).text() for i in range(2)) == headers
