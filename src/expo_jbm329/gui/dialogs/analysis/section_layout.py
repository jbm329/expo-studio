"""Shared layout helpers for titled analysis result sections."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTextDocumentFragment
from PyQt6.QtWidgets import QFrame, QLabel, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

if TYPE_CHECKING:
    from collections.abc import Iterable

_DIGIT_SUPERSCRIPT = re.compile(r"<sup>(\d+)</sup>")
_SUPERSCRIPT_DIGITS = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")
ANALYSIS_FRAME_MARGINS = (10, 8, 10, 8)

ANALYSIS_TABS_STYLE = (
    "QTabBar::tab { padding: 4px 10px 6px; border: none; border-bottom: 2px solid transparent; }"
    "QTabBar::tab:selected { border-bottom-color: palette(highlight); }"
)


def _plain_superscripts(text: str) -> str:
    """Keep numeric superscripts such as R² readable once markup is removed."""
    return _DIGIT_SUPERSCRIPT.sub(lambda match: match.group(1).translate(_SUPERSCRIPT_DIGITS), text)


def rich_text_lines(texts: Iterable[str]) -> tuple[str, ...]:
    """Convert ``<br>``-separated section rich text into non-empty plain-text lines.

    Used to export the exact displayed comments without scraping widgets.

    Args:
        texts: Rich-text blocks whose lines are separated by ``<br>``.

    Returns:
        Plain-text lines with markup removed and entities decoded.
    """
    lines: list[str] = []
    for text in texts:
        for part in _plain_superscripts(text).split("<br>"):
            line = QTextDocumentFragment.fromHtml(part).toPlainText().strip()
            if line:
                lines.append(line)
    return tuple(lines)


def apply_analysis_frame(frame: QFrame) -> None:
    """Apply the native, plain border used for framed analysis content."""
    frame.setFrameShape(QFrame.Shape.StyledPanel)
    frame.setFrameShadow(QFrame.Shadow.Plain)
    frame.setLineWidth(1)


class AnalysisResultSection(QFrame):
    """Native framed result panel with a fixed title and independently scrolling content."""

    def __init__(self, title: str, content: QWidget, parent: QWidget | None = None) -> None:
        """Build a result section using the applied configuration header's frame.

        Args:
            title: Plain-text heading that remains visible when scrolling.
            content: Result widget whose ownership transfers to the scroll area.
            parent: Optional owning widget.
        """
        super().__init__(parent)
        apply_analysis_frame(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*ANALYSIS_FRAME_MARGINS)
        heading = QLabel(title, self)
        heading.setTextFormat(Qt.TextFormat.PlainText)
        heading.setWordWrap(True)
        heading.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        font = heading.font()
        font.setBold(True)
        heading.setFont(font)
        layout.addWidget(heading)

        scroll = build_section_scroll_area(content, self)
        # A regular outer frame paints like the header even on native Windows styles.
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)
        viewport = scroll.viewport()
        if viewport is not None:
            viewport.setAutoFillBackground(False)
        # QScrollArea.setWidget enables background filling on the content.
        content.setAutoFillBackground(False)
        layout.addWidget(scroll, 1)


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
