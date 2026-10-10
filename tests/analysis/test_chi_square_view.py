from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd
import pytest
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from PyQt6.QtCore import QCoreApplication, Qt
from PyQt6.QtWidgets import QApplication, QLabel, QSplitter, QTableWidget

from expo_jbm329.gui.dialogs.analysis.chi_square_view import (
    MAX_ANNOTATED_CELLS,
    RESIDUAL_SIGNIFICANCE_THRESHOLD,
    ChiSquareView,
)
from expo_jbm329.services.analysis.chi_square import ChiSquareError, ChiSquareResult, analyze_chi_square


@pytest.fixture(autouse=True)
def _flush_deferred_paints():
    # Lets matplotlib canvases process deferred paint events before the
    # widgets are garbage collected.
    yield
    QApplication.processEvents()


def _table_df(counts: dict[tuple[str, str], int]) -> pd.DataFrame:
    rows = [(row, column) for (row, column), count in counts.items() for _ in range(count)]
    return pd.DataFrame(rows, columns=["row", "col"])


def _two_by_three_result() -> ChiSquareResult:
    return analyze_chi_square(
        _table_df({
            ("x", "a"): 10,
            ("x", "b"): 20,
            ("x", "c"): 30,
            ("y", "a"): 25,
            ("y", "b"): 15,
            ("y", "c"): 5,
        })
    )


@pytest.mark.parametrize("factory", [_two_by_three_result, lambda: _two_by_two_small_result()])
def test_chi_square_test_results_header_gap_stays_fixed_when_section_grows(factory):
    view = ChiSquareView(factory())
    panel = view.findChild(QSplitter).widget(2)
    panel.setParent(None)
    panel.resize(1100, 500)
    panel.show()
    try:
        QCoreApplication.processEvents()
        layout = panel.layout()
        labels = [layout.itemAt(index).widget() for index in range(layout.count() - 1)]
        geometry = [(label.y(), label.height()) for label in labels]
        panel.resize(1100, 800)
        QCoreApplication.processEvents()
        assert [(label.y(), label.height()) for label in labels] == geometry
    finally:
        panel.close()
        panel.deleteLater()
        view.close()


def _two_by_two_small_result() -> ChiSquareResult:
    return analyze_chi_square(_table_df({("x", "p"): 8, ("x", "q"): 2, ("y", "p"): 1, ("y", "q"): 5}))


def _labels(view: ChiSquareView) -> list[QLabel]:
    return view.findChildren(QLabel)


def _label_texts(view: ChiSquareView) -> str:
    return "\n".join(label.text() for label in _labels(view))


@pytest.mark.parametrize("error", list(ChiSquareError))
def test_error_result_shows_only_a_message(error: ChiSquareError):
    result = analyze_chi_square(pd.DataFrame({"a": [1]}))
    view = ChiSquareView(ChiSquareResult(**{**_result_fields(result), "error": error}))

    labels = _labels(view)
    assert len(labels) == 1
    assert labels[0].text() != ""
    assert view.findChildren(QTableWidget) == []
    assert view.findChildren(FigureCanvasQTAgg) == []


def _result_fields(result: ChiSquareResult) -> dict[str, object]:
    return {field: getattr(result, field) for field in result.__dataclass_fields__}


def test_observed_table_includes_row_and_column_totals():
    view = ChiSquareView(_two_by_three_result())

    table = view.findChild(QTableWidget)
    assert table is not None
    assert table.selectionMode() is QTableWidget.SelectionMode.NoSelection
    headers = [table.horizontalHeaderItem(i).text() for i in range(table.columnCount())]
    assert headers == ["row", "a", "b", "c", "Total"]
    assert table.rowCount() == 3

    cells = [[table.item(r, c).text() for c in range(table.columnCount())] for r in range(table.rowCount())]
    assert cells[0] == ["x", "10", "20", "30", "60"]
    assert cells[1] == ["y", "25", "15", "5", "45"]
    assert cells[2][0] == "Total"
    assert cells[2][-1] == "105"


def test_layout_has_titled_table_heatmap_and_results_with_adjustable_dividers():
    view = ChiSquareView(_two_by_three_result())

    splitters = view.findChildren(QSplitter)
    assert len(splitters) == 1
    splitter = splitters[0]
    assert splitter.orientation() is Qt.Orientation.Vertical
    assert splitter.childrenCollapsible() is False
    assert splitter.count() == 3

    table = view.findChild(QTableWidget)
    assert table is not None
    assert splitter.widget(0).isAncestorOf(table)
    assert any(label.text() == "Observed counts" for label in splitter.widget(0).findChildren(QLabel))
    assert len(splitter.widget(1).findChildren(FigureCanvasQTAgg)) == 1
    assert any(label.text() == "Adjusted residuals" for label in splitter.widget(1).findChildren(QLabel))
    assert any(label.text() == "Test results" for label in splitter.widget(2).findChildren(QLabel))
    assert any("Pearson" in label.text() for label in splitter.widget(2).findChildren(QLabel))


def test_caption_names_both_columns_as_plain_text():
    view = ChiSquareView(_two_by_three_result())

    caption = next(label for label in _labels(view) if "Observed counts:" in label.text())
    assert "row" in caption.text()
    assert "col" in caption.text()
    assert caption.textFormat() == Qt.TextFormat.PlainText


def test_heatmap_canvas_is_shown_for_a_valid_result():
    view = ChiSquareView(_two_by_three_result())

    assert len(view.findChildren(FigureCanvasQTAgg)) == 1


def test_results_text_reports_chi_square_and_cramers_v_without_fisher_for_larger_tables():
    view = ChiSquareView(_two_by_three_result())

    text = view.test_results_text(_two_by_three_result())
    assert "Pearson's chi-square test" in text
    assert "Yates" not in text
    assert "df = 2" in text
    assert "Cramér's V" in text
    assert "Fisher" not in text
    assert "appear to be associated" in text


def test_results_text_mentions_yates_and_fisher_for_two_by_two_tables():
    result = _two_by_two_small_result()
    view = ChiSquareView(result)

    text = view.test_results_text(result)
    assert "Yates" in text
    assert "Fisher's exact test" in text
    assert "useful when expected counts are small" in text
    assert "Odds ratio" in text


def test_results_text_escapes_small_p_values_for_rich_text():
    result = dataclasses.replace(_two_by_two_small_result(), p_value=1e-10, fisher_p_value=1e-10)
    view = ChiSquareView(result)

    text = view.test_results_text(result)
    assert text.count("p = &lt; ") == 2
    assert "p = < " not in text


def test_results_text_reports_no_association_for_independent_data():
    result = analyze_chi_square(
        _table_df({("x", "p"): 25, ("x", "q"): 25, ("y", "p"): 25, ("y", "q"): 25}),
    )
    view = ChiSquareView(result)

    assert "no significant association" in view.test_results_text(result)


def test_cochran_warning_is_shown_and_recommends_fisher_for_small_two_by_two_tables():
    result = _two_by_two_small_result()
    assert result.cochran_violated

    view = ChiSquareView(result)

    assert "Prefer Fisher's exact test" in _label_texts(view)
    assert "75%" in view.cochran_warning_text(result)


def test_cochran_warning_recommends_merging_categories_for_larger_tables():
    result = analyze_chi_square(
        _table_df({
            ("x", "a"): 2,
            ("x", "b"): 1,
            ("x", "c"): 3,
            ("y", "a"): 1,
            ("y", "b"): 4,
            ("y", "c"): 1,
        })
    )
    assert result.cochran_violated
    assert result.fisher_p_value is None

    view = ChiSquareView(result)

    assert "Consider merging sparse categories" in view.cochran_warning_text(result)


def test_no_cochran_warning_when_the_rule_holds():
    result = _two_by_three_result()
    assert not result.cochran_violated

    view = ChiSquareView(result)

    assert "⚠" not in _label_texts(view)


def test_heatmap_color_limit_is_never_below_the_significance_threshold():
    assert ChiSquareView.heatmap_color_limit(np.array([[0.5, -0.2]])) == RESIDUAL_SIGNIFICANCE_THRESHOLD


def test_heatmap_color_limit_uses_the_largest_absolute_finite_residual():
    residuals = np.array([[1.0, -4.5], [float("nan"), 3.0]])

    assert ChiSquareView.heatmap_color_limit(residuals) == pytest.approx(4.5)


def test_heatmap_color_limit_falls_back_to_the_threshold_when_nothing_is_finite():
    residuals = np.array([[float("nan")]])

    assert ChiSquareView.heatmap_color_limit(residuals) == RESIDUAL_SIGNIFICANCE_THRESHOLD


def test_large_tables_render_without_cell_annotations():
    # 11 x 11 = 121 cells > MAX_ANNOTATED_CELLS.
    size = 11
    assert size * size > MAX_ANNOTATED_CELLS
    counts = {(f"r{i}", f"c{j}"): 1 + (i + j) % 3 for i in range(size) for j in range(size)}
    result = analyze_chi_square(_table_df(counts))

    view = ChiSquareView(result)

    canvas = view.findChild(FigureCanvasQTAgg)
    assert canvas is not None
    assert len(canvas.figure.axes[0].texts) == 0


def test_small_tables_annotate_every_finite_cell():
    view = ChiSquareView(_two_by_three_result())

    canvas = view.findChild(FigureCanvasQTAgg)
    assert canvas is not None
    assert len(canvas.figure.axes[0].texts) == 6
