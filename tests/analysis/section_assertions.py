"""Shared assertions for scrollable analysis result sections."""

from __future__ import annotations

from PyQt6.QtCore import QCoreApplication, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QLabel, QScrollArea, QWidget


def _wait_for(predicate, timeout_ms: int = 500) -> None:
    elapsed = 0
    while not predicate() and elapsed < timeout_ms:
        QTest.qWait(10)
        elapsed += 10


def assert_section_scrolls_below_frozen_title(
    panel: QWidget, small_height: int, large_height: int = 900, width: int = 1100
) -> QWidget:
    """Assert `panel` is a fixed title above content that scrolls only when needed.

    The panel is detached from its view and shown at both heights.

    Args:
        panel: Titled section built by an analysis view.
        small_height: Height at which the content must overflow.
        large_height: Height at which the content must fit.
        width: Panel width used at both heights.

    Returns:
        The content widget inside the section scroll area.
    """
    layout = panel.layout()
    assert layout is not None
    title = layout.itemAt(0).widget()
    scroll = layout.itemAt(1).widget()
    assert isinstance(title, QLabel)
    assert isinstance(scroll, QScrollArea)
    assert layout.stretch(1) == 1
    assert scroll.widgetResizable()
    assert scroll.verticalScrollBarPolicy() is Qt.ScrollBarPolicy.ScrollBarAsNeeded
    assert scroll.horizontalScrollBarPolicy() is Qt.ScrollBarPolicy.ScrollBarAsNeeded
    content = scroll.widget()
    assert content is not None

    panel.setParent(None)
    panel.resize(width, small_height)
    panel.show()
    try:
        bar = scroll.verticalScrollBar()
        assert bar is not None
        _wait_for(lambda: bar.maximum() > 0)
        assert bar.maximum() > 0
        title_geometry = title.geometry()
        bar.setValue(bar.maximum())
        QCoreApplication.processEvents()
        assert title.geometry() == title_geometry

        panel.resize(width, large_height)
        _wait_for(lambda: bar.maximum() == 0 and panel.height() == large_height)
        assert title.geometry() == title_geometry
        assert bar.maximum() == 0
        horizontal = scroll.horizontalScrollBar()
        assert horizontal is not None
        assert horizontal.maximum() == 0
    finally:
        panel.close()
    return content
