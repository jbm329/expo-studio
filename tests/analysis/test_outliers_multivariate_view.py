from __future__ import annotations

import dataclasses

import pandas as pd
import pytest
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QSplitter, QTableWidget

from expo_jbm329.gui.dialogs.analysis.outliers_multivariate_view import MultivariateOutliersView
from expo_jbm329.services.analysis.multivariate_outliers import (
    MultivariateOutlierError,
    MultivariateOutlierMethod,
    analyze_multivariate_outliers,
)
from expo_jbm329.services.analysis.outliers_charts import OutlierProjectionLabels
from tests.analysis.section_assertions import assert_section_scrolls_below_frozen_title


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
    splitter = view.findChildren(QSplitter)[0]
    assert _section_title(splitter.widget(0)) == "Potential outliers"
    assert "No potential outliers" in _labels_text(view)


def _section_title(panel) -> str:
    layout = panel.layout()
    title = layout.itemAt(0).widget()
    assert isinstance(title, QLabel)
    assert title.textFormat() is Qt.TextFormat.PlainText
    assert title.font().bold()
    return title.text()


def test_layout_has_three_resizable_titled_sections_like_regression():
    view = MultivariateOutliersView(_result())
    splitter = view.findChildren(QSplitter)[0]

    assert splitter.orientation() is Qt.Orientation.Vertical
    assert splitter.count() == 3
    assert [_section_title(splitter.widget(index)) for index in range(3)] == [
        "Potential outliers, most anomalous first",
        "Outlier projection",
        "Model comments",
    ]
    table_layout = splitter.widget(0).layout()
    assert table_layout.itemAt(1).widget() is view.extremes_table()
    assert table_layout.stretch(1) == 1


@pytest.mark.parametrize(("section", "small_height", "width"), [(1, 120, 1100), (2, 80, 400)])
def test_projection_and_comments_scroll_below_a_frozen_title(section, small_height, width):
    view = MultivariateOutliersView(dataclasses.replace(_result(), sampled=True))
    panel = view.findChildren(QSplitter)[0].widget(section)

    content = assert_section_scrolls_below_frozen_title(panel, small_height, width=width)

    if section == 1:
        assert isinstance(content, FigureCanvasQTAgg)
    else:
        assert isinstance(content, QLabel)
        assert content.textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByMouse
        assert "Isolation Forest" in content.text()
    panel.deleteLater()
    view.close()


def test_summary_reports_standardization_and_sampling():
    result = dataclasses.replace(_result(), standardize=False, sampled=True)
    view = MultivariateOutliersView(result)

    text = _labels_text(view)
    assert "not standardized" in text
    assert "deterministic sample" in text


def test_method_name_translates_every_method():
    view = MultivariateOutliersView(_result())

    assert view.method_name(MultivariateOutlierMethod.LOCAL_OUTLIER_FACTOR) == "Local Outlier Factor"


# ----------------------------------------------------------------------
# Export text
# ----------------------------------------------------------------------


def test_chart_labels_are_shared_by_the_displayed_projection():
    result = _result()
    view = MultivariateOutliersView(result)
    axes = view.findChildren(FigureCanvasQTAgg)[0].figure.axes[0]

    labels = view.chart_labels()

    assert view.result() is result
    assert labels == OutlierProjectionLabels(
        heading="Outlier projection",
        title="PCA projection (visualization only)",
        pc1_axis="PC1",
        pc2_axis="PC2",
        inliers="Inliers",
        outliers="Potential outliers",
    )
    assert axes.get_title() == labels.title
    assert [text.get_text() for text in axes.get_legend().get_texts()] == ["Inliers", "Potential outliers"]


def test_sampled_projection_has_a_plain_caption():
    view = MultivariateOutliersView(dataclasses.replace(_result(), sampled=True))

    assert view.chart_labels().captions == ("The projection shows a deterministic sample of 7 rows.",)


def test_export_notes_are_the_plain_model_comments_and_features():
    result = _result()
    notes = MultivariateOutliersView(result).export_notes()

    assert notes[0].startswith("Isolation Forest on 2 features (standardized):")
    assert "<b>" not in notes[0]
    assert notes[1] == "Scores rank observations within this fit. Potential outliers are not necessarily errors."
    assert notes[-1] == "Features: x, y"


def test_export_text_of_an_error_view_has_no_notes_or_caption():
    view = MultivariateOutliersView(
        dataclasses.replace(_result(), error=MultivariateOutlierError.NO_VARIATION, sampled=True)
    )

    assert view.export_notes() == ()
    assert view.chart_labels().captions == ()
