"""Shared assertions for scrollable analysis result sections."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QCoreApplication, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QLabel, QScrollArea, QWidget

from expo_jbm329.gui.dialogs.analysis.section_layout import AnalysisResultSection

if TYPE_CHECKING:
    from collections.abc import Callable


def _wait_for(predicate: Callable[[], bool], timeout_ms: int = 2000) -> None:
    elapsed = 0
    while not predicate() and elapsed < timeout_ms:
        QTest.qWait(10)
        elapsed += 10


def _required_content_height(content: QWidget, viewport_width: int) -> int:
    """Return the height a resizable scroll area must give `content` at `viewport_width`.

    Mirrors how `QScrollArea` sizes a resizable widget: height-for-width when supported,
    otherwise the effective minimum size.
    """
    if content.hasHeightForWidth():
        return content.heightForWidth(viewport_width)
    return max(content.minimumSize().height(), content.minimumSizeHint().height())


def _overflow_height(
    panel: QWidget, title: QLabel | None, scroll: QScrollArea, content: QWidget, small_height: int
) -> int:
    """Return a panel height at which the section content is guaranteed to overflow.

    Text content depends on the available fonts (e.g. a bare CI runner using the offscreen
    platform), so a fixed caller height alone is not reliable. The returned height never
    exceeds `small_height`, keeping caller expectations intact.
    """
    layout = panel.layout()
    assert layout is not None
    viewport = scroll.viewport()
    assert viewport is not None
    required = _required_content_height(content, viewport.width())
    assert required >= 2, (
        f"Section content reports no measurable height (required={required}, "
        f"sizeHint={content.sizeHint()}, minimumSizeHint={content.minimumSizeHint()}, "
        f"font={content.font().family()!r}); check that fonts are available."
    )
    margins = layout.contentsMargins()
    chrome = margins.top() + margins.bottom() + 2 * scroll.frameWidth()
    if isinstance(panel, AnalysisResultSection):
        chrome += 2 * panel.frameWidth()
    if title is not None:
        chrome += title.height() + layout.spacing()
    return min(small_height, chrome + required // 2)


def assert_section_scrolls_below_frozen_title(
    panel: QWidget, small_height: int, large_height: int = 900, width: int = 1100, *, titled: bool = True
) -> QWidget:
    """Assert `panel` is a fixed title above content that scrolls only when needed.

    The panel is detached from its view and shown at both heights.

    Args:
        panel: Titled section built by an analysis view.
        small_height: Height at which the content must overflow.
        large_height: Height at which the content must fit.
        width: Panel width used at both heights.
        titled: Whether a separate fixed title precedes the scroll area.

    Returns:
        The content widget inside the section scroll area.
    """
    layout = panel.layout()
    assert layout is not None
    title = layout.itemAt(0).widget() if titled else None
    scroll_index = 1 if titled else 0
    scroll = layout.itemAt(scroll_index).widget()
    if titled:
        assert isinstance(title, QLabel)
    assert isinstance(scroll, QScrollArea)
    assert layout.stretch(scroll_index) == 1
    assert scroll.widgetResizable()
    assert scroll.verticalScrollBarPolicy() is Qt.ScrollBarPolicy.ScrollBarAsNeeded
    assert scroll.horizontalScrollBarPolicy() is Qt.ScrollBarPolicy.ScrollBarAsNeeded
    content = scroll.widget()
    assert content is not None

    panel.setParent(None)
    # The scroll area's default minimum size hint can exceed short font-dependent content and
    # keep the detached panel too tall to overflow; the behavior under test is the scrolling.
    if not isinstance(panel, AnalysisResultSection):
        scroll.setMinimumHeight(1)
    panel.resize(width, small_height)
    panel.show()
    try:
        bar = scroll.verticalScrollBar()
        assert bar is not None
        QCoreApplication.processEvents()
        panel.resize(width, _overflow_height(panel, title, scroll, content, small_height))
        _wait_for(lambda: bar.maximum() > 0)
        viewport = scroll.viewport()
        assert viewport is not None
        assert bar.maximum() > 0, (
            f"Content did not overflow: panel={panel.size()}, viewport={viewport.size()}, "
            f"content={content.size()}, font={content.font().family()!r}"
        )
        title_geometry = title.geometry() if title is not None else None
        bar.setValue(bar.maximum())
        QCoreApplication.processEvents()
        if title is not None:
            assert title.geometry() == title_geometry

        panel.resize(width, large_height)
        _wait_for(lambda: bar.maximum() == 0 and panel.height() == large_height)
        if title is not None:
            assert title.geometry() == title_geometry
        assert bar.maximum() == 0
        horizontal = scroll.horizontalScrollBar()
        assert horizontal is not None
        assert horizontal.maximum() == 0
        if isinstance(panel, AnalysisResultSection):
            assert content.height() >= _required_content_height(content, content.width())
    finally:
        panel.close()
    return content
