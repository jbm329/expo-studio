"""Indented condition rows with handle-only dragging and stable widget ownership."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, override

from PyQt6.QtCore import QEvent, QMimeData, QPoint, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QDrag, QPainter, QPen
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QMenu,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from expo_jbm329.services.data_operations.reshape_condition_tree import ConditionDrop, ConditionNode, ConditionTree
from expo_jbm329.services.data_operations.reshape_conditions import ConditionMatch

if TYPE_CHECKING:
    from PyQt6.QtCore import QObject
    from PyQt6.QtGui import (
        QContextMenuEvent,
        QDragEnterEvent,
        QDragLeaveEvent,
        QDragMoveEvent,
        QDropEvent,
        QMouseEvent,
        QPaintEvent,
    )

_MIME = "application/x-expo-reshape-condition"
_INDENT = 24
_SCROLL_EDGE = 28


class ConditionDragHandle(QToolButton):
    """Start a move only from the dedicated handle, never from rule controls."""

    def __init__(self, row: ConditionTreeRow) -> None:
        """Associate the handle with a stable row."""
        super().__init__(row)
        self._row = row
        self._press: QPoint | None = None
        self.setText("::")
        self.setAccessibleName(self.tr("Move rule or group"))
        self.setToolTip(self.tr("Drag to move or group. Click for more actions."))
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.clicked.connect(self._show_actions)

    def _show_actions(self) -> None:
        self._row.tree.show_actions(self._row.node, self.mapToGlobal(QPoint(0, self.height())))

    @override
    def mousePressEvent(self, a0: QMouseEvent | None) -> None:
        """Remember only a left-button drag origin."""
        event = a0
        if event is None:
            return
        self._press = event.position().toPoint() if event.button() == Qt.MouseButton.LeftButton else None
        self._row.tree.select(self._row.node)
        super().mousePressEvent(event)

    @override
    def mouseReleaseEvent(self, a0: QMouseEvent | None) -> None:
        """Clear a click's drag origin."""
        self._press = None
        super().mouseReleaseEvent(a0)

    @override
    def mouseMoveEvent(self, e: QMouseEvent | None) -> None:
        """Let Qt run a native drag after its normal movement threshold."""
        event = e
        if event is None:
            return
        if (
            self._press is not None
            and event.buttons() & Qt.MouseButton.LeftButton
            and (event.position().toPoint() - self._press).manhattanLength() >= QApplication.startDragDistance()
        ):
            self._press = None
            self.setDown(False)
            drag = QDrag(self)
            drag.setMimeData(self._row.tree.mime_data(self._row.node))
            drag.exec(Qt.DropAction.MoveAction)
            self._row.tree.stop_drag_scroll()
            return
        super().mouseMoveEvent(event)


class ConditionTreeRow(QWidget):
    """One persistent editor row, with tree branches and drop feedback."""

    def __init__(self, tree: ConditionTreeWidget, node: ConditionNode, content: QWidget) -> None:
        """Own a rule/group editor without tying its lifetime to a tree index."""
        super().__init__(tree.panel)
        self.tree = tree
        self.node = node
        self.level = 0
        self.branches: tuple[bool, ...] = ()
        self.last = False
        self.indicator: ConditionDrop | None = None
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.row_layout = QHBoxLayout(self)
        self.handle = ConditionDragHandle(self)
        self.handle.setEnabled(node is not tree.model.root)
        self.row_layout.addWidget(self.handle)
        self.row_layout.addWidget(content, 1)
        for widget in (content, *content.findChildren(QWidget)):
            widget.installEventFilter(self)
        self.setMinimumHeight(content.sizeHint().height() + 8)

    def set_depth(self, depth: int, branches: tuple[bool, ...], *, last: bool) -> None:
        """Update indentation without recreating or reparenting the editor."""
        self.level, self.branches, self.last = depth, branches, last
        self.row_layout.setContentsMargins(depth * _INDENT + 4, 4, 4, 4)
        self.update()

    def placement(self, point: QPoint) -> ConditionDrop:
        """Reserve row edges for ordering and the center for grouping."""
        if self.node is self.tree.model.root:
            return ConditionDrop.INTO
        if point.y() < self.height() // 4:
            return ConditionDrop.BEFORE
        if point.y() >= self.height() * 3 // 4:
            return ConditionDrop.AFTER
        return ConditionDrop.INTO

    def _accept_destination(self, event: QDropEvent) -> bool:
        source = self.tree.drag_source(event.mimeData())
        placement = self.placement(event.position().toPoint())
        allowed = source is not None and self.tree.model.can_move(source, self.node, placement)
        self.indicator = placement if allowed else None
        self.update()
        if allowed:
            self.tree.track_drag(self.mapToGlobal(event.position().toPoint()))
            event.setDropAction(Qt.DropAction.MoveAction)
            event.accept()
        else:
            self.tree.stop_drag_scroll()
            event.ignore()
        return allowed

    @override
    def dragEnterEvent(self, a0: QDragEnterEvent | None) -> None:
        """Accept only structurally valid drags from this builder."""
        event = a0
        if event is not None:
            self._accept_destination(event)

    @override
    def dragMoveEvent(self, a0: QDragMoveEvent | None) -> None:
        """Update destination feedback as the pointer crosses row zones."""
        event = a0
        if event is not None:
            self._accept_destination(event)

    @override
    def dragLeaveEvent(self, a0: QDragLeaveEvent | None) -> None:
        """Remove feedback when the pointer leaves this row."""
        event = a0
        self.indicator = None
        self.tree.stop_drag_scroll()
        self.update()
        if event is not None:
            event.accept()

    @override
    def dropEvent(self, a0: QDropEvent | None) -> None:
        """Apply one validated structural move, leaving rejected drags untouched."""
        event = a0
        if event is None:
            return
        self.tree.stop_drag_scroll()
        if self._accept_destination(event):
            source = self.tree.drag_source(event.mimeData())
            if source is not None:
                self.tree.move_node(source, self.node, self.placement(event.position().toPoint()))
        self.indicator = None
        self.tree.stop_drag_scroll()
        self.update()

    @override
    def mousePressEvent(self, a0: QMouseEvent | None) -> None:
        """Select a row when its tree chrome is clicked."""
        self.tree.select(self.node)
        super().mousePressEvent(a0)

    @override
    def contextMenuEvent(self, a0: QContextMenuEvent | None) -> None:
        """Expose structural actions to mouse and keyboard users."""
        event = a0
        if event is not None:
            self.tree.show_actions(self.node, event.globalPos())
            event.accept()

    @override
    def eventFilter(self, a0: QObject | None, a1: QEvent | None) -> bool:
        """Select the owning row without intercepting its editor interaction."""
        event = a1
        if event is not None and event.type() in {QEvent.Type.FocusIn, QEvent.Type.MouseButtonPress}:
            self.tree.select(self.node)
        return super().eventFilter(a0, event)

    @override
    def paintEvent(self, a0: QPaintEvent | None) -> None:
        """Draw branch lines, selection and before/after/into drop indicators."""
        super().paintEvent(a0)
        painter = QPainter(self)
        painter.setPen(self.palette().mid().color())
        for level, continues in enumerate(self.branches):
            if continues:
                x = level * _INDENT + _INDENT // 2
                painter.drawLine(x, 0, x, self.height())
        if self.level:
            x = (self.level - 1) * _INDENT + _INDENT // 2
            middle = self.height() // 2
            painter.drawLine(x, 0, x, middle if self.last else self.height())
            painter.drawLine(x, middle, self.level * _INDENT, middle)
        if self.tree.selected is self.node:
            painter.setPen(self.palette().highlight().color())
            painter.drawRect(self.rect().adjusted(self.level * _INDENT, 0, -1, -1))
        if self.indicator is not None:
            painter.setPen(QPen(self.palette().highlight().color(), 2))
            if self.indicator == ConditionDrop.INTO:
                painter.drawRect(self.rect().adjusted(self.level * _INDENT + 1, 1, -2, -2))
            else:
                y = 1 if self.indicator == ConditionDrop.BEFORE else self.height() - 2
                painter.drawLine(self.level * _INDENT, y, self.width(), y)
        painter.end()


class ConditionTreeWidget(QScrollArea):
    """A widget-backed tree that never destroys rule editors when moving nodes."""

    changed = pyqtSignal()
    add_requested = pyqtSignal(object)  # ConditionNode group

    def __init__(self, parent: QWidget) -> None:
        """Create permanent row ownership and the outer group's connector."""
        super().__init__(parent)
        self.model = ConditionTree()
        self.selected = self.model.root
        self.rows: dict[str, ConditionTreeRow] = {}
        self.connectors: dict[str, QComboBox] = {}
        self._scroll_direction = 0
        self._scroll_timer = QTimer(self)
        self._scroll_timer.setInterval(75)
        self._scroll_timer.timeout.connect(self._scroll_drag)
        self.setWidgetResizable(True)
        self.panel = QWidget(self)
        self._layout = QVBoxLayout(self.panel)
        self._layout.setSpacing(0)
        self._layout.addStretch()
        self.setWidget(self.panel)
        self.refresh()

    def track_drag(self, global_position: QPoint) -> None:
        """Scroll near viewport edges while a valid drag is held stationary."""
        viewport = self.viewport()
        if viewport is None:
            return
        y = viewport.mapFromGlobal(global_position).y()
        self._scroll_direction = -1 if y < _SCROLL_EDGE else 1 if y >= viewport.height() - _SCROLL_EDGE else 0
        if self._scroll_direction:
            self._scroll_timer.start()
        else:
            self.stop_drag_scroll()

    def stop_drag_scroll(self) -> None:
        """Stop edge scrolling on leave, rejection or drop."""
        self._scroll_timer.stop()
        self._scroll_direction = 0

    def _scroll_drag(self) -> None:
        scrollbar = self.verticalScrollBar()
        if scrollbar is not None:
            scrollbar.setValue(scrollbar.value() + self._scroll_direction * scrollbar.singleStep())

    def select(self, node: ConditionNode) -> None:
        """Keep a stable selected destination for Add rule and context actions."""
        self.selected = node
        for row in self.rows.values():
            row.update()

    def insertion_group(self) -> ConditionNode:
        """Resolve selection to a group, including when a rule is selected."""
        if self.selected.match is not None:
            return self.selected
        return self.model.parent(self.selected) or self.model.root

    def attach_rule(self, node: ConditionNode, editor: QWidget) -> None:
        """Wrap one new editor; subsequent moves reuse this exact row."""
        self.rows[node.key] = ConditionTreeRow(self, node, editor)

    def _group_row(self, node: ConditionNode) -> ConditionTreeRow:
        content = QWidget(self.panel)
        layout = QHBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        connector = QComboBox(content)
        connector.addItem(self.tr("All rules (AND)"), ConditionMatch.ALL)
        connector.addItem(self.tr("Any rule (OR)"), ConditionMatch.ANY)
        connector.setCurrentIndex(connector.findData(node.match))
        connector.setAccessibleName(self.tr("Group operator"))
        connector.setToolTip(self.tr("Choose how the rules in this group are combined."))

        def set_connector() -> None:
            value = connector.currentData()
            if isinstance(value, ConditionMatch):
                node.match = value
                self.changed.emit()

        connector.currentIndexChanged.connect(set_connector)
        self.connectors[node.key] = connector
        add = QPushButton(self.tr("Add rule"), content)
        add.setAutoDefault(False)
        add.clicked.connect(lambda: self.add_requested.emit(node))
        layout.addWidget(connector)
        layout.addStretch()
        layout.addWidget(add)
        return ConditionTreeRow(self, node, content)

    def refresh(self) -> None:
        """Reorder layout entries, retaining every surviving editor and picker."""
        nodes = self.model.nodes()
        keys = {node.key for node in nodes}
        while self._layout.count() > 1:
            self._layout.takeAt(0)
        for key in tuple(self.rows):
            if key not in keys:
                self.rows.pop(key).deleteLater()
                self.connectors.pop(key, None)
        if self.selected not in nodes:
            self.selected = self.model.root

        def visit(node: ConditionNode, depth: int, branches: tuple[bool, ...], *, last: bool) -> None:
            row = self.rows.get(node.key)
            if row is None:
                if node.match is None:
                    message = "A condition leaf has no rule editor."
                    raise ValueError(message)
                row = self._group_row(node)
                self.rows[node.key] = row
            row.set_depth(depth, branches, last=last)
            self._layout.insertWidget(self._layout.count() - 1, row)
            row.show()
            for index, child in enumerate(node.children):
                visit(child, depth + 1, (*branches, not last) if depth else (), last=index == len(node.children) - 1)

        visit(self.model.root, 0, (), last=True)
        self.changed.emit()

    def mime_data(self, node: ConditionNode) -> QMimeData:
        """Scope drag payloads to this builder and one stable node identity."""
        mime = QMimeData()
        mime.setData(_MIME, f"{self.model.root.key}:{node.key}".encode("ascii"))
        return mime

    def drag_source(self, mime: QMimeData | None) -> ConditionNode | None:
        """Reject external drags and nodes removed since a drag began."""
        if mime is None or not mime.hasFormat(_MIME):
            return None
        payload = mime.data(_MIME).data()
        return next(
            (node for node in self.model.nodes() if payload == f"{self.model.root.key}:{node.key}".encode("ascii")),
            None,
        )

    def move_node(self, source: ConditionNode, target: ConditionNode, placement: ConditionDrop) -> None:
        """Move without rebinding editors, signals or asynchronous requests."""
        self.model.move(source, target, placement)
        self.selected = source
        self.refresh()

    def action_menu(self, node: ConditionNode) -> QMenu:
        """Build enabled structural actions for the selected rule or group."""
        menu = QMenu(self)
        parent = self.model.parent(node)
        index = parent.children.index(node) if parent is not None else -1
        specifications = (
            (self.tr("Move up"), "up", parent is not None and index > 0),
            (self.tr("Move down"), "down", parent is not None and index + 1 < len(parent.children)),
            (self.tr("Group with previous (AND)"), "indent", parent is not None and index > 0),
            (self.tr("Move out of group"), "outdent", parent is not None and parent is not self.model.root),
            (self.tr("Ungroup (use parent operator)"), "ungroup", parent is not None and node.match is not None),
        )
        for label, operation, enabled in specifications:
            action = QAction(label, menu)
            menu.addAction(action)
            action.setData(operation)
            action.setEnabled(enabled)
            action.triggered.connect(partial(self.perform_action, node, operation))
        return menu

    def show_actions(self, node: ConditionNode, position: QPoint) -> None:
        """Present the same actions through the handle or row context menu."""
        self.select(node)
        menu = self.action_menu(node)
        menu.exec(position)
        menu.deleteLater()

    def perform_action(self, node: ConditionNode, operation: str, _checked: bool = False) -> None:
        """Resolve a context action against the current tree, never old indexes."""
        parent = self.model.parent(node)
        if parent is None:
            return
        index = parent.children.index(node)
        if operation == "up" and index > 0:
            self.move_node(node, parent.children[index - 1], ConditionDrop.BEFORE)
        elif operation == "down" and index + 1 < len(parent.children):
            self.move_node(node, parent.children[index + 1], ConditionDrop.AFTER)
        elif operation == "indent" and index > 0:
            self.model.group_with_previous(node)
            self.selected = node
            self.refresh()
        elif operation == "outdent" and parent is not self.model.root:
            self.move_node(node, parent, ConditionDrop.AFTER)
        elif operation == "ungroup" and node.match is not None:
            self.model.ungroup(node)
            self.refresh()
