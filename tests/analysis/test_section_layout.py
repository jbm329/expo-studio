from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QWidget

from expo_jbm329.gui.dialogs.analysis.section_layout import build_section_scroll_area, rich_text_lines


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


def test_rich_text_lines_split_breaks_strip_markup_and_drop_empty_lines():
    lines = rich_text_lines(("<b>Model</b>: a &lt; b<br><br>  second ", "third<br>"))
    assert lines == ("Model: a < b", "second", "third")
    assert rich_text_lines(()) == ()
    assert rich_text_lines(("R<sup>2</sup> = 0.9; x<sup>10</sup>",)) == ("R² = 0.9; x¹⁰",)
