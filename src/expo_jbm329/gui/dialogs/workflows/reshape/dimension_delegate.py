"""Partial text emphasis for the checkable dimension list."""

from html import escape
from typing import override

from PyQt6.QtCore import QModelIndex, QSize, Qt
from PyQt6.QtGui import QAbstractTextDocumentLayout, QFont, QPainter, QPalette, QTextDocument
from PyQt6.QtWidgets import QApplication, QStyle, QStyledItemDelegate, QStyleOptionViewItem

COLUMN_NAME_ROLE = int(Qt.ItemDataRole.UserRole) + 1
DTYPE_ROLE = int(Qt.ItemDataRole.UserRole) + 2


class DimensionDelegate(QStyledItemDelegate):
    """Draw bold column names while retaining native checkboxes and selection."""

    @staticmethod
    def _document(option: QStyleOptionViewItem, index: QModelIndex) -> QTextDocument:
        document = QTextDocument()
        document.setDocumentMargin(0)
        font = QFont(option.font)
        font.setBold(False)
        document.setDefaultFont(font)
        name = escape(str(index.data(COLUMN_NAME_ROLE)))
        dtype = escape(str(index.data(DTYPE_ROLE)))
        document.setHtml(f'<span style="white-space: pre;"><b>{name}</b> [{dtype}]</span>')
        return document

    @override
    def paint(self, painter: QPainter | None, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        """Paint native item chrome and partially bold text."""
        if painter is None:
            return
        styled = QStyleOptionViewItem(option)
        self.initStyleOption(styled, index)
        style = QApplication.style()
        if style is None:
            return
        text_rect = style.subElementRect(QStyle.SubElement.SE_ItemViewItemText, styled, styled.widget)
        document = self._document(styled, index)
        styled.text = ""
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, styled, painter, styled.widget)

        context = QAbstractTextDocumentLayout.PaintContext()
        context.palette = QPalette(styled.palette)
        if styled.state & QStyle.StateFlag.State_Selected:
            context.palette.setColor(QPalette.ColorRole.Text, styled.palette.color(QPalette.ColorRole.HighlightedText))
        layout = document.documentLayout()
        if layout is not None:
            painter.save()
            painter.setClipRect(text_rect)
            painter.translate(text_rect.left(), text_rect.top() + (text_rect.height() - document.size().height()) / 2)
            layout.draw(painter, context)
            painter.restore()

    @override
    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        """Include the bold name's extra width in horizontal scrolling."""
        styled = QStyleOptionViewItem(option)
        self.initStyleOption(styled, index)
        size = super().sizeHint(styled, index)
        document = self._document(styled, index)
        extra_width = max(0, int(document.idealWidth() + 1) - styled.fontMetrics.horizontalAdvance(styled.text))
        return QSize(size.width() + extra_width, max(size.height(), int(document.size().height() + 1)))
