"""Widgets for database schema display and interaction.

This module provides a specialized Qt tree widget for rendering database schema
information, with drag support to export SQL identifiers. Identifier formatting
is delegated to an injected provider so the widget stays dialect agnostic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from PyQt6.QtCore import QMimeData, Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
)

from expo_jbm329.db.dialects.ansi import AnsiDialect
from expo_jbm329.db.identifier_formatting import build_identifier_text

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence


type DragTextProvider = Callable[[Sequence[QTreeWidgetItem]], str]


class SchemaTreeWidget(QTreeWidget):
    """A QTreeWidget specialized for database schema display and drag operations.

    This widget displays database schema elements (schemas, tables, views, columns)
    in a hierarchical tree structure. It supports drag-only operations to export
    SQL identifiers to the workbench editor. Multiple selection is enabled for
    dragging multiple items.

    The drag text is produced by an injected provider (see
    ``set_drag_text_provider``), which allows the owning controller to format
    identifiers using the dialect of each item's connection.

    Attributes:
        MIME_TEXT: MIME type for plain text payload ("text/plain").
        MIME_SQL_IDS: Custom MIME type for SQL identifiers ("application/x-sql-identifiers").
    """

    # ------------------------------ Configuration ------------------------------
    # MIME types used for drag payloads. text/plain is always set.
    # application/x-sql-identifiers carries the same text for downstream integrations.
    MIME_TEXT = "text/plain"
    MIME_SQL_IDS = "application/x-sql-identifiers"

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initializes SchemaTreeWidget."""
        super().__init__(parent)

        self._drag_text_provider: DragTextProvider | None = None

        # Basic presentation
        self.setHeaderHidden(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        # Interaction policy
        self.setDragEnabled(True)  # drag: yes
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)  # drop: no
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)  # multi-select

    def set_drag_text_provider(self, provider: DragTextProvider | None) -> None:
        """Set the callable that builds drag text for the dragged items.

        Args:
            provider: Callable receiving the dragged items and returning the
                SQL identifier text, or None to use the ANSI fallback.
        """
        self._drag_text_provider = provider

    def _build_drag_text(self, items: Sequence[QTreeWidgetItem]) -> str:
        """Build the drag text for the given items.

        Args:
            items: The dragged tree items.

        Returns:
            The SQL identifier text for the items.
        """
        if self._drag_text_provider is not None:
            return self._drag_text_provider(items)

        metas = [item.data(0, Qt.ItemDataRole.UserRole) for item in items]
        return build_identifier_text(metas, AnsiDialect())

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
        # Defensive fallback: use selectedItems() if no items were supplied
        selected: Sequence[QTreeWidgetItem] = list(items) or self.selectedItems()

        text_out = self._build_drag_text(selected)

        md = QMimeData()
        if text_out:
            md.setData(self.MIME_SQL_IDS, text_out.encode("utf-8"))
            md.setText(text_out)  # sets text/plain
        else:
            # Provide an empty text/plain to be explicit (some targets expect text mimetype existing)
            md.setText("")
        return md
