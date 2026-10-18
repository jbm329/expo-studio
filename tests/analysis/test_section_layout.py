from __future__ import annotations

import pytest
from PyQt6.QtCore import QCoreApplication, Qt
from PyQt6.QtGui import QPalette
from PyQt6.QtWidgets import QFrame, QLabel, QScrollArea, QVBoxLayout, QWidget

from expo_jbm329.gui.dialogs.analysis.applied_configuration_header import AppliedConfigurationHeader
from expo_jbm329.gui.dialogs.analysis.section_layout import (
    AnalysisResultSection,
    build_section_scroll_area,
    rich_text_lines,
)
from expo_jbm329.services.analysis.presentation import AnalysisPresentation
from tests.analysis.section_assertions import assert_section_scrolls_below_frozen_title


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


def test_result_section_uses_regular_header_frame_and_padding_without_inner_border() -> None:
    parent = QWidget()
    header = AppliedConfigurationHeader(AnalysisPresentation("Hypothesis Tests", "Group comparison"), parent)
    content = QLabel("Results")
    panel = AnalysisResultSection("Test results", content, parent)
    layout = panel.layout()
    assert layout is not None
    header_layout = header.layout()
    assert header_layout is not None
    assert panel.parentWidget() is parent
    assert panel.frameShape() is header.frameShape() is QFrame.Shape.StyledPanel
    assert panel.frameShadow() is header.frameShadow() is QFrame.Shadow.Plain
    assert panel.lineWidth() == header.lineWidth() == 1
    assert panel.frameWidth() == header.frameWidth()
    assert layout.contentsMargins() == header_layout.contentsMargins()
    heading = layout.itemAt(0).widget()
    assert isinstance(heading, QLabel)
    assert heading.text() == "Test results"
    assert heading.font().bold()
    assert heading.textFormat() is Qt.TextFormat.PlainText
    scroll = layout.itemAt(1).widget()
    assert isinstance(scroll, QScrollArea)
    assert scroll.parentWidget() is panel
    assert scroll.widget() is content
    assert content.parentWidget() is scroll.viewport()
    assert scroll.frameShape() is QFrame.Shape.NoFrame
    assert scroll.frameWidth() == 0
    assert not scroll.viewport().autoFillBackground()
    assert not content.autoFillBackground()
    assert not panel.styleSheet()
    assert not scroll.styleSheet()
    parent.deleteLater()


@pytest.mark.parametrize("container", [False, True])
def test_result_section_wraps_and_scrolls_all_text_below_fixed_title(container: bool) -> None:
    label = QLabel("<br>".join(["<b>Results</b>: " + "wrapped measurement " * 12] * 12))
    label.setWordWrap(True)
    label.setTextFormat(Qt.TextFormat.RichText)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    content: QWidget = label
    if container:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(label)
        warning = QLabel("Last warning: " + "complete cohort " * 12)
        warning.setWordWrap(True)
        layout.addWidget(warning)
        layout.addStretch(1)
    panel = AnalysisResultSection("Test results", content)
    try:
        assert content.hasHeightForWidth()
        assert content.heightForWidth(300) > content.heightForWidth(1100)
        assert_section_scrolls_below_frozen_title(panel, 100, large_height=1800)
        panel.resize(350, 120)
        panel.show()
        QCoreApplication.processEvents()
        scroll = panel.findChild(QScrollArea)
        assert scroll is not None
        bar = scroll.verticalScrollBar()
        assert bar is not None
        assert bar.maximum() > 0
        bar.setValue(bar.maximum())
        QCoreApplication.processEvents()
        viewport = scroll.viewport()
        assert viewport is not None
        assert content.geometry().bottom() <= viewport.rect().bottom()
        if container:
            assert warning.geometry().bottom() < content.height()
            assert warning.height() >= warning.heightForWidth(warning.width())
        else:
            assert label.height() >= label.heightForWidth(label.width())
    finally:
        panel.close()
        panel.deleteLater()


def test_result_section_scrolls_horizontally_for_non_wrapping_identifiers() -> None:
    content = QLabel("measurement_identifier_" * 60)
    panel = AnalysisResultSection("Test results", content)
    panel.resize(400, 150)
    panel.show()
    try:
        QCoreApplication.processEvents()
        scroll = panel.findChild(QScrollArea)
        assert scroll is not None
        bar = scroll.horizontalScrollBar()
        assert bar is not None
        assert bar.maximum() > 0
        bar.setValue(bar.maximum())
        QCoreApplication.processEvents()
        assert content.geometry().right() <= scroll.viewport().rect().right()
    finally:
        panel.close()
        panel.deleteLater()


@pytest.mark.parametrize("dark", [False, True])
def test_result_section_renders_header_background_instead_of_viewport_base(dark: bool) -> None:
    parent = QWidget()
    palette = parent.palette()
    window = palette.color(QPalette.ColorRole.Window)
    palette.setColor(QPalette.ColorRole.Window, window.darker(250) if dark else window.lighter(120))
    palette.setColor(QPalette.ColorRole.Base, window.lighter(180) if dark else window.darker(180))
    parent.setPalette(palette)
    header = AppliedConfigurationHeader(AnalysisPresentation("Hypothesis Tests", "Group comparison"), parent)
    panel = AnalysisResultSection("Test results", QLabel("Results"), parent)
    header.resize(500, 100)
    panel.setGeometry(0, 110, 500, 250)
    parent.resize(500, 360)
    parent.show()
    try:
        QCoreApplication.processEvents()
        # Compare the composite: native styles may paint StyledPanel's background
        # with Base instead of Window, and isolated grabs omit that ancestor paint.
        image = parent.grab().toImage()
        scale = image.devicePixelRatio()
        expected = image.pixelColor(round(250 * scale), round(80 * scale))
        # Compare 8-bit RGB values: a grabbed pixel and a palette color derived via
        # darker()/lighter() can carry different internal precision despite being
        # visually identical.
        expected_rgb = expected.rgb()
        assert expected_rgb in (
            palette.color(QPalette.ColorRole.Window).rgb(),
            palette.color(QPalette.ColorRole.Base).rgb(),
        )
        assert image.pixelColor(round(250 * scale), round(340 * scale)).rgb() == expected_rgb
        scroll = panel.findChild(QScrollArea)
        assert scroll is not None
        viewport = scroll.viewport()
        assert viewport is not None
        point = viewport.mapTo(parent, viewport.rect().bottomLeft())
        assert image.pixelColor(round((point.x() + 20) * scale), round((point.y() - 20) * scale)).rgb() == expected_rgb
    finally:
        parent.close()
        parent.deleteLater()


def test_rich_text_lines_split_breaks_strip_markup_and_drop_empty_lines():
    lines = rich_text_lines(("<b>Model</b>: a &lt; b<br><br>  second ", "third<br>"))
    assert lines == ("Model: a < b", "second", "third")
    assert rich_text_lines(()) == ()
    assert rich_text_lines(("R<sup>2</sup> = 0.9; x<sup>10</sup>",)) == ("R² = 0.9; x¹⁰",)
