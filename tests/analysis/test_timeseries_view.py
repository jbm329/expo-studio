from __future__ import annotations

import dataclasses

import pandas as pd
import pytest
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from PyQt6.QtCore import QCoreApplication, Qt
from PyQt6.QtWidgets import QLabel, QScrollArea

from expo_jbm329.gui.dialogs.analysis.timeseries_view import TimeSeriesView
from expo_jbm329.services.analysis.timeseries import TimeSeriesError, analyze_time_series


def _result():
    df = pd.DataFrame({"when": pd.date_range("2025-01-01", periods=28, freq="D"), "value": range(28)})
    result = analyze_time_series(df)
    assert result.error is None
    return result


def _labels_text(view: TimeSeriesView) -> str:
    return "\n".join(label.text() for label in view.findChildren(QLabel))


@pytest.mark.parametrize("error", list(TimeSeriesError))
def test_every_error_has_a_message(error):
    assert TimeSeriesView(_result()).error_text(error)


def test_error_contains_no_canvases():
    view = TimeSeriesView(dataclasses.replace(_result(), error=TimeSeriesError.NOT_ENOUGH_OBSERVATIONS))

    assert view.findChildren(FigureCanvasQTAgg) == []
    assert "At least 3" in _labels_text(view)


def test_regular_result_shows_series_acf_and_decomposition():
    view = TimeSeriesView(_result())
    canvases = view.findChildren(FigureCanvasQTAgg)

    assert len(canvases) == 3
    assert {axis.get_title() for canvas in canvases for axis in canvas.figure.axes} >= {
        "Series",
        "Autocorrelation",
        "Seasonal decomposition",
    }


def test_unavailable_diagnostics_and_decomposition_show_explanations():
    df = pd.DataFrame({
        "when": pd.to_datetime(["2025-01-01", "2025-01-02", "2025-01-04", "2025-01-05"]),
        "value": [1.0, 2.0, 3.0, 4.0],
    })
    result = analyze_time_series(df)
    view = TimeSeriesView(result)

    assert result.error is None
    canvases = view.findChildren(FigureCanvasQTAgg)
    assert len(canvases) == 3
    assert all(len(canvas.figure.axes) == 1 for canvas in canvases)


def test_summary_reports_cleaning_statistics():
    result = dataclasses.replace(_result(), invalid_rows=2, duplicate_rows=3)
    view = TimeSeriesView(result)

    text = _labels_text(view)
    assert "2 invalid rows" in text
    assert "3 duplicate rows" in text


def test_summary_is_separate_top_aligned_and_keeps_fixed_gap_when_resized():
    view = TimeSeriesView(_result())
    view.resize(1100, 800)
    view.show()
    try:
        QCoreApplication.processEvents()
        panel = view.layout().itemAt(0).widget()
        heading = panel.layout().itemAt(0).widget()
        text = panel.layout().itemAt(1).widget()
        scroll = view.findChild(QScrollArea)
        assert heading.text() == "Summary"
        assert not scroll.isAncestorOf(panel)
        assert text.alignment() == Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        assert heading.y() == panel.layout().contentsMargins().top()
        gap = text.y() - heading.geometry().bottom()
        height = panel.height()
        scroll_height = scroll.height()
        view.resize(1100, 1100)
        QCoreApplication.processEvents()
        assert text.y() - heading.geometry().bottom() == gap
        assert panel.height() == height
        assert scroll.height() > scroll_height
        assert len(scroll.findChildren(FigureCanvasQTAgg)) == 3
    finally:
        view.close()
