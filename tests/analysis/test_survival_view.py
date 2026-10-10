from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd
import pytest
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from PyQt6.QtCore import QCoreApplication, Qt
from PyQt6.QtWidgets import QLabel, QSplitter, QTableWidget

from expo_jbm329.gui.dialogs.analysis.survival_view import SurvivalRegressionView
from expo_jbm329.services.analysis.survival import (
    SurvivalError,
    _survival_plot_data,  # noqa: PLC2701
    analyze_cox_regression,
    survival_term_name,
)
from expo_jbm329.utils.format_utils import fmt_int, fmt_num


def _result():
    rng = np.random.default_rng(17)
    size = 180
    x = rng.normal(size=size)
    event_time = rng.exponential(scale=np.exp(-0.4 * x), size=size)
    censor_time = rng.exponential(scale=1.7, size=size)
    event = event_time <= censor_time
    frame = pd.DataFrame({
        "duration": np.minimum(event_time, censor_time),
        "event": event.astype(int),
        "group": np.where(np.arange(size) % 2, "treated", "control"),
        "x": x,
    })
    return analyze_cox_regression(frame, "duration", "event", ["x", "group"])


def _text(view: SurvivalRegressionView) -> str:
    return "\n".join(label.text() for label in view.findChildren(QLabel))


def test_cox_view_shows_hazard_ratio_table_counts_reference_and_caveats():
    result = _result()
    assert result.error is None
    view = SurvivalRegressionView(result)

    table = view.table()
    assert table is not None
    assert table.selectionMode() is QTableWidget.SelectionMode.NoSelection
    assert table.horizontalHeaderItem(2).text() == "Hazard ratio"
    assert table.rowCount() == len(result.terms)
    text = _text(view)
    assert "Event coding: 1 = event; 0 = censored." in text
    assert f"Events: {result.n_events}; censored: {result.n_censored}" in text
    assert "Reference for group:" in text
    assert "Efron" in text
    assert "proportional-hazards assumption was not assessed" in text


def test_cox_coefficient_columns_remain_content_sized_in_a_wide_view():
    view = SurvivalRegressionView(_result())
    table = view.table()
    assert table is not None
    assert not table.horizontalHeader().stretchLastSection()
    widths = [table.columnWidth(column) for column in range(table.columnCount())]
    view.resize(1600, 900)
    view.show()
    try:
        QCoreApplication.processEvents()
        assert [table.columnWidth(column) for column in range(table.columnCount())] == widths
        assert sum(widths) < table.viewport().width()
    finally:
        view.close()


@pytest.mark.parametrize("error", list(SurvivalError))
def test_structured_errors_are_shown_without_a_coefficient_table(error):
    failed = dataclasses.replace(_result(), error=error)
    view = SurvivalRegressionView(failed)

    assert _text(view)
    assert view.table() is None
    assert view.summary_label() is None
    assert view.findChild(FigureCanvasQTAgg) is None


def test_cox_table_charts_comments_layout_and_exact_plot_contents():
    result = _result()
    view = SurvivalRegressionView(result)
    view.resize(1000, 900)
    view.show()
    QCoreApplication.processEvents()
    try:
        splitter = view.findChild(QSplitter)
        assert splitter is not None
        assert splitter.orientation() is Qt.Orientation.Vertical
        assert splitter.count() == 3
        assert not splitter.childrenCollapsible()
        assert splitter.widget(0).findChild(QTableWidget) is view.table()
        assert view.summary_label() in splitter.widget(2).findChildren(QLabel)
        canvas = splitter.widget(1).findChild(FigureCanvasQTAgg)
        assert canvas is not None
        canvas.draw()
        forest, survival, risk_axis = canvas.figure.axes
        assert forest.get_xscale() == "log"
        assert [label.get_text() for label in forest.get_yticklabels()] == [
            survival_term_name(term) for term in result.terms
        ]
        np.testing.assert_allclose(forest.lines[0].get_xdata(), [term.hazard_ratio for term in result.terms])
        np.testing.assert_allclose(forest.lines[1].get_xdata(), [term.hazard_ratio_ci_low for term in result.terms])
        np.testing.assert_allclose(forest.lines[2].get_xdata(), [term.hazard_ratio_ci_high for term in result.terms])
        np.testing.assert_array_equal(forest.lines[-1].get_xdata(), [1.0, 1.0])
        data = result.plot_data
        assert data is not None
        np.testing.assert_array_equal(survival.lines[0].get_xdata(), data.times)
        np.testing.assert_array_equal(survival.lines[0].get_ydata(), data.survival)
        assert survival.lines[0].get_drawstyle() == "steps-post"
        censored = [index for index, count in enumerate(data.censored) if count > 0]
        np.testing.assert_array_equal(survival.lines[1].get_xdata(), [data.times[index] for index in censored])
        np.testing.assert_array_equal(survival.lines[1].get_ydata(), [data.survival[index] for index in censored])
        assert survival.lines[1].get_marker() == "+"
        assert survival.get_ylim()[0] == 0.0
        assert "unadjusted" in survival.get_title()
        assert risk_axis.get_title() == "At risk immediately before time"
        risk_table = risk_axis.tables[0]
        for column, (time, count) in enumerate(zip(data.risk_times, data.risk_counts, strict=True)):
            assert risk_table[0, column].get_text().get_text() == fmt_num(time, sig=3)
            assert risk_table[1, column].get_text().get_text() == fmt_int(count)
        text = _text(view)
        assert "without covariate adjustment" in text
        assert "not a Cox prediction" in text
        assert "no survival sampling or confidence bands" in text
    finally:
        view.close()


@pytest.mark.parametrize("value", [0.0, np.inf, np.nan])
def test_unplottable_forest_interval_is_explicit_and_survival_still_draws(value):
    result = _result()
    term = dataclasses.replace(result.terms[0], hazard_ratio_ci_low=value)
    view = SurvivalRegressionView(dataclasses.replace(result, terms=(term, *result.terms[1:])))
    canvas = view.findChild(FigureCanvasQTAgg)
    assert canvas is not None
    forest, survival, _ = canvas.figure.axes
    assert any("Forest plot unavailable" in text.get_text() for text in forest.texts)
    assert not forest.axison
    assert survival.lines
    assert view.table() is not None


def test_missing_survival_data_are_explicit_without_hiding_cox_effects():
    view = SurvivalRegressionView(dataclasses.replace(_result(), plot_data=None))
    canvas = view.findChild(FigureCanvasQTAgg)
    assert canvas is not None
    forest, survival, _ = canvas.figure.axes
    assert forest.lines
    assert any("No survival chart data" in text.get_text() for text in survival.texts)
    assert view.table() is not None


def test_extreme_finite_forest_intervals_and_zero_survival_render():
    result = _result()
    term = dataclasses.replace(
        result.terms[0],
        hazard_ratio=1.0,
        hazard_ratio_ci_low=1e-100,
        hazard_ratio_ci_high=1e100,
    )
    data = _survival_plot_data(np.array([1.0, 2.0, 3.0]), np.ones(3, dtype=int))
    view = SurvivalRegressionView(dataclasses.replace(result, terms=(term,), plot_data=data))
    view.resize(1000, 900)
    view.show()
    QCoreApplication.processEvents()
    try:
        canvas = view.findChild(FigureCanvasQTAgg)
        assert canvas is not None
        canvas.draw()
        forest, survival, _ = canvas.figure.axes
        assert forest.get_xlim() == (1e-100, 1e100)
        assert survival.lines[0].get_ydata()[-1] == 0.0
        assert len(survival.lines[1].get_xdata()) == 0
    finally:
        view.close()


def test_tied_event_and_censor_marks_draw_at_post_event_survival():
    data = _survival_plot_data(np.ones(4), np.array([1, 1, 0, 0]))
    view = SurvivalRegressionView(dataclasses.replace(_result(), plot_data=data))
    view.resize(1000, 900)
    view.show()
    QCoreApplication.processEvents()
    try:
        canvas = view.findChild(FigureCanvasQTAgg)
        assert canvas is not None
        canvas.draw()
        survival = canvas.figure.axes[1]
        np.testing.assert_array_equal(survival.lines[1].get_xdata(), [1.0])
        np.testing.assert_array_equal(survival.lines[1].get_ydata(), [0.5])
    finally:
        view.close()
