from __future__ import annotations

import dataclasses

import pandas as pd
import pytest
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from PyQt6.QtWidgets import QLabel, QSplitter, QTableWidget

from expo_jbm329.gui.dialogs.analysis.outliers_multivariate_view import MultivariateOutliersView
from expo_jbm329.services.analysis.multivariate_outliers import (
    MultivariateOutlierError,
    MultivariateOutlierMethod,
    analyze_multivariate_outliers,
)


def _result():
    df = pd.DataFrame({"x": [0.0, 0.1, -0.1, 10.0, 10.1, 9.9, 30.0], "y": [0.0, 0.1, -0.1, 10.0, 9.9, 10.1, 30.0]})
    result = analyze_multivariate_outliers(df, contamination=0.2)
    assert result.error is None
    return result


def _labels_text(view: MultivariateOutliersView) -> str:
    return "\n".join(label.text() for label in view.findChildren(QLabel))


@pytest.mark.parametrize("error", list(MultivariateOutlierError))
def test_every_error_has_a_message(error):
    assert MultivariateOutliersView(_result()).error_text(error)


def test_error_has_no_plot_or_observation_table():
    view = MultivariateOutliersView(dataclasses.replace(_result(), error=MultivariateOutlierError.NO_VARIATION))

    assert view.extremes_table() is None
    assert view.findChildren(FigureCanvasQTAgg) == []
    assert "no variation" in _labels_text(view)


def test_result_shows_projection_and_ranked_observation_table():
    result = _result()
    view = MultivariateOutliersView(result)
    table = view.extremes_table()

    assert len(view.findChildren(FigureCanvasQTAgg)) == 1
    assert table is not None
    assert table.selectionMode() is QTableWidget.SelectionMode.NoSelection
    assert table.rowCount() == len(result.extremes)
    assert [table.horizontalHeaderItem(index).text() for index in range(table.columnCount())] == [
        "Row",
        "Anomaly score",
        "x",
        "y",
    ]
    assert view.configuration() == (result.columns, result.method, True, 0.2, 20)
    splitters = view.findChildren(QSplitter)
    assert len(splitters) == 1
    assert splitters[0].childrenCollapsible() is False


def test_projection_has_inlier_and_outlier_series():
    view = MultivariateOutliersView(_result())
    axis = view.findChildren(FigureCanvasQTAgg)[0].figure.axes[0]

    assert axis.get_title() == "PCA projection (visualization only)"
    assert len(axis.collections) == 2
    assert len(axis.lines) == 2


def test_no_flagged_rows_has_a_clear_message():
    result = dataclasses.replace(_result(), outlier_count=0, extremes=())
    view = MultivariateOutliersView(result)

    assert view.extremes_table() is None
    assert "<b>No potential outliers</b>" in _labels_text(view)


def test_summary_reports_standardization_and_sampling():
    result = dataclasses.replace(_result(), standardize=False, sampled=True)
    view = MultivariateOutliersView(result)

    text = _labels_text(view)
    assert "not standardized" in text
    assert "deterministic sample" in text


def test_method_name_translates_every_method():
    view = MultivariateOutliersView(_result())

    assert view.method_name(MultivariateOutlierMethod.LOCAL_OUTLIER_FACTOR) == "Local Outlier Factor"
