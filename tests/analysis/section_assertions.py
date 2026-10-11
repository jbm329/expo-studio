"""Shared assertions for scrollable analysis result sections."""

from __future__ import annotations

from PyQt6.QtCore import QCoreApplication, Qt
from PyQt6.QtWidgets import QLabel, QScrollArea, QWidget


def assert_section_scrolls_below_frozen_title(panel: QWidget, small_height: int, large_height: int = 900) -> QWidget:
    """Assert `panel` is a fixed title above content that scrolls only when needed.

    The panel is detached from its view and shown at both heights.

    Args:
        panel: Titled section built by an analysis view.
        small_height: Height at which the content must overflow.
        large_height: Height at which the content must fit.

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
    panel.resize(1100, small_height)
    panel.show()
    try:
        QCoreApplication.processEvents()
        bar = scroll.verticalScrollBar()
        assert bar is not None
        assert bar.maximum() > 0
        title_geometry = title.geometry()
        bar.setValue(bar.maximum())
        QCoreApplication.processEvents()
        assert title.geometry() == title_geometry

        panel.resize(1100, large_height)
        QCoreApplication.processEvents()
        assert title.geometry() == title_geometry
        assert bar.maximum() == 0
        horizontal = scroll.horizontalScrollBar()
        assert horizontal is not None
        assert horizontal.maximum() == 0
    finally:
        panel.close()
    return content
