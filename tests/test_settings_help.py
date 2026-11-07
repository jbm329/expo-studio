from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pandas as pd
import pytest
from PyQt6.QtCore import QEvent, Qt, QTimer, QTranslator, QUrl
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QLabel, QLineEdit, QMainWindow, QPushButton

from expo_jbm329.app.help_topics import HelpTopic
from expo_jbm329.app.settings import rest_connection_editor, settings_editor
from expo_jbm329.app.settings.config_store import (
    load_settings,
    read_connections,
    read_log_config,
    read_rest_connections,
)
from expo_jbm329.app.settings.connection_editor import ConnectionEditor
from expo_jbm329.app.settings.log_config_editor import LogConfigEditor
from expo_jbm329.app.settings.rest_connection_editor import RestConnectionEditor
from expo_jbm329.app.settings.settings_editor import SettingsEditor
from expo_jbm329.gui.dialogs.rest import scb_browser_dialog
from expo_jbm329.gui.dialogs.rest.scb_browser_dialog import ScbBrowserDialog
from expo_jbm329.gui.dialogs.service.common.localization import localize_dialog_buttons
from expo_jbm329.gui.dialogs.service.dialog_service import DialogService
from expo_jbm329.gui.dialogs.workflows.concat.concat_dialog import ConcatDialog
from expo_jbm329.gui.dialogs.workflows.derived_column.derived_column_dialog import DerivedColumnDialog
from expo_jbm329.gui.dialogs.workflows.derived_column.formula_editor import FormulaEditor
from expo_jbm329.gui.dialogs.workflows.join.join_dialog import JoinDialog
from expo_jbm329.gui.dialogs.workflows.join.join_preview_dialog import JoinPreviewDialog
from expo_jbm329.gui.dialogs.workflows.reshape.condition_dialog import ConditionDialog
from expo_jbm329.gui.dialogs.workflows.reshape.condition_editor import ConditionEditor
from expo_jbm329.gui.dialogs.workflows.reshape.metric_source_cell import MetricSourceCell
from expo_jbm329.gui.dialogs.workflows.reshape.reshape_dialog import ReshapeDialog
from expo_jbm329.services.data_operations.derived_column.derived_column_service import (
    DerivedColumnSpec,
    validate_derived_column_spec,
)
from expo_jbm329.services.data_operations.joins import JoinMetadata
from expo_jbm329.services.data_operations.reshape_condition_values import ValuePage
from expo_jbm329.services.data_operations.reshape_conditions import (
    ConditionColumn,
    ConditionGroup,
    ConditionMatch,
    ConditionOperator,
    ConditionRule,
    ConditionValue,
)
from expo_jbm329.services.data_operations.reshape_preview import ReshapePreview
from expo_jbm329.services.rest.scb.browser import ScbTableMetadata, ScbTableSummary, ScbVariable, ScbVariableValue
from expo_jbm329.utils.dataset_ref import DatasetRef
from expo_jbm329.workbench.controllers.menu_controller import MenuController

if TYPE_CHECKING:
    from collections.abc import Iterator

    from expo_jbm329.services.data_operations.derived_column.derived_column_parser import FormulaValidationResult

HELP_LABELS = {"en": "Help", "sv": "Hjälp", "de": "Hilfe", "fr": "Aide", "it": "Aiuto", "es": "Ayuda", "pl": "Pomoc"}
type SettingsHelpDialog = (
    SettingsEditor
    | LogConfigEditor
    | ConnectionEditor
    | RestConnectionEditor
    | ScbBrowserDialog
    | JoinDialog
    | JoinPreviewDialog
    | ConcatDialog
    | DerivedColumnDialog
    | ReshapeDialog
    | ConditionDialog
)


@pytest.fixture(autouse=True)
def offline_scb_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    metadata = ScbTableMetadata(
        table_id="sample",
        label="Sample table",
        variables=(
            ScbVariable(
                name="Region",
                label="Region",
                display_name="Region",
                values=(ScbVariableValue(code="01", label="First"), ScbVariableValue(code="02", label="Second")),
            ),
        ),
    )
    monkeypatch.setattr(
        scb_browser_dialog, "fetch_scb_tables", MagicMock(return_value=[ScbTableSummary("sample", "Sample")])
    )
    monkeypatch.setattr(scb_browser_dialog, "fetch_scb_table_metadata", MagicMock(return_value=metadata))


@pytest.fixture(params=list(HELP_LABELS))
def help_language(request: pytest.FixtureRequest, qt_app: QApplication) -> Iterator[str]:
    language = str(request.param)
    translator = QTranslator()
    catalog = Path(__file__).resolve().parents[1] / "src" / "expo_jbm329" / "i18n" / "locales" / f"app_{language}.qm"
    assert translator.load(str(catalog))
    qt_app.installTranslator(translator)
    try:
        yield language
    finally:
        qt_app.removeTranslator(translator)


def _settings_dialog(dialogs: MagicMock, parent: QMainWindow | None = None) -> SettingsEditor:
    highlighter = MagicMock()
    highlighter.available_themes_with_labels.return_value = [("system", "System")]
    return SettingsEditor(
        parent=parent, dialogs=dialogs, file_dialogs=MagicMock(), highlighter_theme_service=highlighter
    )


@pytest.fixture(
    params=[
        HelpTopic.GENERAL_SETTINGS,
        HelpTopic.LOG_SETTINGS,
        HelpTopic.DATABASE_CONNECTIONS,
        HelpTopic.REST_API_CONNECTIONS,
        HelpTopic.SCB_QUERY_BUILDER,
        HelpTopic.JOIN_DATASETS,
        HelpTopic.JOIN_PREVIEW,
        HelpTopic.CONCATENATE_DATASETS,
        HelpTopic.DERIVED_COLUMNS,
        HelpTopic.RESHAPE,
        HelpTopic.RESHAPE_CONDITION_BUILDER,
    ],
    ids=[
        "general",
        "log",
        "database",
        "rest",
        "scb",
        "join",
        "join-preview",
        "concat",
        "derived",
        "reshape",
        "condition",
    ],
)
def help_topic(request: pytest.FixtureRequest) -> HelpTopic:
    topic = request.param
    assert isinstance(topic, HelpTopic)
    return topic


def _dialog_for_topic(topic: HelpTopic, dialogs: MagicMock, parent: QMainWindow | None = None) -> SettingsHelpDialog:
    if topic is HelpTopic.RESHAPE_CONDITION_BUILDER:
        column = ConditionColumn(0, "Product", True)
        return ConditionDialog(
            parent=parent,
            dialogs=dialogs,
            columns=[column],
            initial=ConditionGroup((ConditionRule(column, ConditionOperator.IS_NULL),)),
        )
    if topic is HelpTopic.RESHAPE:
        return ReshapeDialog(
            parent=parent,
            dialogs=dialogs,
            source_dataset=DatasetRef("source", "Sales", 2, 2),
            source_columns=["Region", "Amount"],
            source_dtypes=["string", "int64"],
            numeric_column_positions=[1],
            datetime_column_positions=[],
        )
    if topic is HelpTopic.DERIVED_COLUMNS:
        frame = pd.DataFrame({"Price": [12.5, 8.0], "Quantity": [2, 3]})

        def validate(name: str, formula: str) -> tuple[FormulaValidationResult, str]:
            result = validate_derived_column_spec(frame, DerivedColumnSpec(name, formula))
            return result, "Valid formula." if result.ok else "Invalid formula."

        return DerivedColumnDialog(df=frame, validate_callback=validate, parent=parent, dialogs=dialogs)
    if topic is HelpTopic.CONCATENATE_DATASETS:
        return ConcatDialog(
            parent=parent,
            dialogs=dialogs,
            left_tab_title="Left",
            right_tab_titles=["Right", "Other"],
            left_columns=["id", "value"],
            right_columns_map={"Right": ["id", "value"], "Other": ["id", "extra"]},
        )
    if topic is HelpTopic.JOIN_PREVIEW:
        return JoinPreviewDialog(
            parent,
            dialogs=dialogs,
            df=pd.DataFrame({"id": [1, 2], "join_status": ["both", "left_only"]}),
            metadata=JoinMetadata(0.5, 0.5, 0.0, "one-to-one", 2),
        )
    if topic is HelpTopic.JOIN_DATASETS:
        return JoinDialog(
            parent,
            dialogs=dialogs,
            all_tab_titles=["Left", "Right"],
            left_initial="Left",
            get_columns_for_tab={"Left": ["id", "value"], "Right": ["id", "value"]},
            joinable_map={("Left", "id", "Right"): {"id"}, ("Right", "id", "Left"): {"id"}},
        )
    if topic is HelpTopic.SCB_QUERY_BUILDER:
        return ScbBrowserDialog(parent=parent, dialogs=dialogs)
    if topic is HelpTopic.REST_API_CONNECTIONS:
        return RestConnectionEditor(parent=parent, dialogs=dialogs)
    if topic is HelpTopic.DATABASE_CONNECTIONS:
        return ConnectionEditor(parent=parent, dialogs=dialogs)
    if topic is HelpTopic.LOG_SETTINGS:
        return LogConfigEditor(parent=parent, dialogs=dialogs)
    assert topic is HelpTopic.GENERAL_SETTINGS
    return _settings_dialog(dialogs, parent)


def _help_button(dialog: SettingsHelpDialog) -> QPushButton:
    boxes = dialog.findChildren(QDialogButtonBox)
    boxes = [box for box in boxes if box.button(QDialogButtonBox.StandardButton.Help) is not None]
    assert len(boxes) == 1
    button = boxes[0].button(QDialogButtonBox.StandardButton.Help)
    assert button is not None
    assert boxes[0].buttonRole(button) == QDialogButtonBox.ButtonRole.HelpRole
    return button


def _derived_inputs(dialog: DerivedColumnDialog) -> tuple[QLineEdit, FormulaEditor]:
    name = dialog.findChild(QLineEdit)
    editor = dialog.findChild(FormulaEditor)
    assert name is not None
    assert editor is not None
    return name, editor


def _derived_action_button(dialog: DerivedColumnDialog, standard: QDialogButtonBox.StandardButton) -> QPushButton:
    buttons = [button for box in dialog.findChildren(QDialogButtonBox) if (button := box.button(standard)) is not None]
    assert len(buttons) == 1
    return buttons[0]


def _press_f1(app: QApplication, dialog: SettingsHelpDialog) -> None:
    app.processEvents()
    app.setActiveWindow(dialog)
    if isinstance(dialog, SettingsEditor):
        focus_widget = dialog.txt_documents_dir
    elif isinstance(dialog, LogConfigEditor):
        focus_widget = dialog.cb_logger_level
    elif isinstance(dialog, RestConnectionEditor):
        focus_widget = dialog.url_edit
    elif isinstance(dialog, ScbBrowserDialog):
        focus_widget = dialog.value_list
    elif isinstance(dialog, JoinDialog):
        focus_widget = dialog.rb_left
    elif isinstance(dialog, JoinPreviewDialog):
        focus_widget = _help_button(dialog)
    elif isinstance(dialog, ConcatDialog):
        focus_widget = dialog.cb_right_dataset
    elif isinstance(dialog, DerivedColumnDialog):
        _, focus_widget = _derived_inputs(dialog)
    elif isinstance(dialog, ReshapeDialog):
        condition = dialog.metrics.cellWidget(0, 3)
        assert isinstance(condition, ConditionEditor)
        focus_widget = condition.text
    elif isinstance(dialog, ConditionDialog):
        focus_widget = dialog.rules[0].column
    else:
        focus_widget = dialog.list_widget
    focus_widget.setFocus()
    assert app.activeWindow() is dialog
    assert app.focusWidget() is focus_widget
    for event_type in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
        app.sendEvent(focus_widget, QKeyEvent(event_type, Qt.Key.Key_F1, Qt.KeyboardModifier.NoModifier))


def test_standard_help_button_localizes_in_every_language(help_language: str) -> None:
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Help)
    localize_dialog_buttons(buttons)
    button = buttons.button(QDialogButtonBox.StandardButton.Help)
    assert button is not None
    assert button.text() == HELP_LABELS[help_language]


@pytest.mark.parametrize("opened", [True, False])
def test_settings_help_button_and_f1_preserve_edits(
    monkeypatch: pytest.MonkeyPatch, qt_app: QApplication, help_language: str, help_topic: HelpTopic, opened: bool
) -> None:
    urls: list[str] = []

    def open_url(url: QUrl) -> bool:
        urls.append(url.toString())
        return opened

    monkeypatch.setattr(settings_editor.QDesktopServices, "openUrl", open_url)
    fetch = MagicMock()
    monkeypatch.setattr(rest_connection_editor, "fetch_json", fetch)
    dialogs = MagicMock(spec=DialogService)
    changes = MagicMock()
    preview = MagicMock()
    join_before = None
    concat_before = None
    reshape_before = None
    reshape_revision = None
    condition_before = None
    persisted = None
    dialog = _dialog_for_topic(help_topic, dialogs)
    if isinstance(dialog, SettingsEditor):
        persisted = load_settings()
        dialog.spin_undo_limit.setValue(37)
    elif isinstance(dialog, LogConfigEditor):
        persisted = read_log_config()
        dialog.spin_file_backup.setValue(37)
    elif isinstance(dialog, (RestConnectionEditor, ScbBrowserDialog)):
        persisted = read_rest_connections()
    elif isinstance(dialog, JoinDialog):
        dialog.rb_left.setChecked(True)
        join_before = dialog.build_result()
        dialog.btn_preview.clicked.connect(preview)
    elif isinstance(dialog, JoinPreviewDialog):
        persisted = load_settings()
    elif isinstance(dialog, ConcatDialog):
        dialog.cb_right_dataset.setCurrentText("Other")
        concat_before = dialog.build_result()
    elif isinstance(dialog, DerivedColumnDialog):
        name, editor = _derived_inputs(dialog)
        name.setText("Line total")
        editor.setPlainText("[Price] * [Quantity]")
    elif isinstance(dialog, ReshapeDialog):
        _configure_reshape(dialog)
        reshape_before = dialog.capture_request()
        reshape_revision = dialog.revision
        dialog.preview_requested.connect(preview)
        dialog.configuration_changed.connect(changes)
    elif isinstance(dialog, ConditionDialog):
        condition_before = dialog.build_group()
        dialog.page_requested.connect(preview)
        dialog.request_invalidated.connect(changes)
    else:
        persisted = read_connections()
    try:
        dialog.show()
        dialog.activateWindow()
        qt_app.processEvents()
        if isinstance(dialog, ConnectionEditor):
            dialog.db_type_combo.setCurrentIndex(dialog.db_type_combo.findData("postgresql"))
            dialog.server_edit.setText("unsaved.example")
            dialog.connections_changed.connect(changes)
        elif isinstance(dialog, RestConnectionEditor):
            dialog.url_edit.setText("https://unsaved.example/api")
            dialog.connections_changed.connect(changes)
        elif isinstance(dialog, ScbBrowserDialog):
            dialog.select_all_button.click()
        help_button = _help_button(dialog)
        assert help_button.text() == HELP_LABELS[help_language]
        assert not help_button.autoDefault()
        assert not help_button.isDefault()
        if isinstance(dialog, (ConnectionEditor, RestConnectionEditor)):
            list_bottom = dialog.list_widget.mapTo(dialog, dialog.list_widget.rect().bottomLeft())
            help_top = help_button.mapTo(dialog, help_button.rect().topLeft())
            assert help_top.y() > list_bottom.y()
            assert help_top.x() == list_bottom.x()
            assert help_top.x() < dialog.btn_add.mapTo(dialog, dialog.btn_add.rect().topLeft()).x()
        elif isinstance(dialog, ScbBrowserDialog):
            assert dialog.variable_list.height() == dialog.value_list.height()
            assert dialog.variable_list.y() == dialog.value_list.y()
            help_top = help_button.mapTo(dialog, help_button.rect().topLeft())
            assert help_top.y() > dialog.selection_counter.y() + dialog.selection_counter.height()
            assert help_top.x() < dialog.apply_button.x()
        elif isinstance(dialog, JoinDialog):
            help_left = help_button.mapTo(dialog, help_button.rect().topLeft()).x()
            assert help_left < dialog.btn_preview.x() < dialog.btn_ok.x() < dialog.btn_cancel.x()
        elif isinstance(dialog, ReshapeDialog):
            help_left = help_button.mapTo(dialog, help_button.rect().topLeft()).x()
            preview_left = dialog.preview_button.x()
            ok_left = dialog.apply_button.mapTo(dialog, dialog.apply_button.rect().topLeft()).x()
            assert help_left < preview_left < ok_left
            assert preview_left - help_left > dialog.width() // 2
        elif isinstance(dialog, ConditionDialog):
            help_left = help_button.mapTo(dialog, help_button.rect().topLeft()).x()
            assert help_left < dialog.apply_button.mapTo(dialog, dialog.apply_button.rect().topLeft()).x()
        elif isinstance(dialog, JoinPreviewDialog):
            close_buttons = [
                button for button in dialog.findChildren(QPushButton) if button.text() == dialog.tr("Close")
            ]
            assert len(close_buttons) == 1
            assert help_button.mapTo(dialog, help_button.rect().topLeft()).x() < close_buttons[0].x()
        elif isinstance(dialog, (ConcatDialog, DerivedColumnDialog)):
            help_left = help_button.mapTo(dialog, help_button.rect().topLeft()).x()
            for box in dialog.findChildren(QDialogButtonBox):
                for standard in (QDialogButtonBox.StandardButton.Ok, QDialogButtonBox.StandardButton.Cancel):
                    button = box.button(standard)
                    if button is not None:
                        assert help_left < button.mapTo(dialog, button.rect().topLeft()).x()
        else:
            action_buttons = [
                button
                for button in dialog.findChildren(QPushButton)
                if button.text() in {dialog.tr("Reset defaults"), dialog.tr("Cancel"), dialog.tr("Save")}
            ]
            assert len(action_buttons) == 3
            help_left = help_button.mapTo(dialog, help_button.rect().topLeft()).x()
            assert all(button.mapTo(dialog, button.rect().topLeft()).x() > help_left for button in action_buttons)
        help_button.click()
        assert urls == [help_topic.url]
        _press_f1(qt_app, dialog)
        assert urls == [help_topic.url] * 2
        assert dialog.isVisible()
        if isinstance(dialog, SettingsEditor):
            assert dialog.spin_undo_limit.value() == 37
            assert load_settings() == persisted
        elif isinstance(dialog, LogConfigEditor):
            assert dialog.spin_file_backup.value() == 37
            assert read_log_config() == persisted
        elif isinstance(dialog, RestConnectionEditor):
            assert dialog.url_edit.text() == "https://unsaved.example/api"
            assert read_rest_connections() == persisted
            changes.assert_not_called()
        elif isinstance(dialog, ScbBrowserDialog):
            assert dialog.result_data is None
            assert dialog.apply_button.isEnabled()
            for row in range(dialog.value_list.count()):
                item = dialog.value_list.item(row)
                assert item is not None
                assert item.checkState() == Qt.CheckState.Checked
            assert read_rest_connections() == persisted
            assert dialog.variable_list.height() == dialog.value_list.height()
        elif isinstance(dialog, JoinDialog):
            assert dialog.build_result() == join_before
            preview.assert_not_called()
        elif isinstance(dialog, JoinPreviewDialog):
            assert dialog.model.rowCount() == 2
            assert dialog.model.columnCount() == 2
            assert dialog.analysis.pb_match.value() == 50
            assert dialog.analysis.pb_left.value() == 50
            assert dialog.analysis.pb_right.value() == 0
            assert load_settings() == persisted
        elif isinstance(dialog, ConcatDialog):
            assert dialog.build_result() == concat_before
            assert dialog.right_columns_list.count() == 2
        elif isinstance(dialog, DerivedColumnDialog):
            name, editor = _derived_inputs(dialog)
            assert name.text() == "Line total"
            assert editor.toPlainText() == "[Price] * [Quantity]"
            assert _derived_action_button(dialog, QDialogButtonBox.StandardButton.Ok).isEnabled()
            assert dialog.get_result() is None
        elif isinstance(dialog, ReshapeDialog):
            assert dialog.capture_request() == reshape_before
            assert dialog.revision == reshape_revision
            assert dialog.applied_request is None
            assert dialog.preview_button.isEnabled()
            assert dialog.apply_button.isEnabled()
            preview.assert_not_called()
            changes.assert_not_called()
        elif isinstance(dialog, ConditionDialog):
            assert dialog.build_group() == condition_before
            assert dialog.applied_group is None
            assert dialog.apply_button.isEnabled()
            preview.assert_not_called()
            changes.assert_not_called()
        else:
            assert dialog.server_edit.text() == "unsaved.example"
            assert read_connections() == persisted
            changes.assert_not_called()
        dialogs.info.assert_not_called()
        dialogs.critical.assert_not_called()
        fetch.assert_not_called()
        if opened:
            dialogs.warn.assert_not_called()
        else:
            assert dialogs.warn.call_count == 2
            dialogs.warn.assert_called_with(
                dialog,
                dialog.tr("Unable to open link"),
                dialog.tr("The user manual could not be opened.\n\n{url}").format(url=help_topic.url),
            )
            if help_language != "en":
                assert dialog.tr("Unable to open link") != "Unable to open link"
                assert dialog.tr("The user manual could not be opened.\n\n{url}") != (
                    "The user manual could not be opened.\n\n{url}"
                )
    finally:
        dialog.close()


def test_condition_default_width_preserves_nested_rules(qt_app: QApplication, help_language: str) -> None:
    column = ConditionColumn(0, "Product", True)
    group = ConditionGroup((
        ConditionGroup((ConditionRule(column, ConditionOperator.IS_NULL),), ConditionMatch.ANY),
        ConditionRule(column, ConditionOperator.IS_NOT_NULL),
    ))
    dialog = ConditionDialog(parent=None, columns=[column], initial=group)
    try:
        dialog.show()
        qt_app.processEvents()
        assert dialog.width() == 810
        assert dialog.build_group() == group
    finally:
        dialog.close()


@pytest.mark.parametrize("loading", [False, True])
def test_condition_help_preserves_rules_values_and_requests(
    monkeypatch: pytest.MonkeyPatch, qt_app: QApplication, loading: bool
) -> None:
    opener = MagicMock(return_value=True)
    monkeypatch.setattr(settings_editor.QDesktopServices, "openUrl", opener)
    column = ConditionColumn(0, "Product", True)
    selected = ConditionValue("string", "A")
    group = ConditionGroup((
        ConditionGroup((ConditionRule(column, ConditionOperator.IN, (selected,)),), ConditionMatch.ANY),
        ConditionRule(column, ConditionOperator.IS_NOT_NULL),
    ))
    dialog = ConditionDialog(parent=None, columns=[column], initial=group, dialogs=MagicMock(spec=DialogService))
    requests = MagicMock()
    invalidations = MagicMock()
    accepted = MagicMock()
    try:
        dialog.show()
        picker = dialog.rules[0].picker
        for timer in dialog.findChildren(QTimer):
            timer.stop()
        if not loading:
            picker.receive_page(ValuePage((selected, ConditionValue("string", "B")), False))
        qt_app.processEvents()
        generation = picker.generation
        feedback = dialog.validation.text()
        dialog.page_requested.connect(requests)
        dialog.request_invalidated.connect(invalidations)
        dialog.accepted.connect(accepted)

        _help_button(dialog).click()
        _press_f1(qt_app, dialog)

        assert opener.call_count == 2
        assert picker.selected_values() == (selected,)
        assert picker.generation == generation
        assert picker.loading == loading
        assert dialog.validation.text() == feedback
        assert dialog.apply_button.isEnabled() == (not loading)
        assert dialog.applied_group is None
        requests.assert_not_called()
        invalidations.assert_not_called()
        accepted.assert_not_called()
        if not loading:
            assert dialog.build_group() == group
            dialog.apply_button.click()
            assert dialog.applied_group == group
            accepted.assert_called_once()
        else:
            cancel = next(
                button
                for box in dialog.findChildren(QDialogButtonBox)
                if (button := box.button(QDialogButtonBox.StandardButton.Cancel)) is not None
            )
            cancel.click()
            assert not dialog.isVisible()
            assert dialog.applied_group is None
    finally:
        dialog.close()


def test_condition_f1_returns_to_reshape_after_closing(
    monkeypatch: pytest.MonkeyPatch, qt_app: QApplication, help_language: str
) -> None:
    urls: list[str] = []

    def open_url(url: QUrl) -> bool:
        urls.append(url.toString())
        return True

    monkeypatch.setattr(settings_editor.QDesktopServices, "openUrl", open_url)
    dialogs = MagicMock(spec=DialogService)
    parent = _dialog_for_topic(HelpTopic.RESHAPE, dialogs)
    assert isinstance(parent, ReshapeDialog)
    dialog = ConditionDialog(parent=parent, columns=[ConditionColumn(0, "Product", True)], dialogs=dialogs)
    try:
        parent.show()
        dialog.show()
        _press_f1(qt_app, dialog)
        assert urls == [HelpTopic.RESHAPE_CONDITION_BUILDER.url]
        dialog.close()
        _press_f1(qt_app, parent)
        assert urls == [HelpTopic.RESHAPE_CONDITION_BUILDER.url, HelpTopic.RESHAPE.url]
    finally:
        dialog.close()
        parent.close()


def _configure_reshape(dialog: ReshapeDialog) -> None:
    dimension = dialog.dimensions.item(0)
    assert dimension is not None
    dimension.setCheckState(Qt.CheckState.Checked)
    source = dialog.metrics.cellWidget(0, 2)
    assert isinstance(source, MetricSourceCell)
    source.value.setCurrentIndex(source.value.findData(1))
    name = dialog.metrics.item(0, 0)
    assert name is not None
    name.setText("Total amount")
    condition = dialog.metrics.cellWidget(0, 3)
    assert isinstance(condition, ConditionEditor)
    condition.text.setText("[Amount] > 0")
    condition.validate_now()


@pytest.mark.parametrize("state", ["empty", "preview", "busy"])
def test_reshape_help_preserves_preview_and_dispatch(
    monkeypatch: pytest.MonkeyPatch, qt_app: QApplication, state: str
) -> None:
    opener = MagicMock(return_value=True)
    monkeypatch.setattr(settings_editor.QDesktopServices, "openUrl", opener)
    dialog = _dialog_for_topic(HelpTopic.RESHAPE, MagicMock(spec=DialogService))
    assert isinstance(dialog, ReshapeDialog)
    preview = MagicMock()
    changes = MagicMock()
    accepted = MagicMock()
    try:
        dialog.show()
        _configure_reshape(dialog)
        request = dialog.capture_request()
        if state == "preview":
            dialog.show_preview(ReshapePreview(request, pd.DataFrame({"Region": ["North"], "Total amount": [150]}), 1))
        elif state == "busy":
            dialog.set_preview_busy(True)
        qt_app.processEvents()
        revision = dialog.revision
        model = dialog.preview_model
        text = dialog.preview_placeholder.text()
        table_visible = dialog.preview_table.isVisible()
        enabled = dialog.preview_button.isEnabled()
        dialog.preview_requested.connect(preview)
        dialog.configuration_changed.connect(changes)
        dialog.accepted.connect(accepted)

        _help_button(dialog).click()
        _press_f1(qt_app, dialog)

        assert opener.call_count == 2
        assert dialog.capture_request() == request
        assert dialog.revision == revision
        assert dialog.preview_model is model
        assert dialog.preview_placeholder.text() == text
        assert dialog.preview_table.isVisible() == table_visible
        assert dialog.preview_button.isEnabled() == enabled
        assert dialog.apply_button.isEnabled() == enabled
        assert dialog.applied_request is None
        preview.assert_not_called()
        changes.assert_not_called()
        accepted.assert_not_called()
        if state != "busy":
            dialog.preview_button.click()
            preview.assert_called_once_with(request)
            dialog.apply_button.click()
            assert dialog.applied_request == request
            accepted.assert_called_once()
        else:
            cancel_buttons = [
                button
                for box in dialog.findChildren(QDialogButtonBox)
                if (button := box.button(QDialogButtonBox.StandardButton.Cancel)) is not None
            ]
            assert len(cancel_buttons) == 1
            cancel_buttons[0].click()
            assert not dialog.isVisible()
            assert dialog.applied_request is None
    finally:
        dialog.close()


@pytest.mark.parametrize("formula", ["[Price] * [Quantity]", "[Price] *"])
@pytest.mark.parametrize("opened", [True, False])
def test_derived_help_preserves_validation_and_editor_state(
    monkeypatch: pytest.MonkeyPatch, qt_app: QApplication, formula: str, opened: bool
) -> None:
    opener = MagicMock(return_value=opened)
    monkeypatch.setattr(settings_editor.QDesktopServices, "openUrl", opener)
    dialogs = MagicMock(spec=DialogService)
    frame = pd.DataFrame({"Price": [12.5, 8.0], "Quantity": [2, 3]})
    original = frame.copy(deep=True)

    def validate_formula(name: str, text: str) -> tuple[FormulaValidationResult, str]:
        result = validate_derived_column_spec(frame, DerivedColumnSpec(name, text))
        return result, "Valid formula." if result.ok else "Invalid formula."

    validate = MagicMock(wraps=validate_formula)
    dialog = DerivedColumnDialog(df=frame, validate_callback=validate, dialogs=dialogs)
    name, editor = _derived_inputs(dialog)
    ok = _derived_action_button(dialog, QDialogButtonBox.StandardButton.Ok)
    accepted = MagicMock()
    rejected = MagicMock()
    dialog.accepted.connect(accepted)
    dialog.rejected.connect(rejected)
    try:
        dialog.show()
        qt_app.setActiveWindow(dialog)
        name.setText("Line total")
        editor.setPlainText(formula)
        cursor = editor.textCursor()
        cursor.select(cursor.SelectionType.Document)
        editor.setTextCursor(cursor)
        feedback = [label.text() for label in dialog.findChildren(QLabel)]
        diagnostics = [selection.cursor.selectedText() for selection in editor.extraSelections()]
        enabled = ok.isEnabled()
        assert enabled == (formula == "[Price] * [Quantity]")
        validate.reset_mock()

        _help_button(dialog).click()
        _press_f1(qt_app, dialog)

        assert opener.call_count == 2
        assert name.text() == "Line total"
        assert editor.toPlainText() == formula
        assert editor.textCursor().selectedText() == cursor.selectedText()
        assert [label.text() for label in dialog.findChildren(QLabel)] == feedback
        assert [selection.cursor.selectedText() for selection in editor.extraSelections()] == diagnostics
        assert ok.isEnabled() == enabled
        assert dialog.get_result() is None
        pd.testing.assert_frame_equal(frame, original)
        validate.assert_not_called()
        accepted.assert_not_called()
        rejected.assert_not_called()

        if enabled:
            ok.click()
            assert dialog.result() == QDialog.DialogCode.Accepted
            spec = dialog.get_result()
            assert spec is not None
            assert spec.column_name == "Line total"
            assert spec.formula == formula
            accepted.assert_called_once()
        else:
            cancel = _derived_action_button(dialog, QDialogButtonBox.StandardButton.Cancel)
            cancel.click()
            assert dialog.result() == QDialog.DialogCode.Rejected
            assert dialog.get_result() is None
            rejected.assert_called_once()
    finally:
        dialog.close()


@pytest.mark.parametrize(
    ("standard", "expected"),
    [
        (QDialogButtonBox.StandardButton.Ok, QDialog.DialogCode.Accepted),
        (QDialogButtonBox.StandardButton.Cancel, QDialog.DialogCode.Rejected),
    ],
)
def test_concat_action_buttons_preserve_dialog_result(
    qt_app: QApplication, standard: QDialogButtonBox.StandardButton, expected: QDialog.DialogCode
) -> None:
    dialogs = MagicMock(spec=DialogService)
    dialog = _dialog_for_topic(HelpTopic.CONCATENATE_DATASETS, dialogs)
    try:
        dialog.show()
        qt_app.processEvents()
        buttons = [
            button for box in dialog.findChildren(QDialogButtonBox) if (button := box.button(standard)) is not None
        ]
        assert len(buttons) == 1
        buttons[0].click()
        assert dialog.result() == expected
        assert not dialog.isVisible()
        dialogs.warn.assert_not_called()
    finally:
        dialog.close()


def test_settings_f1_does_not_trigger_parent_manual_action(
    monkeypatch: pytest.MonkeyPatch, qt_app: QApplication, help_topic: HelpTopic
) -> None:
    opener = MagicMock(return_value=True)
    monkeypatch.setattr(settings_editor.QDesktopServices, "openUrl", opener)
    parent = QMainWindow()
    menubar = parent.menuBar()
    assert menubar is not None
    noop = MagicMock()
    homepage = MagicMock()
    MenuController(
        menubar=menubar,
        new_file=noop,
        open_file=noop,
        save_file=noop,
        save_file_as=noop,
        quit_app=noop,
        export_csv=noop,
        export_excel=noop,
        export_data=noop,
        export_profile=noop,
        clear_editor=noop,
        open_settings_dialog=noop,
        open_log_settings_dialog=noop,
        open_connection_dialog=noop,
        open_rest_connection_dialog=noop,
        show_about_dialog=noop,
        open_user_manual=homepage,
    )
    dialog = _dialog_for_topic(help_topic, MagicMock(spec=DialogService), parent)
    try:
        parent.show()
        dialog.show()
        dialog.activateWindow()
        qt_app.processEvents()
        _press_f1(qt_app, dialog)
        opener.assert_called_once()
        assert opener.call_args.args[0].toString() == help_topic.url
        homepage.assert_not_called()
        dialog.close()
        parent.activateWindow()
        qt_app.processEvents()
        for event_type in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            qt_app.sendEvent(parent, QKeyEvent(event_type, Qt.Key.Key_F1, Qt.KeyboardModifier.NoModifier))
        homepage.assert_called_once_with(False)
        assert opener.call_count == 1
    finally:
        dialog.close()
        parent.close()


def test_scb_lists_keep_equal_height_with_limit_warning(
    monkeypatch: pytest.MonkeyPatch, qt_app: QApplication, help_language: str
) -> None:
    values = tuple(ScbVariableValue(str(index), str(index)) for index in range(101))
    metadata = ScbTableMetadata(
        table_id="sample",
        label="Sample table",
        variables=tuple(ScbVariable(name, name, name, values) for name in ("Region", "Period")),
    )
    monkeypatch.setattr(scb_browser_dialog, "fetch_scb_table_metadata", MagicMock(return_value=metadata))
    opener = MagicMock(return_value=True)
    monkeypatch.setattr(scb_browser_dialog.QDesktopServices, "openUrl", opener)
    dialog = ScbBrowserDialog(dialogs=MagicMock(spec=DialogService))
    try:
        dialog.show()
        dialog.activateWindow()
        dialog.select_all_button.click()
        dialog.variable_list.setCurrentRow(1)
        dialog.select_all_button.click()
        qt_app.processEvents()
        assert dialog.selection_warning.text() == dialog.tr("This selection exceeds the SCB limit.")
        assert not dialog.apply_button.isEnabled()
        assert dialog.variable_list.height() == dialog.value_list.height()
        assert dialog.variable_list.y() == dialog.value_list.y()
        help_button = _help_button(dialog)
        help_top = help_button.mapTo(dialog, help_button.rect().topLeft())
        assert help_top.y() > dialog.selection_warning.y() + dialog.selection_warning.height()
        assert dialog.selection_counter.geometry().right() <= dialog.width()
        assert dialog.selection_warning.geometry().right() <= dialog.width()
        help_button.click()
        _press_f1(qt_app, dialog)
        assert opener.call_count == 2
        assert not dialog.apply_button.isEnabled()
        assert dialog.result_data is None
        assert dialog.selection_warning.text() == dialog.tr("This selection exceeds the SCB limit.")
        dialog.clear_selection_button.click()
        assert dialog.apply_button.isEnabled()
        assert dialog.selection_warning.text() == ""
        assert dialog.variable_list.height() == dialog.value_list.height()
    finally:
        dialog.close()


def test_scb_f1_uses_builder_topic_then_rest_topic_after_closing(
    monkeypatch: pytest.MonkeyPatch, qt_app: QApplication, help_language: str
) -> None:
    urls: list[str] = []

    def open_url(url: QUrl) -> bool:
        urls.append(url.toString())
        return True

    monkeypatch.setattr(scb_browser_dialog.QDesktopServices, "openUrl", open_url)
    dialogs = MagicMock(spec=DialogService)
    parent = RestConnectionEditor(dialogs=dialogs)
    dialog = ScbBrowserDialog(parent=parent, dialogs=dialogs)
    try:
        parent.show()
        dialog.show()
        _press_f1(qt_app, dialog)
        assert urls == [HelpTopic.SCB_QUERY_BUILDER.url]
        dialog.close()
        _press_f1(qt_app, parent)
        assert urls == [HelpTopic.SCB_QUERY_BUILDER.url, HelpTopic.REST_API_CONNECTIONS.url]
    finally:
        dialog.close()
        parent.close()


def test_join_preview_f1_returns_to_join_topic_after_closing(
    monkeypatch: pytest.MonkeyPatch, qt_app: QApplication, help_language: str
) -> None:
    urls: list[str] = []

    def open_url(url: QUrl) -> bool:
        urls.append(url.toString())
        return True

    monkeypatch.setattr(settings_editor.QDesktopServices, "openUrl", open_url)
    dialogs = MagicMock(spec=DialogService)
    parent = _dialog_for_topic(HelpTopic.JOIN_DATASETS, dialogs)
    assert isinstance(parent, JoinDialog)
    data = pd.DataFrame({"id": [1]})
    dialog = JoinPreviewDialog(parent, df=data, metadata=JoinMetadata(1.0, 0.0, 0.0, "one-to-one", 1), dialogs=dialogs)
    try:
        parent.show()
        dialog.show()
        _press_f1(qt_app, dialog)
        assert urls == [HelpTopic.JOIN_PREVIEW.url]
        assert list(data.columns) == ["id"]
        dialog.close()
        _press_f1(qt_app, parent)
        assert urls == [HelpTopic.JOIN_PREVIEW.url, HelpTopic.JOIN_DATASETS.url]
    finally:
        dialog.close()
        parent.close()
