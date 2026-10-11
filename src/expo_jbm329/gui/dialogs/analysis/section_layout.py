"""Shared layout helpers for titled analysis result sections."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QScrollArea, QWidget


def build_section_scroll_area(content: QWidget, parent: QWidget) -> QScrollArea:
    """Wrap section content so it scrolls only when it exceeds the section.

    The section title is placed outside the returned area, which keeps it
    visible while the content scrolls.

    Args:
        content: Chart, splitter or text widget shown in the section.
        parent: Section panel that owns the scroll area.

    Returns:
        A resizable scroll area with scrollbars shown only when needed.
    """
    scroll = QScrollArea(parent)
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    scroll.setWidget(content)
    return scroll
