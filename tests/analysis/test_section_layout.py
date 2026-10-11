from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QWidget

from expo_jbm329.gui.dialogs.analysis.section_layout import build_section_scroll_area


def test_section_scroll_area_owns_content_and_shows_scrollbars_only_when_needed():
    parent = QWidget()
    content = QLabel("Content")

    scroll = build_section_scroll_area(content, parent)

    assert scroll.parentWidget() is parent
    assert scroll.widget() is content
    assert scroll.widgetResizable()
    assert scroll.horizontalScrollBarPolicy() is Qt.ScrollBarPolicy.ScrollBarAsNeeded
    assert scroll.verticalScrollBarPolicy() is Qt.ScrollBarPolicy.ScrollBarAsNeeded
    parent.deleteLater()
