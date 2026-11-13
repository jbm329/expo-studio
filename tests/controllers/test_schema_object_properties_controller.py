from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QEvent, QTranslator
from PyQt6.QtWidgets import QApplication, QTableWidgetSelectionRange, QWidget

from expo_jbm329.db.core.object_properties import (
    ColumnProperties,
    ConstraintKind,
    MetadataState,
    MetadataValue,
    NamedProperty,
    ObjectConstraint,
    ObjectProperties,
    SchemaObjectIdentity,
    SchemaObjectKind,
)
from expo_jbm329.i18n.language import Language
from expo_jbm329.workbench.controllers.connection_controller import ConnectionController
from expo_jbm329.workbench.controllers.schema_object_properties_controller import SchemaObjectPropertiesController


class DeferredOperations:
    def __init__(self):
        self.calls = []

    def run_operation(self, **kwargs):
        self.calls.append(kwargs)


@pytest.fixture
def snapshot():
    absent = MetadataValue[str](MetadataState.ABSENT)
    identity = SchemaObjectIdentity("dbo", "<Orders>", SchemaObjectKind.TABLE, "Example")
    properties = (
        NamedProperty("MS_Description", MetadataValue(MetadataState.AVAILABLE, "<b>Literal</b>\nDescription")),
        NamedProperty("Custom", MetadataValue(MetadataState.AVAILABLE, "Other value")),
    )
    columns = tuple(
        ColumnProperties(
            name,
            ordinal,
            MetadataValue(MetadataState.AVAILABLE, "nvarchar(50)"),
            MetadataValue(MetadataState.AVAILABLE, False),
            absent,
            properties[0].value,
            MetadataValue(MetadataState.AVAILABLE, properties),
            MetadataValue(MetadataState.NOT_APPLICABLE),
            MetadataValue(MetadataState.UNSUPPORTED),
        )
        for ordinal, name in enumerate(("tenant", "id"), 1)
    )
    constraint = ObjectConstraint(
        "FK_Items",
        ConstraintKind.FOREIGN_KEY,
        ("tenant", "id"),
        MetadataValue(MetadataState.NOT_APPLICABLE),
        SchemaObjectIdentity("other", "Items", SchemaObjectKind.TABLE, "Example"),
        ("tenant", "item_id"),
    )
    return ObjectProperties(
        identity,
        properties[0].value,
        MetadataValue(MetadataState.AVAILABLE, properties),
        columns,
        MetadataValue(MetadataState.AVAILABLE, (constraint,)),
    )


@pytest.fixture
def controller(snapshot):
    parent = QWidget()
    operations = DeferredOperations()
    loader = MagicMock(return_value=snapshot)
    controller = SchemaObjectPropertiesController(parent=parent, async_ops=operations, load=loader)
    yield controller, operations, loader
    for session in list(controller._sessions):
        if not sip.isdeleted(session.dialog):
            session.dialog.close()
    parent.close()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_loading_runs_only_in_worker_and_displays_catalog_snapshot(controller, snapshot):
    from expo_jbm329.gui.dialogs.analysis.section_layout import ANALYSIS_TABS_STYLE

    ctrl, operations, loader = controller
    dialog = ctrl.open("Clicked / connection", snapshot.identity)
    assert dialog.tabs.styleSheet() == ANALYSIS_TABS_STYLE
    loader.assert_not_called()
    assert not dialog.tabs.isEnabled()
    assert not dialog.retry.isEnabled()
    call = operations.calls[0]
    call["on_result"](call["work"]())
    loader.assert_called_once_with("Clicked / connection", snapshot.identity, corr_id=call["corr_id"])
    assert dialog.tabs.isEnabled()
    assert dialog.windowTitle() == "Properties (table: <Orders>)"
    assert dialog.status.isHidden()
    assert dialog.description.toPlainText() == "<b>Literal</b>\nDescription"
    assert dialog.columns.item(0, 0).text() == "tenant"
    assert dialog.columns.item(0, 1).text() == "nvarchar(50)"
    assert dialog.columns.item(0, 4).text() == "Foreign key"
    assert dialog.properties.rowCount() == 2
    assert dialog.constraints.rowCount() == 1
    assert dialog.constraints.item(0, 2).text() == "tenant, id"
    assert dialog.constraints.item(0, 3).text() == "other.Items (tenant, item_id)"
    assert "Custom: Other value" in dialog.details.toPlainText()
    assert "&lt;b&gt;Literal&lt;/b&gt;" in dialog.columns.item(0, 5).toolTip()
    dialog.columns.selectRow(1)
    assert dialog.details.toPlainText().startswith("id\n")


def test_copy_selected_cells_uses_plain_tab_separated_text(controller, snapshot):
    ctrl, operations, _ = controller
    dialog = ctrl.open("Clicked", snapshot.identity)
    operations.calls[0]["on_result"](snapshot)
    dialog.columns.clearSelection()
    dialog.columns.setRangeSelected(QTableWidgetSelectionRange(0, 0, 1, 1), True)
    dialog._copy_selected()
    assert QApplication.clipboard().text() == "tenant\tnvarchar(50)\nid\tnvarchar(50)"


def test_description_has_blank_line_spacing_without_identity_path(controller, snapshot):
    from PyQt6.QtWidgets import QLabel

    ctrl, _, _ = controller
    dialog = ctrl.open("Hidden connection", snapshot.identity)
    labels = [label.text() for label in dialog.findChildren(QLabel)]
    assert not any("Hidden connection" in text or "Example / dbo" in text for text in labels)
    layout = dialog.layout()
    spacers = [layout.itemAt(index).spacerItem() for index in range(layout.count())]
    assert any(spacer is not None and spacer.sizeHint().height() >= dialog.fontMetrics().height() for spacer in spacers)


def test_retry_ignores_out_of_order_result_error_and_finished(controller, snapshot):
    ctrl, operations, _ = controller
    dialog = ctrl.open("Clicked", snapshot.identity)
    first = operations.calls[0]
    first["on_error"]("internal traceback")
    assert dialog.retry.isEnabled()
    dialog.retry.click()
    second = operations.calls[1]
    first["on_result"](snapshot)
    first["on_error"]("stale error")
    first["on_finished"]()
    assert not dialog.tabs.isEnabled()
    assert not dialog.retry.isEnabled()
    second["on_result"](snapshot)
    second["on_finished"]()
    assert dialog.tabs.isEnabled()


@pytest.mark.parametrize("destroy", [False, True])
def test_closing_ignores_all_callbacks_and_queued_work(controller, snapshot, destroy):
    ctrl, operations, loader = controller
    dialog = ctrl.open("Clicked", snapshot.identity)
    call = operations.calls[0]
    if destroy:
        dialog.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    else:
        dialog.close()
    assert call["stale_check"]()
    assert call["work"]() is None
    call["on_result"](snapshot)
    call["on_error"]("late error")
    call["on_finished"]()
    loader.assert_not_called()
    assert ctrl._sessions == []


@pytest.mark.parametrize("method", ["disconnect", "invalidate_configuration"])
@pytest.mark.parametrize("active", [True, False])
def test_connection_invalidation_survives_same_name_reconnect(controller, snapshot, method, active):
    ctrl, operations, loader = controller
    connections = ConnectionController(
        get_connection_names=lambda: ["Clicked", "Other"],
        close_db_connection=lambda _name: None,
        clear_schema_cache=lambda _name: None,
    )
    connections.bind_schema_loader(lambda _name, _force: None)
    connections.on_connection_invalidated(ctrl.invalidate_connection)
    connections.connect("Clicked" if active else "Other")
    dialog = ctrl.open("Clicked", snapshot.identity)
    call = operations.calls[0]
    connections.connect("Other")
    assert not call["stale_check"]()
    getattr(connections, method)("Clicked")
    connections.connect("Clicked")
    assert call["stale_check"]()
    call["on_result"](snapshot)
    call["on_error"]("late error")
    call["on_finished"]()
    assert "connection changed" in dialog.status.text()
    assert not dialog.tabs.isEnabled() and not dialog.retry.isEnabled()
    assert call["work"]() is None
    loader.assert_not_called()
    fresh = ctrl.open("Clicked", snapshot.identity)
    operations.calls[1]["on_result"](snapshot)
    assert fresh.tabs.isEnabled()


def test_expected_errors_are_explicit_and_retryable(controller, snapshot):
    ctrl, operations, loader = controller
    loader.side_effect = RuntimeError("Permission denied.\n\nCheck permissions.")
    dialog = ctrl.open("Clicked", snapshot.identity)
    call = operations.calls[0]
    call["on_result"](call["work"]())
    call["on_finished"]()
    assert "Permission denied." in dialog.status.text()
    assert "Check permissions." in dialog.status.text()
    assert dialog.retry.isEnabled()
    assert not dialog.tabs.isEnabled()


def test_empty_view_and_null_metadata_remain_explicit(controller, snapshot):
    ctrl, operations, _ = controller
    dialog = ctrl.open("Clicked", snapshot.identity)
    missing = replace(
        snapshot,
        identity=replace(snapshot.identity, kind=SchemaObjectKind.VIEW),
        description=MetadataValue(MetadataState.ABSENT),
        columns=(),
        constraints=MetadataValue(MetadataState.NOT_APPLICABLE),
    )
    operations.calls[0]["on_result"](missing)
    assert dialog.description.toPlainText() == "Not set"
    assert dialog.windowTitle() == "Properties (view: <Orders>)"
    assert dialog.status.isHidden()
    assert dialog.columns.rowCount() == 0


def test_native_comments_hide_named_properties_without_losing_descriptions(controller, snapshot):
    ctrl, operations, _ = controller
    dialog = ctrl.open("Postgres", snapshot.identity)
    native = replace(
        snapshot,
        properties=MetadataValue(MetadataState.UNSUPPORTED),
        columns=tuple(
            replace(column, properties=MetadataValue(MetadataState.UNSUPPORTED)) for column in snapshot.columns
        ),
    )
    operations.calls[0]["on_result"](native)
    assert not dialog.tabs.isTabVisible(1)
    assert dialog.tabs.isTabVisible(0) and dialog.tabs.isTabVisible(2)
    assert dialog.description.toPlainText() == native.description.value
    assert dialog.columns.item(0, 5).text() == native.columns[0].description.value
    dialog.show_properties(snapshot)
    assert dialog.tabs.isTabVisible(1)


@pytest.mark.parametrize("language", list(Language))
def test_properties_ui_strings_have_compiled_translations(language):
    from expo_jbm329.gui.dialogs.schema_object_properties_dialog import SchemaObjectPropertiesDialog
    from expo_jbm329.workbench.controllers.schema_object_properties_controller import CATALOG_ERROR_MESSAGES

    translator = QTranslator()
    catalog = Path(__file__).parents[2] / "src" / "expo_jbm329" / "i18n" / "locales" / f"app_{language.value}.qm"
    assert translator.load(str(catalog))
    for source in (
        "Properties (table: {name})",
        "Properties (view: {name})",
        "Copy selected cells",
        "Loading properties...",
        "Extended properties",
    ):
        translated = translator.translate(SchemaObjectPropertiesDialog.__name__, source)
        assert bool(translated) == (language != Language.ENGLISH)
    for source in CATALOG_ERROR_MESSAGES:
        translated = translator.translate("DbErrors", source)
        assert bool(translated) == (language != Language.ENGLISH)


@pytest.mark.parametrize("language", list(Language))
def test_properties_dialog_renders_using_each_compiled_language(controller, snapshot, language, qt_app):
    import xml.etree.ElementTree as ET

    translator = QTranslator()
    locale_dir = Path(__file__).parents[2] / "src" / "expo_jbm329" / "i18n" / "locales"
    assert translator.load(str(locale_dir / f"app_{language.value}.qm"))
    root = ET.parse(locale_dir / f"app_{language.value}.ts").getroot()
    contexts = {"SchemaObjectPropertiesDialog", "SchemaObjectPropertiesController"}
    for context in root.findall("context"):
        if context.findtext("name") not in contexts:
            continue
        for message in context.findall("message"):
            source = message.findtext("source")
            translated = translator.translate(context.findtext("name"), source)
            assert bool(translated) == (language != Language.ENGLISH)
            if "{error}" in source:
                assert "{error}" in (translated or source)
    qt_app.installTranslator(translator)
    try:
        ctrl, operations, _ = controller
        dialog = ctrl.open("Clicked", snapshot.identity)
        expected = (
            translator.translate("SchemaObjectPropertiesDialog", "Loading properties...") or "Loading properties..."
        )
        assert dialog.status.text() == expected
        operations.calls[-1]["on_result"](snapshot)
        expected = translator.translate("SchemaObjectPropertiesDialog", "No") or "No"
        assert dialog.columns.item(0, 2).text() == expected
        assert dialog.description.toPlainText() == snapshot.description.value
        dialog.close()
    finally:
        qt_app.removeTranslator(translator)
