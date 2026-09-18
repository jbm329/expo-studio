"""Widgets for database schema display and interaction.

This module provides specialized Qt widgets for rendering database schema
information in a tree structure, with support for drag-and-drop operations
to export SQL identifiers. It includes utilities for validating and formatting
schema metadata.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, override

from PyQt6.QtCore import QMimeData, Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence


def _is_valid_meta(meta: Any) -> bool:
    """Validates the structure of metadata dicts placed in UserRole.

    Checks if the provided metadata dict conforms to the expected shapes for
    database schema elements (tables, views, or columns).

    Args:
        meta: The metadata dict to validate. Expected structures:
            - For tables/views: {"type": "table"|"view", "schema": str, "name": str}
            - For columns: {"type": "column", "schema": str, "table": str, "column": str}

    Returns:
        True if the dict has a valid structure, False otherwise.
    """
    if not isinstance(meta, dict):
        return False
    t = meta.get("type")
    if t in {"table", "view"}:
        return all(k in meta for k in ("schema", "name"))
    if t == "column":
        return all(k in meta for k in ("schema", "table", "column"))
    return False


def _qualify_table(schema: str, name: str) -> str:
    """Returns a fully qualified table/view name with bracket quoting.

    Args:
        schema: The schema name.
        name: The table or view name.

    Returns:
        A string in the format [schema].[name].
    """
    return f"[{schema}].[{name}]"


def _qualify_column(schema: str, table: str, column: str) -> str:
    """Returns a fully qualified column name with bracket quoting.

    Args:
        schema: The schema name.
        table: The table name.
        column: The column name.

    Returns:
        A string in the format [schema].[table].[column].
    """
    return f"[{schema}].[{table}].[{column}]"


def build_drag_text_from_meta(
    metas: Iterable[dict[str, Any]],
    *,
    prefer_multiline_for_same_table: bool = True,
    indent: str = "    ",
) -> str:
    """Builds drag text (SQL identifiers) from metadata dicts.

    Formats database schema elements (tables, views, columns) into SQL identifier
    strings suitable for drag-and-drop operations. Supports multiline formatting
    for columns from the same table.

    Args:
        metas: Iterable of metadata dicts representing schema elements.
        prefer_multiline_for_same_table: If True and all items are columns from
            the same table, formats as a comma-separated multiline list.
        indent: Indentation string for multiline formatting.

    Returns:
        A string containing formatted SQL identifiers, separated by newlines
        or commas depending on the input and options.
    """
    # Collect strings + compute shape characteristics
    parts: list[str] = []
    seen: set[str] = set()
    types: set[str] = set()
    tables_for_cols: set[tuple[str, str]] = set()

    for m in metas:
        if not _is_valid_meta(m):
            continue

        t = m["type"]
        types.add(t)

        if t in {"table", "view"}:
            text = _qualify_table(m["schema"], m["name"])
            if text not in seen:
                seen.add(text)
                parts.append(text)

        elif t == "column":
            text = _qualify_column(m["schema"], m["table"], m["column"])
            if text not in seen:
                seen.add(text)
                parts.append(text)
            tables_for_cols.add((m["schema"], m["table"]))

    if not parts:
        return ""

    only_cols = types == {"column"}
    if only_cols and len(tables_for_cols) == 1 and prefer_multiline_for_same_table:
        # Pretty-print a multi-line, comma-separated column list
        # First element without indent, subsequent with provided indent.
        head, *tail = parts
        if not tail:
            return head
        return ",\n".join([head] + [f"{indent}{p}" for p in tail])

    # Mixed types or multiple tables -> newline separated for clarity
    return "\n".join(parts)


class SchemaTreeWidget(QTreeWidget):
    """A QTreeWidget specialized for database schema display and drag operations.

    This widget displays database schema elements (schemas, tables, views, columns)
    in a hierarchical tree structure. It supports drag-only operations to export
    SQL identifiers to the workbench editor. Multiple selection is enabled for
    dragging multiple items.

    Attributes:
        MIME_TEXT: MIME type for plain text payload ("text/plain").
        MIME_SQL_IDS: Custom MIME type for SQL identifiers ("application/x-sql-identifiers").
        PREFER_MULTILINE_FOR_SAME_TABLE: Whether to format multiline columns from same table.
        MULTILINE_INDENT: Indentation string for multiline formatting.
    """

    # ------------------------------ Configuration ------------------------------
    # MIME types used for drag payloads. text/plain is always set.
    # application/x-sql-identifiers carries the same text for downstream integrations.
    MIME_TEXT = "text/plain"
    MIME_SQL_IDS = "application/x-sql-identifiers"

    # Whether to render multi-line, comma-separated columns when all are from the same table.
    PREFER_MULTILINE_FOR_SAME_TABLE = True

    # Indentation used for multi-line columns
    MULTILINE_INDENT = "    "

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initializes SchemaTreeWidget."""
        super().__init__(parent)

        # Basic presentation
        self.setHeaderHidden(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        # Interaction policy
        self.setDragEnabled(True)  # drag: yes
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)  # drop: no
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)  # multi-select

        # Optional: disable default sorting (SchemaController controls structure)
        # self.setSortingEnabled(False)

    # --------------------------------------------------------------------------
    # Qt override: build mime data for drag
    # --------------------------------------------------------------------------
    @override
    def mimeData(self, items: Iterable[QTreeWidgetItem]) -> QMimeData:
        """Builds MIME data for drag operations.

        Constructs a QMimeData object containing SQL identifiers from the selected
        tree items. Supports both plain text and custom MIME types for downstream
        processing.

        Args:
            items: Iterable of selected QTreeWidgetItem instances being dragged.

        Returns:
            A QMimeData object with text/plain and application/x-sql-identifiers data.
        """
        # Defensive fallback: use selectedItems() if items is falsy
        selected: Sequence[QTreeWidgetItem] = list(items) if items else self.selectedItems()

        # Extract and normalize meta dicts
        metas: list[dict[str, Any]] = []
        for it in selected:
            meta = it.data(0, Qt.ItemDataRole.UserRole)
            if _is_valid_meta(meta):
                metas.append(meta)

        # Build the text payload
        text_out = build_drag_text_from_meta(
            metas,
            prefer_multiline_for_same_table=self.PREFER_MULTILINE_FOR_SAME_TABLE,
            indent=self.MULTILINE_INDENT,
        )

        md = QMimeData()
        if text_out:
            md.setData(self.MIME_SQL_IDS, text_out.encode("utf-8"))
            md.setText(text_out)  # sets text/plain
        else:
            # Provide an empty text/plain to be explicit (some targets expect text mimetype existing)
            md.setText("")
        return md
