from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QTreeWidgetItem

from expo_jbm329.gui.widgets.schema_tree_widget import SchemaTreeWidget


def make_item(meta: dict[str, str]) -> QTreeWidgetItem:
    item = QTreeWidgetItem(["x"])
    item.setData(0, Qt.ItemDataRole.UserRole, meta)
    return item


def test_mime_data_uses_ansi_fallback_without_provider():
    tree = SchemaTreeWidget()
    item = make_item({"type": "table", "schema": "dbo", "name": "T"})

    md = tree.mimeData([item])

    assert md.text() == '"dbo"."T"'
    assert bytes(md.data(SchemaTreeWidget.MIME_SQL_IDS)).decode("utf-8") == '"dbo"."T"'


def test_mime_data_delegates_to_provider():
    tree = SchemaTreeWidget()
    received = []

    def provider(items):
        received.extend(items)
        return "[dbo].[T]"

    tree.set_drag_text_provider(provider)
    item = make_item({"type": "table", "schema": "dbo", "name": "T"})

    md = tree.mimeData([item])

    assert received == [item]
    assert md.text() == "[dbo].[T]"
    assert bytes(md.data(SchemaTreeWidget.MIME_SQL_IDS)).decode("utf-8") == "[dbo].[T]"


def test_mime_data_empty_text_when_nothing_draggable():
    tree = SchemaTreeWidget()
    item = make_item({"type": "group", "group": "tables"})

    md = tree.mimeData([item])

    assert md.text() == ""
    assert not md.hasFormat(SchemaTreeWidget.MIME_SQL_IDS)
