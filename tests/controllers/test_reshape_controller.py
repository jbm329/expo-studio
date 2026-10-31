from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest
from PyQt6.QtWidgets import QWidget

from expo_jbm329.gui.dialogs.service.dialog_service import DialogService
from expo_jbm329.gui.dialogs.workflows.reshape.condition_editor import ConditionEditor
from expo_jbm329.utils.dataset_ref import DatasetRef
from expo_jbm329.workbench.controllers import reshape_controller as module


def test_condition_controller_receives_shared_dialog_service(monkeypatch):
    conditions = MagicMock()
    monkeypatch.setattr(module, "ReshapeConditionController", conditions)
    dialogs = MagicMock(spec=DialogService)
    async_ops = MagicMock()
    logger = MagicMock()
    module.ReshapeController(
        parent_widget=QWidget(), results=MagicMock(), async_ops=async_ops, logger=logger, dialogs=dialogs
    )
    conditions.assert_called_once_with(async_ops, logger, dialogs=dialogs)


def test_open_captures_only_active_dataset_metadata_without_mutation(monkeypatch):
    dataframe = pd.DataFrame([[1, 2, 3]], columns=[1, "1", "value"])
    original = dataframe.copy(deep=True)
    record = SimpleNamespace(tab_id="stable-id", title="Source", is_ready=True, df=dataframe)
    results = MagicMock()
    results.active_tab_id.return_value = record.tab_id
    results.tabs_by_id = {record.tab_id: record, "other-id": object()}
    dialog_class = MagicMock()
    monkeypatch.setattr(module, "ReshapeDialog", dialog_class)
    parent = QWidget()
    controller = module.ReshapeController(parent_widget=parent, results=results, async_ops=MagicMock())

    controller.open_reshape_dialog()

    dialog_class.assert_called_once_with(
        parent=parent,
        source_dataset=DatasetRef("stable-id", "Source", 1, 3),
        source_columns=[1, "1", "value"],
        source_dtypes=["int64", "int64", "int64"],
        numeric_column_positions=(0, 1, 2),
        datetime_column_positions=(),
    )
    dialog_class.return_value.exec.assert_called_once_with()
    pd.testing.assert_frame_equal(dataframe, original)
    assert results.method_calls == [("active_tab_id", (), {})]


def test_open_passes_numeric_positions_from_dtype_metadata(monkeypatch):
    dataframe = pd.DataFrame({
        "text": pd.Series(["12", "34"], dtype="string"),
        "empty_numeric": pd.Series([None, None], dtype="Int64"),
        "flag": pd.Series([True, False], dtype="boolean"),
        "float": pd.Series([1.0, 2.0]),
        "date": pd.Series([pd.NaT, pd.NaT], dtype="datetime64[ns, UTC]"),
    })
    original = dataframe.copy(deep=True)
    results = MagicMock()
    results.active_tab_id.return_value = "source"
    results.tabs_by_id = {"source": SimpleNamespace(tab_id="source", title="Source", is_ready=True, df=dataframe)}
    dialog_class = MagicMock()
    monkeypatch.setattr(module, "ReshapeDialog", dialog_class)
    parent = QWidget()
    module.ReshapeController(parent_widget=parent, results=results, async_ops=MagicMock()).open_reshape_dialog()
    assert dialog_class.call_args.kwargs["numeric_column_positions"] == (1, 3)
    assert dialog_class.call_args.kwargs["datetime_column_positions"] == (4,)
    assert dialog_class.call_args.kwargs["source_dtypes"] == [str(dtype) for dtype in dataframe.dtypes]
    pd.testing.assert_frame_equal(dataframe, original)


@pytest.mark.parametrize("state", ["no-active", "removed", "pending", "no-data"])
def test_unavailable_source_warns_without_opening_dialog(monkeypatch, state, widget_language):
    results = MagicMock()
    results.active_tab_id.return_value = None if state == "no-active" else "source"
    record = SimpleNamespace(
        is_ready=state != "pending",
        df=None if state == "no-data" else pd.DataFrame({"a": [1]}),
    )
    results.tabs_by_id = {} if state in {"no-active", "removed"} else {"source": record}
    dialogs = MagicMock(spec=DialogService)
    dialog_class = MagicMock()
    monkeypatch.setattr(module, "ReshapeDialog", dialog_class)
    logger = MagicMock()
    parent = QWidget()
    controller = module.ReshapeController(
        parent_widget=parent, results=results, async_ops=MagicMock(), logger=logger, dialogs=dialogs
    )

    controller.open_reshape_dialog()

    dialogs.warn.assert_called_once_with(
        parent, controller._tr(controller.TR_UNAVAILABLE), controller._tr(controller.TR_READY_DATASET_REQUIRED)
    )
    logger.warning.assert_called_once()
    dialog_class.assert_not_called()


def test_condition_builder_keeps_original_source_after_active_tab_changes(monkeypatch):
    dataframe = pd.DataFrame({"original": [1]})
    results = MagicMock()
    results.active_tab_id.return_value = "source"
    results.tabs_by_id = {"source": SimpleNamespace(tab_id="source", title="Source", is_ready=True, df=dataframe)}
    parent = QWidget()
    controller = module.ReshapeController(parent_widget=parent, results=results, async_ops=MagicMock())
    condition_controller = MagicMock()
    controller._conditions = condition_controller
    editors = []

    def execute(dialog):
        results.active_tab_id.return_value = "other"
        results.tabs_by_id["source"].df = pd.DataFrame({"replacement": [2]})
        editor = dialog.metrics.cellWidget(0, 3)
        assert isinstance(editor, ConditionEditor)
        dialog.metrics.item(0, 0).setText("Total")
        dialog.metrics.cellWidget(0, 2).value.setCurrentIndex(1)
        editors.append(editor)
        editor.button.click()
        return 0

    monkeypatch.setattr(module.ReshapeDialog, "exec", execute)
    controller.open_reshape_dialog()
    assert condition_controller.open_dialog.call_count == 1
    args = condition_controller.open_dialog.call_args.args
    assert args[1] is editors[0]
    assert args[2] is dataframe
    results.active_tab_id.assert_called_once()
