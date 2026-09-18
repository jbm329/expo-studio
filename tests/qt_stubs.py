from __future__ import annotations

from types import SimpleNamespace

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont


class DummySignal:
    def __init__(self):
        self.cbs = []

    def connect(self, cb):
        self.cbs.append(cb)

    def emit(self, *a):
        [cb(*a) for cb in self.cbs]


class StubTreeItem:
    """Qt-liknande QTreeWidgetItem-stub som klarar: text, children, setData/data, flags, setIcon."""

    ChildIndicatorPolicy = SimpleNamespace(ShowIndicator=1)

    def __init__(self, texts, meta=None):
        self._texts = list(texts)
        self._meta = meta or {}
        self._children = []
        self._expanded = False
        # Viktigt: håll flaggor som Qt.ItemFlag/Flags så OR med Qt.ItemFlag fungerar
        self._flags = Qt.ItemFlag(0)

    def text(self, column):
        return self._texts[column]

    def setText(self, column, value):
        self._texts[column] = value

    def addChild(self, item):
        self._children.append(item)

    def addChildren(self, items):
        self._children.extend(items)

    def child(self, idx):
        return self._children[idx]

    def childCount(self):
        return len(self._children)

    def takeChild(self, idx):
        return self._children.pop(idx)

    def takeChildren(self):
        children = list(self._children)
        self._children = []
        return children

    def data(self, col, role):
        return self._meta

    def setData(self, col, role, value):
        self._meta = value

    def setIcon(self, col, icon):
        pass

    def font(self, column):
        return QFont()

    def setFont(self, column, font):
        pass

    def setChildIndicatorPolicy(self, policy):
        pass

    def setExpanded(self, value):
        self._expanded = value

    def setFlags(self, flags):
        try:
            self._flags = Qt.ItemFlag(int(flags))
        except (
            AttributeError,
            ConnectionError,
            FileNotFoundError,
            IndexError,
            KeyError,
            LookupError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ):
            self._flags = flags

    def flags(self):
        return self._flags


class StubTree:
    """Qt-liknande QTreeWidget-stub som klarar addTopLevelItem, expandItem, itemAt, viewport."""

    def __init__(self):
        self.top = []
        self.customContextMenuRequested = DummySignal()
        self.itemDoubleClicked = DummySignal()
        self.itemExpanded = DummySignal()

    def clear(self):
        self.top = []

    def addTopLevelItem(self, item):
        self.top.append(item)

    def topLevelItemCount(self):
        return len(self.top)

    def topLevelItem(self, index):
        return self.top[index]

    def expandItem(self, item):
        item.setExpanded(True)

    def repaint(self):
        pass

    def viewport(self):
        return SimpleNamespace(mapToGlobal=lambda p: p)

    def itemAt(self, pos):
        # Returnera första tabell/vy-barnet för enkelhet
        if self.top:
            root = self.top[0]
            group = root.child(0) if root.childCount() else None
            if group and group.childCount():
                return group.child(0)
        return None
