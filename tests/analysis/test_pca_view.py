from __future__ import annotations

import dataclasses

import pandas as pd
import pytest
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from PyQt6.QtWidgets import QLabel, QSplitter

from expo_jbm329.gui.dialogs.analysis.pca_view import PCAView
from expo_jbm329.services.analysis.pca import PCAError, PCAResult, analyze_pca


def _result(*, standardize: bool = True) -> PCAResult:
    df = pd.DataFrame({
        "a": [1.0, 2.0, 3.0, 4.0],
        "b": [2.0, 3.0, 5.0, 7.0],
        "c": [4.0, 1.0, 6.0, 2.0],
    })
    result = analyze_pca(df, standardize=standardize)
    assert result.error is None
    return result


def _labels_text(view: PCAView) -> str:
    return "\n".join(label.text() for label in view.findChildren(QLabel))


def _axes(view: PCAView):
    return [canvas.figure.axes[0] for canvas in view.findChildren(FigureCanvasQTAgg)]


@pytest.mark.parametrize("error", list(PCAError))
def test_every_error_has_a_message(error):
    view = PCAView(_result())

    assert view.error_text(error)


def test_error_shows_only_message_without_plots_or_table():
    result = dataclasses.replace(_result(), error=PCAError.NO_VARIATION)
    view = PCAView(result)

    assert view.loadings_table() is None
    assert view.findChildren(QSplitter) == []
    assert view.error_text(PCAError.NO_VARIATION) in _labels_text(view)


def test_success_shows_scree_scatter_and_feature_loadings():
    result = _result()
    view = PCAView(result)
    table = view.loadings_table()

    assert len(_axes(view)) == 2
    assert table is not None
    assert table.rowCount() == 3
    assert table.columnCount() == 4
    assert [table.item(row, 0).text() for row in range(table.rowCount())] == list(result.columns)
    assert view.configuration() == (result.columns, True)


def test_scree_plot_shows_component_and_cumulative_variance():
    view = PCAView(_result())
    scree = next(ax for ax in _axes(view) if ax.get_title() == "Scree plot")

    assert scree.get_title() == "Scree plot"
    assert len(scree.patches) == 3
    assert len(scree.lines) == 1
    assert scree.get_ylim()[1] == 105


def test_scatter_plot_is_labeled_with_pc1_and_pc2_variance():
    view = PCAView(_result())
    scatter = next(ax for ax in _axes(view) if ax.get_title() == "PC1 vs PC2")

    assert scatter.get_title() == "PC1 vs PC2"
    assert scatter.get_xlabel().startswith("PC1 (")
    assert scatter.get_ylabel().startswith("PC2 (")
    assert len(scatter.collections) == 1
    assert len(scatter.lines) == 2


def test_summary_reports_complete_case_deletion_and_standardization():
    result = dataclasses.replace(_result(), total_rows=10, rows_used=7, rows_dropped=3)
    view = PCAView(result)

    text = _labels_text(view)
    assert "standardized" in text
    assert "7 of 10 rows" in text
    assert "3 dropped" in text


def test_summary_reports_unstandardized_fit_and_sampling():
    result = dataclasses.replace(_result(standardize=False), sampled=True, sample_pc1=(1.0, 2.0), sample_pc2=(3.0, 4.0))
    view = PCAView(result)

    text = _labels_text(view)
    assert "not standardized" in text
    assert "sample of 2 rows" in text


def test_loadings_are_formatted_and_right_aligned():
    view = PCAView(_result())
    table = view.loadings_table()
    assert table is not None

    item = table.item(0, 1)
    assert item.text() != ""
    assert item.textAlignment() != 0


def test_no_component_values_are_not_needed_to_display_error():
    result = PCAResult(
        columns=("a", "b"),
        available_columns=("a", "b"),
        standardize=True,
        total_rows=0,
        rows_used=0,
        rows_dropped=0,
        explained_variance=(),
        explained_variance_ratio=(),
        cumulative_variance_ratio=(),
        loadings=(),
        sample_pc1=(),
        sample_pc2=(),
        sampled=False,
        error=PCAError.NOT_ENOUGH_OBSERVATIONS,
    )

    view = PCAView(result)

    assert "At least 2 complete rows" in _labels_text(view)
