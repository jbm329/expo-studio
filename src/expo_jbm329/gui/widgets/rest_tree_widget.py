"""Widget for listing and interacting with REST API data sources.

This module provides the RestWidget class, a lightweight QListWidget-based
UI component for displaying configured REST API connections. Each entry
represents a runnable data source that can be loaded into the workbench.

Responsibilities:
- Display configured REST connections
- Handle user interaction (double-click, context menu)
- Emit signals for higher-level controllers to act upon

The widget is intentionally "dumb":
- No HTTP logic
- No JobManager interaction
- No configuration mutation
"""

from __future__ import annotations

from PyQt6.QtCore import QT_TR_NOOP, QPoint, QPointF, Qt, pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMenu, QTreeWidget, QTreeWidgetItem, QWidget

from expo_jbm329.services.rest.registry import rest_registry
from expo_jbm329.utils.i18n_utils import tr


class RestTreeWidget(QTreeWidget):
    """List widget for REST API data sources."""

    # --- i18n markers (pylupdate6-visible) -----------------------------
    TR_LOAD = QT_TR_NOOP("Load data")
    TR_EDIT = QT_TR_NOOP("Edit…")
    TR_DUPLICATE = QT_TR_NOOP("Duplicate…")
    TR_COPY = QT_TR_NOOP("Create copy…")

    @staticmethod
    def _tr(text: str) -> str:
        return tr("RestTreeWidget", text)

    FOLDER_ROLE = "__rest_folder__"
    SAMPLES_FOLDER_KEY = "samples"

    # ------------------------------------------------------------------
    # Signals (Qt-idiomatic API)
    # ------------------------------------------------------------------
    load_requested = pyqtSignal(str)  # preset name
    edit_requested = pyqtSignal(str)  # preset name
    copy_requested = pyqtSignal(str)  # preset name

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------
    def __init__(
        self,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the RestWidget."""
        super().__init__(parent)

        self.setHeaderHidden(True)

        # Presentation
        self.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        # Signals
        self.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.customContextMenuRequested.connect(self._on_context_menu)

    # ==================================================================
    # Public API
    # ==================================================================
    def reload(self) -> None:
        """Reload the list of REST connections from the runtime registry."""
        self.clear()

        entries = rest_registry.list_all()

        # -------------------------------
        # Folder samples
        # -------------------------------
        samples_item = QTreeWidgetItem([self._tr("samples")])
        samples_item.setData(0, Qt.ItemDataRole.UserRole, self.FOLDER_ROLE)
        self.addTopLevelItem(samples_item)

        # 1) Samples (folder: samples)
        for entry in entries:
            if entry.source == "sample":
                item = QTreeWidgetItem([entry.name])

                item.setData(0, Qt.ItemDataRole.UserRole, entry.name)

                # Visual hint: read-only (logiskt, ej ikon än)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)

                self._apply_tooltip(item, entry)
                samples_item.addChild(item)

        # 2) User connections (root)
        for entry in entries:
            if entry.source != "sample":
                item = QTreeWidgetItem([entry.name])

                item.setData(0, Qt.ItemDataRole.UserRole, entry.name)

                self._apply_tooltip(item, entry)
                self.addTopLevelItem(item)

    # ==================================================================
    # Internal helpers
    # ==================================================================

    def _apply_tooltip(self, item: QTreeWidgetItem, entry: object) -> None:
        """Apply tooltip information from a RestConnectionEntry."""
        tooltip = []
        url = entry.request.url.strip()
        if url:
            tooltip.append(f"URL: {url}")

        path = entry.request.response_path
        if path:
            tooltip.append(f"Path: {path}")

        if tooltip:
            item.setToolTip(0, "\n".join(tooltip))

    # ==================================================================
    # Event handlers
    # ==================================================================
    def _on_item_double_clicked(self, item: QTreeWidgetItem) -> None:
        """Handle double-click on a REST preset."""
        name = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(name, str):
            self.load_requested.emit(name)

    def _on_context_menu(self, pos: object) -> None:
        """Show context menu for REST presets."""
        item = self.itemAt(pos)
        if not item:
            return

        name = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(name, str):
            return

        if name == "__rest_folder__":
            return

        menu = QMenu(self)

        entry = rest_registry.get(name)
        is_sample = entry and entry.read_only

        act_rest = QAction(name, menu)
        menu.addAction(act_rest)
        act_rest.setEnabled(False)
        menu.addSeparator()
        act_load = QAction(self._tr(self.TR_LOAD), menu)
        menu.addAction(act_load)
        act_edit = QAction(self._tr(self.TR_EDIT), menu)
        menu.addAction(act_edit)
        act_copy = QAction(self._tr(self.TR_COPY) if is_sample else self._tr(self.TR_DUPLICATE), menu)
        menu.addAction(act_copy)
        menu.addSeparator()

        # Disable edit/delete for read-only entries
        if is_sample:
            act_edit.setEnabled(False)

        if isinstance(pos, QPointF):
            point: QPoint = pos.toPoint()
        else:
            point: QPoint = pos

        global_pos: QPoint = self.mapToGlobal(point)
        chosen = menu.exec(global_pos)

        if not chosen:
            return

        if chosen == act_load:
            self.load_requested.emit(name)
        elif chosen == act_edit:
            self.edit_requested.emit(name)
        elif chosen == act_copy:
            self.copy_requested.emit(name)
