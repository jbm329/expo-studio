from __future__ import annotations

import dataclasses

import pandas as pd
import pytest
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QSplitter, QTableWidget

from expo_jbm329.gui.dialogs.analysis.clustering_view import ClusteringView
from expo_jbm329.services.analysis.clustering import (
    ClusteringError,
    ClusteringMethod,
    ClusterSize,
    analyze_clustering,
)
from tests.analysis.section_assertions import assert_section_scrolls_below_frozen_title


def _result(method: ClusteringMethod = ClusteringMethod.K_MEANS):
    df = pd.DataFrame({
        "x": [0.0, 0.1, -0.1, 10.0, 10.1, 9.9],
        "y": [0.0, -0.1, 0.1, 10.0, 10.1, 9.9],
    })
    result = analyze_clustering(df, method=method, cluster_count=2, dbscan_epsilon=0.5, dbscan_min_samples=2)
    assert result.error is None
    return result


def _labels_text(view: ClusteringView) -> str:
    return "\n".join(label.text() for label in view.findChildren(QLabel))


def _section_title(panel) -> str:
    title = panel.layout().itemAt(0).widget()
    assert isinstance(title, QLabel)
    assert title.textFormat() is Qt.TextFormat.PlainText
    assert title.font().bold()
    return title.text()


@pytest.mark.parametrize("method", list(ClusteringMethod))
@pytest.mark.parametrize(("section", "small_height", "width"), [(1, 120, 1100), (2, 60, 400)])
def test_projection_and_comments_scroll_below_a_frozen_title(method, section, small_height, width):
    view = ClusteringView(dataclasses.replace(_result(method), sampled=True))
    panel = view.findChild(QSplitter).widget(section)

    content = assert_section_scrolls_below_frozen_title(panel, small_height, width=width)

    if section == 1:
        assert isinstance(content, FigureCanvasQTAgg)
    else:
        assert isinstance(content, QLabel)
        assert content.textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByMouse
        assert view.method_name(method) in content.text()
    panel.deleteLater()
    view.close()


@pytest.mark.parametrize("error", list(ClusteringError))
def test_every_error_has_a_message(error):
    view = ClusteringView(_result())

    assert view.error_text(error)


def test_error_shows_only_a_message_without_plot_or_table():
    view = ClusteringView(dataclasses.replace(_result(), error=ClusteringError.NO_VARIATION))

    assert view.cluster_table() is None
    assert view.findChildren(FigureCanvasQTAgg) == []
    assert view.error_text(ClusteringError.NO_VARIATION) in _labels_text(view)


@pytest.mark.parametrize(
    ("method", "name"),
    [
        (ClusteringMethod.K_MEANS, "K-Means"),
        (ClusteringMethod.DBSCAN, "DBSCAN"),
        (ClusteringMethod.AGGLOMERATIVE, "Agglomerative"),
    ],
)
def test_method_names(method, name):
    view = ClusteringView(_result())

    assert view.method_name(method) == name


def test_success_shows_projection_and_cluster_table():
    result = _result()
    view = ClusteringView(result)
    table = view.cluster_table()

    assert len(view.findChildren(FigureCanvasQTAgg)) == 1
    assert table is not None
    assert table.selectionMode() is QTableWidget.SelectionMode.NoSelection
    assert table.rowCount() == len(result.clusters)
    assert table.item(0, 0).text() == "Cluster 1"
    assert view.configuration() == (result.columns, result.method, True, 2, 0.5, 2)


def test_layout_has_table_plot_and_comments_like_regression():
    view = ClusteringView(_result())

    splitters = view.findChildren(QSplitter)
    assert len(splitters) == 1
    splitter = splitters[0]
    assert splitter.orientation() is Qt.Orientation.Vertical
    assert splitter.childrenCollapsible() is False
    assert splitter.count() == 3
    assert [_section_title(splitter.widget(index)) for index in range(3)] == [
        "Cluster sizes",
        "Cluster projection",
        "Model summary",
    ]
    table_layout = splitter.widget(0).layout()
    assert table_layout.itemAt(1).widget() is view.cluster_table()
    assert table_layout.stretch(1) == 1
    assert len(splitter.widget(1).findChildren(FigureCanvasQTAgg)) == 1


def test_projection_has_one_collection_per_cluster_and_axes():
    view = ClusteringView(_result())
    canvas = view.findChildren(FigureCanvasQTAgg)[0]
    axis = canvas.figure.axes[0]

    assert axis.get_title() == "Cluster projection (internal PCA)"
    assert axis.get_xlabel() == "PC1"
    assert axis.get_ylabel() == "PC2"
    assert len(axis.collections) == 2
    assert len(axis.lines) == 2


def test_dbscan_noise_is_listed_and_colored_separately():
    result = dataclasses.replace(
        _result(),
        method=ClusteringMethod.DBSCAN,
        clusters=(ClusterSize(label=0, count=4),),
        noise_count=2,
        sample_labels=(0, 0, 0, 0, -1, -1),
    )
    view = ClusteringView(result)
    table = view.cluster_table()
    assert table is not None

    assert table.rowCount() == 2
    assert table.item(1, 0).text() == "Noise"
    assert table.item(1, 1).text() == "2"
    axis = view.findChildren(FigureCanvasQTAgg)[0].figure.axes[0]
    assert len(axis.collections) == 2


def test_summary_reports_rows_scaling_and_silhouette():
    result = dataclasses.replace(_result(), total_rows=10, rows_used=8, rows_dropped=2, silhouette_score=0.678)
    view = ClusteringView(result)

    text = _labels_text(view)
    assert "standardized" in text
    assert "8 of 10 rows" in text
    assert "2 dropped" in text
    assert "Silhouette score:" in text


def test_summary_explains_unavailable_silhouette_and_sampling():
    result = dataclasses.replace(_result(), standardize=False, silhouette_score=None, sampled=True)
    view = ClusteringView(result)

    text = _labels_text(view)
    assert "not standardized" in text
    assert "not available" in text
    assert "deterministic sample" in text


def test_result_returns_the_displayed_fit():
    result = _result()

    assert ClusteringView(result).result() is result


@pytest.mark.parametrize("sampled", [False, True])
def test_chart_labels_match_the_view_and_caption_only_a_sampled_plot(sampled):
    result = dataclasses.replace(_result(), sampled=sampled)
    view = ClusteringView(result)

    labels = view.chart_labels()

    assert labels.heading == "Cluster projection"
    assert labels.title == "Cluster projection (internal PCA)"
    assert (labels.pc1_axis, labels.pc2_axis) == ("PC1", "PC2")
    assert labels.cluster_name(0) == "Cluster 1"
    assert labels.cluster_name(-1) == "Noise"
    expected = (f"The plot shows a deterministic sample of {len(result.sample_labels)} rows.",) if sampled else ()
    assert labels.captions == expected


def test_error_chart_labels_have_no_caption():
    result = dataclasses.replace(analyze_clustering(pd.DataFrame({"x": [1.0]})), sampled=True)

    assert ClusteringView(result).chart_labels().captions == ()


def test_export_notes_are_the_plain_text_comments_and_features():
    result = dataclasses.replace(_result(), sampled=True)
    view = ClusteringView(result)

    notes = view.export_notes()

    assert notes[0].startswith("K-Means on 2 features (standardized).")
    assert all("<" not in line for line in notes)
    assert any(line.startswith("Silhouette score: ") for line in notes)
    assert f"The plot shows a deterministic sample of {len(result.sample_labels)} rows." in notes
    assert notes[-1] == "Features: x, y"


def test_error_view_has_no_export_notes():
    result = analyze_clustering(pd.DataFrame({"x": [1.0]}))

    assert ClusteringView(result).export_notes() == ()
