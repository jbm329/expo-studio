from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd
import pytest
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from PyQt6.QtCore import QCoreApplication, Qt
from PyQt6.QtWidgets import QLabel, QScrollArea, QSplitter, QTableWidget

from expo_jbm329.gui.dialogs.analysis.regression_view import LARGE_SAMPLE_SIZE, RegressionView
from expo_jbm329.services.analysis.regression import (
    PLOT_SAMPLE_SIZE,
    RegressionError,
    RegressionResult,
    RegressionWarning,
    RegressionWarningReason,
    analyze_regression,
)


def _frame(size: int = 60, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({
        "x": rng.normal(size=size),
        "g": rng.choice(["a", "b", "c"], size=size, p=[0.2, 0.5, 0.3]),
    })
    df["<y>"] = 2 * df["x"] + (df["g"] == "c") * 3 + rng.normal(size=size)
    return df


def _fitted(df: pd.DataFrame | None = None) -> RegressionResult:
    result = analyze_regression(_frame() if df is None else df, "<y>", ["x", "g"])
    assert result.error is None
    return result


def _labels(view: RegressionView) -> list[str]:
    return [label.text() for label in view.findChildren(QLabel)]


def _cells(view: RegressionView, row: int) -> list[str]:
    table = view.table()
    assert table is not None
    cells = []
    for col in range(table.columnCount()):
        item = table.item(row, col)
        assert item is not None
        cells.append(item.text())
    return cells


def _summary(view: RegressionView) -> str:
    label = view.summary_label()
    assert label is not None
    return label.text()


def test_linear_chart_header_gap_stays_fixed_when_section_grows():
    view = RegressionView(_fitted())
    panel = view.findChild(QSplitter).widget(1)
    panel.setParent(None)
    panel.resize(1100, 500)
    panel.show()
    try:
        QCoreApplication.processEvents()
        layout = panel.layout()
        heading = layout.itemAt(0).widget()
        charts = layout.itemAt(1).widget()
        gap = charts.y() - heading.geometry().bottom()
        heading_height = heading.height()
        panel.resize(1100, 800)
        QCoreApplication.processEvents()
        assert heading.height() == heading_height
        assert charts.y() - heading.geometry().bottom() == gap
        assert layout.stretch(1) == 1
    finally:
        panel.close()
        panel.deleteLater()
        view.close()


# ----------------------------------------------------------------------
# Errors
# ----------------------------------------------------------------------


@pytest.mark.parametrize("error", list(RegressionError))
def test_every_error_shows_its_message_only(error):
    result = dataclasses.replace(analyze_regression(_frame()), error=error, error_column="x")
    view = RegressionView(result)

    text = view.error_text(result)
    assert text
    assert _labels(view) == [text]
    assert view.table() is None
    assert view.summary_label() is None


def test_error_messages_name_the_relevant_column_or_count():
    base = analyze_regression(_frame(), "<y>")
    view = RegressionView(base)

    constant = dataclasses.replace(base, error=RegressionError.CONSTANT_PREDICTOR, error_column="flat_column")
    assert "flat_column" in view.error_text(constant)
    target = dataclasses.replace(base, error=RegressionError.CONSTANT_TARGET)
    assert "<y>" in view.error_text(target)
    too_few = dataclasses.replace(base, error=RegressionError.NOT_ENOUGH_OBSERVATIONS, n_used=3)
    assert "3" in view.error_text(too_few)


def test_no_predictors_prompts_the_user():
    view = RegressionView(analyze_regression(_frame()))

    assert _labels(view) == [view.tr("Select one or more predictors and click Apply.")]


def test_error_text_is_empty_without_an_error():
    result = _fitted()

    assert RegressionView(result).error_text(result) == ""


# ----------------------------------------------------------------------
# Coefficients
# ----------------------------------------------------------------------


def test_coefficient_table_lists_every_term():
    result = _fitted()
    view = RegressionView(result)
    table = view.table()

    assert view.result() is result
    assert table is not None
    assert table.selectionMode() is QTableWidget.SelectionMode.NoSelection
    assert table.rowCount() == len(result.terms) == 4
    names = [_cells(view, row)[0] for row in range(table.rowCount())]
    assert names == [view.tr("(Intercept)"), "x", "g = a", "g = c"]


def test_coefficient_row_formats_values_marks_significance_and_blanks_intercept_vif():
    view = RegressionView(_fitted())

    intercept = _cells(view, 0)
    x_row = _cells(view, 1)

    assert intercept[-1] == ""
    assert x_row[-1] != ""
    assert x_row[4].endswith(" *")  # x is strongly significant
    assert " to " in x_row[5]


def test_undefined_interval_is_shown_as_not_available():
    result = _fitted()
    term = dataclasses.replace(result.terms[1], ci_low=float("nan"), p_value=float("nan"))
    view = RegressionView(dataclasses.replace(result, terms=(result.terms[0], term)))

    assert _cells(view, 1)[5] == view.tr("N/A")
    assert not _cells(view, 1)[4].endswith("*")


def test_caption_names_escaped_reference_levels():
    df = _frame()
    df["g"] = df["g"].replace({"b": "<b>"})
    view = RegressionView(_fitted(df))

    caption = next(text for text in _labels(view) if "reference level" in text)
    assert "&lt;b&gt;" in caption
    assert "(3 levels)" in caption


def test_caption_omits_references_without_categorical_predictors():
    view = RegressionView(analyze_regression(_frame(), "<y>", ["x"]))

    assert not any("reference level" in text for text in _labels(view))


# ----------------------------------------------------------------------
# Summary and diagnostics
# ----------------------------------------------------------------------


def test_summary_describes_the_model_with_an_escaped_target():
    result = _fitted()
    text = _summary(RegressionView(result))

    assert "&lt;y&gt;" in text
    assert "<y>" not in text
    assert f"F({result.df_model}, {result.df_residual})" in text
    assert "Breusch-Pagan" in text
    assert "Jarque-Bera" in text
    assert "Durbin-Watson" in text
    assert "Largest VIF" in text


def test_summary_escapes_p_values_below_the_reporting_threshold():
    text = _summary(RegressionView(_fitted()))

    assert "p &lt; " in text  # the overall F test
    assert "p <" not in text


def test_summary_lists_warnings():
    result = dataclasses.replace(
        _fitted(),
        warnings=tuple(RegressionWarning(reason, ("x",)) for reason in RegressionWarningReason),
    )
    view = RegressionView(result)
    text = _summary(view)

    assert text.count("⚠") == len(RegressionWarningReason)
    assert text.count('style="color: #cc6600;"') == len(RegressionWarningReason)
    for warning in result.warnings:
        assert view.warning_text(warning) in text


def test_multicollinearity_warning_names_the_terms():
    view = RegressionView(_fitted())
    warning = RegressionWarning(RegressionWarningReason.HIGH_MULTICOLLINEARITY, ("x", "g = a"))

    assert "x, g = a" in view.warning_text(warning)


def test_diagnostic_verdicts_reflect_the_statistics():
    result = _fitted()
    assert result.diagnostics is not None
    view = RegressionView(result)

    good = _summary(view)
    assert view.tr("no evidence of non-constant residual variance") in good
    assert view.tr("residuals consistent with a normal distribution") in good
    assert view.tr("no problematic multicollinearity") in good

    bad_diagnostics = dataclasses.replace(
        result.diagnostics, breusch_pagan_p_value=0.001, jarque_bera_p_value=0.001, max_vif=50.0
    )
    bad = _summary(RegressionView(dataclasses.replace(result, diagnostics=bad_diagnostics)))
    assert view.tr("non-constant residual variance") in bad
    assert view.tr("residuals not normally distributed") in bad
    assert view.tr("high multicollinearity") in bad
    assert "Q-Q plot" not in bad  # small sample: no large-n caveat


def test_large_sample_non_normality_gets_a_caveat():
    result = _fitted()
    assert result.diagnostics is not None
    diagnostics = dataclasses.replace(result.diagnostics, jarque_bera_p_value=0.001)
    large = dataclasses.replace(result, diagnostics=diagnostics, n_used=LARGE_SAMPLE_SIZE + 1)

    assert "Q-Q plot" in _summary(RegressionView(large))


@pytest.mark.parametrize(
    ("statistic", "expected"),
    [(1.0, "positive autocorrelation"), (2.0, "no evidence of autocorrelation"), (3.0, "negative autocorrelation")],
)
def test_durbin_watson_verdict(statistic, expected):
    view = RegressionView(_fitted())

    assert view._durbin_watson_verdict(statistic) == view.tr(expected)  # noqa: SLF001


# ----------------------------------------------------------------------
# Plots
# ----------------------------------------------------------------------


def test_three_diagnostic_plots_are_drawn():
    view = RegressionView(_fitted())
    canvases = view.findChildren(FigureCanvasQTAgg)

    assert len(canvases) == 3
    titles = {canvas.figure.axes[0].get_title() for canvas in canvases}
    assert titles == {
        view.tr("Residuals vs fitted"),
        view.tr("Actual vs predicted"),
        view.tr("Normal Q-Q plot of residuals"),
    }
    assert not any("random sample" in text for text in _labels(view))


def test_layout_places_coefficients_above_plots_and_summary_below():
    view = RegressionView(_fitted())

    vertical_splitters = [
        splitter for splitter in view.findChildren(QSplitter) if splitter.orientation() is Qt.Orientation.Vertical
    ]
    horizontal_splitters = [
        splitter for splitter in view.findChildren(QSplitter) if splitter.orientation() is Qt.Orientation.Horizontal
    ]
    assert len(vertical_splitters) == 1
    assert len(horizontal_splitters) == 1
    assert all(not splitter.childrenCollapsible() for splitter in vertical_splitters + horizontal_splitters)

    sections = vertical_splitters[0]
    table = view.table()
    assert table is not None
    assert sections.widget(0).isAncestorOf(table)
    assert "Coefficients" in " ".join(_labels(view))
    assert len(sections.widget(1).findChildren(FigureCanvasQTAgg)) == 3
    assert any(label.text() == "Diagnostic plots" for label in sections.widget(1).findChildren(QLabel))

    summary = view.summary_label()
    assert summary is not None
    assert isinstance(sections.widget(2), QScrollArea)
    assert sections.widget(2).isAncestorOf(summary)


def test_sampled_plots_explain_the_sampling():
    df = _frame(size=PLOT_SAMPLE_SIZE + 100)
    view = RegressionView(analyze_regression(df, "<y>", ["x"]))

    assert any("random sample" in text for text in _labels(view))


def test_missing_plot_data_draws_no_plots():
    view = RegressionView(dataclasses.replace(_fitted(), plot=None))

    assert view.findChildren(FigureCanvasQTAgg) == []
