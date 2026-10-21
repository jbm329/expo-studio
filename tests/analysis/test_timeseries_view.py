from __future__ import annotations

import dataclasses
from pathlib import Path

import pandas as pd
import pytest
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from PyQt6.QtCore import QCoreApplication, Qt, QTranslator
from PyQt6.QtWidgets import QLabel, QSplitter

from expo_jbm329.gui.dialogs.analysis import timeseries_view as timeseries_view_module
from expo_jbm329.gui.dialogs.analysis.timeseries_view import TimeSeriesView
from expo_jbm329.services.analysis.chart_presentation import ChartPresentationMetadata
from expo_jbm329.services.analysis.timeseries import DecompositionModel, TimeSeriesError, analyze_time_series
from expo_jbm329.services.analysis.timeseries_charts import TimeSeriesChartLabels
from tests.analysis.section_assertions import assert_section_scrolls_below_frozen_title


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


def _section_title(panel) -> str:
    title = panel.layout().itemAt(0).widget()
    assert isinstance(title, QLabel)
    assert title.textFormat() is Qt.TextFormat.PlainText
    assert title.font().bold()
    return title.text()


def test_layout_has_resizable_charts_and_comments_sections_like_regression():
    view = TimeSeriesView(_result())

    splitters = view.findChildren(QSplitter)
    assert len(splitters) == 1
    splitter = splitters[0]
    assert splitter.orientation() is Qt.Orientation.Vertical
    assert splitter.childrenCollapsible() is False
    assert [_section_title(splitter.widget(index)) for index in range(splitter.count())] == [
        "Charts",
        "Model comments",
    ]
    assert len(splitter.widget(0).findChildren(FigureCanvasQTAgg)) == 3


@pytest.mark.parametrize(("section", "small_height", "width"), [(0, 300, 1100), (1, 50, 150)])
def test_charts_and_comments_scroll_below_a_frozen_title(section, small_height, width):
    view = TimeSeriesView(_result())
    panel = view.findChild(QSplitter).widget(section)

    content = assert_section_scrolls_below_frozen_title(
        panel, small_height, large_height=1200, width=width, result_section=section == 1, content_sized=section == 0
    )

    if section == 0:
        assert len(content.findChildren(FigureCanvasQTAgg)) == 3
    else:
        assert isinstance(content, QLabel)
        assert content.textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByMouse
        assert "time points" in content.text()
    panel.deleteLater()
    view.close()


def _irregular_result():
    df = pd.DataFrame({
        "when": pd.to_datetime(["2025-01-01", "2025-01-02", "2025-01-04", "2025-01-05"]),
        "value": [1.0, 2.0, 3.0, 4.0],
    })
    result = analyze_time_series(df)
    assert result.error is None
    return result


def test_result_returns_the_displayed_analysis():
    result = _result()

    assert TimeSeriesView(result).result() is result


def test_chart_labels_use_value_column_and_translated_titles():
    labels = TimeSeriesView(_result()).chart_labels()

    assert labels == TimeSeriesChartLabels(
        series_metadata=ChartPresentationMetadata(worksheet_heading="", accessible_name="Series"),
        value_axis="value",
        acf_metadata=ChartPresentationMetadata(worksheet_heading="", accessible_name="Autocorrelation"),
        lag_axis="Lag",
        acf_axis="Autocorrelation",
        decomposition_metadata=ChartPresentationMetadata(
            worksheet_heading="", accessible_name="Seasonal decomposition"
        ),
        observed="Observed",
        trend="Trend",
        seasonal="Seasonal",
        residual="Residual",
    )


def test_chart_labels_use_the_shared_presentation_translation_context(monkeypatch):
    monkeypatch.setattr(
        timeseries_view_module,
        "tr",
        lambda context, text: f"sv:{text}" if context == "TimeSeriesPresentation" else text,
    )

    labels = TimeSeriesView(_result()).chart_labels()

    assert labels == TimeSeriesChartLabels(
        series_metadata=ChartPresentationMetadata(worksheet_heading="", accessible_name="sv:Series"),
        value_axis="value",
        acf_metadata=ChartPresentationMetadata(worksheet_heading="", accessible_name="sv:Autocorrelation"),
        lag_axis="sv:Lag",
        acf_axis="sv:Autocorrelation",
        decomposition_metadata=ChartPresentationMetadata(
            worksheet_heading="", accessible_name="sv:Seasonal decomposition"
        ),
        observed="sv:Observed",
        trend="sv:Trend",
        seasonal="sv:Seasonal",
        residual="sv:Residual",
    )


def test_export_notes_contain_summary_and_decomposition_model():
    notes = TimeSeriesView(_result()).export_notes()

    assert notes[-1] == "Decomposition model: Additive"
    assert any("28" in line for line in notes[:-1])
    assert all("<" not in line for line in notes)


def test_export_notes_name_multiplicative_model_and_unavailability_reasons():
    result = dataclasses.replace(_irregular_result(), decomposition_model=DecompositionModel.MULTIPLICATIVE)

    notes = TimeSeriesView(result).export_notes()

    assert notes[-3:] == (
        "Decomposition model: Multiplicative",
        "The autocorrelation requires a regular time frequency.",
        "Seasonal decomposition requires a regular time frequency.",
    )


def test_export_notes_are_empty_for_errors():
    result = dataclasses.replace(_result(), error=TimeSeriesError.NOT_ENOUGH_OBSERVATIONS)

    assert TimeSeriesView(result).export_notes() == ()


def test_autocorrelation_note_is_empty_when_available():
    assert TimeSeriesView(_result()).autocorrelation_note() == ""


def test_autocorrelation_note_explains_unavailable_acf():
    view = TimeSeriesView(_irregular_result())

    assert view.autocorrelation_note() == "The autocorrelation requires a regular time frequency."


@pytest.mark.parametrize(
    "note",
    [
        "The autocorrelation requires a regular time frequency.",
        "The autocorrelation is unavailable while the series has gaps.",
        "Seasonal decomposition requires a regular time frequency.",
        "Seasonal decomposition is unavailable while the series has gaps.",
        "No seasonal period could be detected. Choose one to decompose the series.",
        "Seasonal decomposition needs at least two complete seasonal cycles.",
        "Multiplicative decomposition requires all values to be greater than zero.",
    ],
)
def test_note_text_translates_known_service_notes(monkeypatch, note):
    view = TimeSeriesView(_result())
    monkeypatch.setattr(view, "tr", lambda text: f"sv:{text}")

    assert view.note_text(note) == f"sv:{note}"


def test_note_text_keeps_unknown_notes():
    assert TimeSeriesView(_result()).note_text("Something else; keep punctuation.") == (
        "Something else; keep punctuation."
    )


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("en", "No seasonal period could be detected. Choose one to decompose the series."),
        ("sv", "Ingen säsongsperiod kunde identifieras. Välj en för att dekomponera serien."),
    ],
)
def test_seasonal_note_uses_compiled_translation_with_sentence_capitalization(language: str, expected: str) -> None:
    translator = QTranslator()
    locales = Path(__file__).parents[2] / "src" / "expo_jbm329" / "i18n" / "locales"
    assert translator.load(str(locales / f"app_{language}.qm"))
    assert QCoreApplication.installTranslator(translator)
    view = TimeSeriesView(_result())
    try:
        assert view.note_text("No seasonal period could be detected. Choose one to decompose the series.") == expected
    finally:
        view.close()
        QCoreApplication.removeTranslator(translator)


def test_unavailable_placeholders_show_translated_notes(monkeypatch):
    monkeypatch.setattr(TimeSeriesView, "tr", lambda _self, text: f"sv:{text}")

    view = TimeSeriesView(_irregular_result())

    texts = {
        text.get_text()
        for canvas in view.findChildren(FigureCanvasQTAgg)
        for axis in canvas.figure.axes
        for text in axis.texts
    }
    assert texts == {
        "sv:The autocorrelation requires a regular time frequency.",
        "sv:Seasonal decomposition requires a regular time frequency.",
    }
