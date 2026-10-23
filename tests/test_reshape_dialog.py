from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from PyQt6.QtCore import Qt, QTranslator
from PyQt6.QtWidgets import QComboBox, QDialogButtonBox, QGroupBox

from expo_jbm329.gui.dialogs.workflows.reshape.reshape_dialog import ReshapeDialog
from expo_jbm329.utils.dataset_ref import DatasetRef
from expo_jbm329.utils.format_utils import fmt_int
from expo_jbm329.utils.i18n_utils import translate


def make_dialog(
    columns: tuple[object, ...] = ("PatientId", "VisitId", "Value"),
    numeric_positions: tuple[int, ...] = (0, 2),
) -> ReshapeDialog:
    return ReshapeDialog(
        parent=None,
        source_dataset=DatasetRef("source", "Source <dataset>", 1234, len(columns)),
        source_columns=columns,
        source_dtypes=tuple("int64" if position in numeric_positions else "string" for position in range(len(columns))),
        numeric_column_positions=numeric_positions,
    )


def test_fixed_title_dimensions_and_ui_only_preview():
    dialog = make_dialog()
    assert dialog.windowTitle() == f"Reshape — Source <dataset> ({fmt_int(1234)} rows × {fmt_int(3)} columns)"
    assert dialog.windowFlags() & Qt.WindowType.WindowMaximizeButtonHint
    assert not dialog.windowFlags() & Qt.WindowType.WindowMinimizeButtonHint
    assert dialog.dimensions.count() == 3
    for position in range(dialog.dimensions.count()):
        item = dialog.dimensions.item(position)
        assert item.checkState() == Qt.CheckState.Unchecked
        assert item.data(Qt.ItemDataRole.UserRole) == position
    dialog.dimensions.item(0).setCheckState(Qt.CheckState.Checked)
    assert dialog.dimensions.item(0).checkState() == Qt.CheckState.Checked
    assert dialog.preview_placeholder.text() == ("A five-row output preview will be available here in a later step.")
    assert not dialog.apply_button.isEnabled()
    assert "UI only" in dialog.apply_button.toolTip()
    dialog.close()


def test_metrics_edit_add_remove_and_column_identity():
    long_name = "A very long source column name " * 10
    dialog = make_dialog((1, "1", long_name))
    metrics = dialog.metrics
    assert metrics.rowCount() == 1
    assert not dialog.remove_metric_button.isEnabled()
    functions = metrics.cellWidget(0, 1)
    assert isinstance(functions, QComboBox)
    assert [functions.itemData(index) for index in range(functions.count())] == [
        "SUM",
        "AVG",
        "COUNT",
        "COUNT DISTINCT",
        "MAX",
        "MIN",
    ]
    assert functions.currentData() == "SUM"
    functions.setCurrentText("COUNT")
    columns = metrics.cellWidget(0, 2)
    assert isinstance(columns, QComboBox)
    assert columns.currentData() is None
    assert [columns.itemData(index) for index in range(1, columns.count())] == [0, 1, 2]
    assert columns.itemData(3, Qt.ItemDataRole.ToolTipRole) == long_name
    columns.setCurrentIndex(3)
    assert columns.toolTip() == long_name
    assert dialog.dimensions.item(2).toolTip() == f"{long_name}\nint64"
    metrics.item(0, 0).setText("Distinct visits")
    functions.setCurrentText("COUNT DISTINCT")
    columns.setCurrentIndex(2)
    condition = "yrkesroll = 'Läkare' AND Hallänning = 1"
    metrics.item(0, 3).setText(condition)
    assert metrics.item(0, 3).text() == condition
    assert "Not validated or executed" in metrics.item(0, 3).toolTip()
    dialog.add_metric_button.click()
    assert metrics.rowCount() == 2
    assert metrics.item(1, 0).text() == ""
    assert metrics.item(1, 3).text() == ""
    metrics.selectRow(0)
    assert dialog.remove_metric_button.isEnabled()
    dialog.remove_metric_button.click()
    assert metrics.rowCount() == 1
    assert metrics.item(0, 0).text() == ""
    metrics.selectRow(0)
    dialog.remove_metric_button.click()
    assert metrics.rowCount() == 0
    assert not dialog.remove_metric_button.isEnabled()
    assert not dialog.apply_button.isEnabled()
    dialog.add_metric_button.click()
    assert metrics.rowCount() == 1
    dialog.close()


def test_remove_multiple_selected_metrics_and_reopen_discards_configuration():
    dialog = make_dialog()
    dialog.add_metric_button.click()
    dialog.add_metric_button.click()
    dialog.metrics.selectAll()
    dialog.remove_metric_button.click()
    assert dialog.metrics.rowCount() == 0
    dialog.close()
    reopened = make_dialog()
    assert reopened.metrics.rowCount() == 1
    assert reopened.metrics.item(0, 0).text() == ""
    assert reopened.metrics.item(0, 3).text() == ""
    assert not reopened.apply_button.isEnabled()
    reopened.close()


def test_empty_source_and_close_button():
    dialog = make_dialog((), ())
    assert dialog.dimensions.count() == 0
    columns = dialog.metrics.cellWidget(0, 2)
    assert isinstance(columns, QComboBox)
    assert columns.count() == 1
    assert not dialog.apply_button.isEnabled()
    buttons = dialog.findChild(QDialogButtonBox)
    assert buttons is not None
    close_button = buttons.button(QDialogButtonBox.StandardButton.Close)
    assert close_button is not None
    closed: list[bool] = []
    dialog.rejected.connect(lambda: closed.append(True))
    close_button.click()
    assert closed == [True]


@pytest.mark.parametrize("language", ["en", "sv", "de", "fr", "it", "es", "pl"])
def test_compiled_reshape_translations(qt_app, language):
    translator = QTranslator()
    catalog = Path(__file__).parents[1] / "src" / "expo_jbm329" / "i18n" / "locales" / f"app_{language}.qm"
    assert translator.load(str(catalog))
    qt_app.installTranslator(translator)
    try:
        dialog = make_dialog()
        source_title = "Reshape — {dataset} ({rows} rows × {columns} columns)"
        title = translate("ReshapeDialog", source_title)
        assert dialog.windowTitle() == title.format(dataset="Source <dataset>", rows=fmt_int(1234), columns=fmt_int(3))
        if language != "en":
            assert title != source_title
            assert dialog.apply_button.text() != "Apply"
            assert dialog.preview_placeholder.text() != (
                "A five-row output preview will be available here in a later step."
            )
            for context, source in (
                ("ToolbarController", "Reshape"),
                ("ResultTabManager", "Reshape…"),
                ("ReshapeController", "Reshape unavailable"),
                ("ReshapeController", "Select a ready result dataset before opening Reshape."),
            ):
                assert translate(context, source) != source
            assert "Metrics" not in [box.title() for box in dialog.findChildren(QGroupBox)]
            assert dialog.source_column_guidance.text() != translate_guidance_source()
            assert dialog.dimension_search.placeholderText() != "Search dimensions"
        dialog.close()
    finally:
        qt_app.removeTranslator(translator)


@pytest.mark.parametrize("language", ["en", "sv", "de", "fr", "it", "es", "pl"])
def test_reshape_catalog_entries_are_complete_and_preserve_placeholders(language):
    catalog = Path(__file__).parents[1] / "src" / "expo_jbm329" / "i18n" / "locales" / f"app_{language}.ts"
    root = ET.parse(catalog).getroot()
    checked = 0
    for context in root.findall("context"):
        name = context.findtext("name")
        for message in context.findall("message"):
            source = message.findtext("source", "")
            if name not in {"ReshapeDialog", "ReshapeController"} and (name, source) not in {
                ("ToolbarController", "Reshape"),
                ("ResultTabManager", "Reshape…"),
            }:
                continue
            translation = message.find("translation")
            assert translation is not None
            if language == "en":
                assert translation.get("type") == "unfinished"
                assert not translation.text
            else:
                assert translation.get("type") is None
                assert translation.text
                for placeholder in ("{dataset}", "{rows}", "{columns}"):
                    assert source.count(placeholder) == translation.text.count(placeholder)
            checked += 1
    assert checked == 21


def test_dimension_search_preserves_checks_order_and_identity():
    dialog = make_dialog(("PatientId", "Clinic", "PATIENT code", 1, "1"), (0, 3))
    assert [dialog.dimensions.item(i).text() for i in range(5)] == [
        "PatientId [int64]",
        "Clinic [string]",
        "PATIENT code [string]",
        "1 [int64]",
        "1 [string]",
    ]
    dialog.dimensions.item(0).setCheckState(Qt.CheckState.Checked)
    dialog.dimensions.item(1).setCheckState(Qt.CheckState.Checked)
    dialog.dimension_search.setText("pAtIeNt")
    assert [dialog.dimensions.item(i).isHidden() for i in range(5)] == [False, True, False, True, True]
    assert dialog.dimensions.item(1).checkState() == Qt.CheckState.Checked
    dialog.dimension_search.setText("int64")
    assert all(dialog.dimensions.item(i).isHidden() for i in range(5))
    dialog.dimension_search.setText("1")
    assert [dialog.dimensions.item(i).isHidden() for i in range(5)] == [True, True, True, False, False]
    assert dialog.dimensions.item(3).data(Qt.ItemDataRole.UserRole) == 3
    assert dialog.dimensions.item(4).data(Qt.ItemDataRole.UserRole) == 4
    dialog.dimension_search.clear()
    assert all(not dialog.dimensions.item(i).isHidden() for i in range(5))
    assert dialog.dimensions.item(0).checkState() == Qt.CheckState.Checked
    assert dialog.dimensions.item(1).checkState() == Qt.CheckState.Checked
    assert not dialog.apply_button.isEnabled()
    dialog.close()


def test_dimension_search_handles_empty_source():
    dialog = make_dialog((), ())
    dialog.dimension_search.setText("anything")
    assert dialog.dimensions.count() == 0
    dialog.dimension_search.clear()
    dialog.close()


def test_dimension_dtype_metadata_must_match_columns():
    with pytest.raises(ValueError, match="Source dtype metadata"):
        ReshapeDialog(
            parent=None,
            source_dataset=DatasetRef("source", "Source", 1, 1),
            source_columns=("a",),
            source_dtypes=(),
            numeric_column_positions=(),
        )


def translate_guidance_source() -> str:
    return (
        "SUM, AVG, MAX and MIN accept integer and floating-point columns only. "
        "COUNT and COUNT DISTINCT accept any column. "
        "Changing the function clears an incompatible source selection."
    )


def metric_controls(dialog, row=0):
    functions = dialog.metrics.cellWidget(row, 1)
    columns = dialog.metrics.cellWidget(row, 2)
    assert isinstance(functions, QComboBox)
    assert isinstance(columns, QComboBox)
    return functions, columns


def offered_positions(columns):
    return [columns.itemData(index) for index in range(1, columns.count())]


@pytest.mark.parametrize("function", ["SUM", "AVG", "MAX", "MIN", "COUNT", "COUNT DISTINCT"])
def test_function_filters_source_columns_without_changing_dimensions(function):
    dialog = make_dialog()
    functions, columns = metric_controls(dialog)
    assert offered_positions(columns) == [0, 2]
    assert columns.currentData() is None
    functions.setCurrentText(function)
    assert offered_positions(columns) == ([0, 1, 2] if function.startswith("COUNT") else [0, 2])
    assert columns.currentData() is None
    assert [dialog.dimensions.item(i).data(Qt.ItemDataRole.UserRole) for i in range(3)] == [0, 1, 2]
    assert not dialog.apply_button.isEnabled()
    dialog.close()


def test_switch_preserves_eligible_selection_and_clears_incompatible_selection():
    dialog = make_dialog((1, "1", "duplicate", "duplicate"), (0, 3))
    functions, columns = metric_controls(dialog)
    assert offered_positions(columns) == [0, 3]
    columns.setCurrentIndex(columns.findData(0))
    for function in ("AVG", "COUNT", "MAX", "MIN", "COUNT DISTINCT", "SUM"):
        functions.setCurrentText(function)
        assert columns.currentData() == 0
        assert columns.toolTip() == "1"
    functions.setCurrentText("COUNT")
    columns.setCurrentIndex(columns.findData(1))
    functions.setCurrentText("AVG")
    assert columns.currentData() is None
    assert columns.currentIndex() == 0
    assert columns.toolTip() == "Select column"
    functions.setCurrentText("COUNT DISTINCT")
    assert columns.currentData() is None
    columns.setCurrentIndex(columns.findData(3))
    functions.setCurrentText("SUM")
    assert columns.currentData() == 3
    assert columns.currentText() == "duplicate"
    assert offered_positions(columns) == [0, 3]
    dialog.close()


@pytest.mark.parametrize("source_columns", [(), ("text", "flag")])
def test_no_numeric_columns_still_allows_count_functions(source_columns):
    dialog = make_dialog(source_columns, ())
    functions, columns = metric_controls(dialog)
    assert functions.isEnabled()
    for function in ("SUM", "AVG", "MIN", "MAX"):
        functions.setCurrentText(function)
        assert offered_positions(columns) == []
        assert columns.currentIndex() == 0
    for function in ("COUNT", "COUNT DISTINCT"):
        functions.setCurrentText(function)
        assert offered_positions(columns) == list(range(len(source_columns)))
    assert not dialog.apply_button.isEnabled()
    dialog.close()


def test_metric_callbacks_remain_independent_after_removing_earlier_row():
    dialog = make_dialog()
    dialog.add_metric_button.click()
    dialog.add_metric_button.click()
    first_function, first_columns = metric_controls(dialog)
    middle_function, middle_columns = metric_controls(dialog, 1)
    last_function, last_columns = metric_controls(dialog, 2)
    first_columns.setCurrentIndex(first_columns.findData(0))
    middle_function.setCurrentText("COUNT")
    middle_columns.setCurrentIndex(middle_columns.findData(1))
    dialog.metrics.item(1, 0).setText("Named metric")
    dialog.metrics.item(1, 3).setText("Value > 0")
    dialog.dimensions.item(1).setCheckState(Qt.CheckState.Checked)
    last_columns.setCurrentIndex(last_columns.findData(2))
    assert first_function.currentText() == "SUM"
    assert last_function.currentText() == "SUM"

    dialog.metrics.selectRow(0)
    dialog.remove_metric_button.click()
    middle_function.setCurrentText("AVG")
    assert middle_columns.currentData() is None
    assert last_columns.currentData() == 2
    assert offered_positions(last_columns) == [0, 2]
    assert dialog.metrics.item(0, 0).text() == "Named metric"
    assert dialog.metrics.item(0, 3).text() == "Value > 0"
    assert dialog.dimensions.item(1).checkState() == Qt.CheckState.Checked
    last_function.setCurrentText("COUNT DISTINCT")
    assert last_columns.currentData() == 2
    assert offered_positions(last_columns) == [0, 1, 2]
    assert offered_positions(middle_columns) == [0, 2]

    dialog.add_metric_button.click()
    new_function, new_columns = metric_controls(dialog, 2)
    assert new_function.currentText() == "SUM"
    assert offered_positions(new_columns) == [0, 2]
    assert new_columns.currentData() is None
    assert not dialog.apply_button.isEnabled()
    dialog.close()
