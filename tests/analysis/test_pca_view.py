from __future__ import annotations

import dataclasses

import pandas as pd
import pytest
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QSplitter, QTableWidget

from expo_jbm329.gui.dialogs.analysis.pca_view import PCAView
from expo_jbm329.services.analysis.pca import PCAError, PCAResult, analyze_pca
from expo_jbm329.utils.format_utils import fmt_pct
from tests.analysis.section_assertions import assert_section_scrolls_below_frozen_title


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


def _sections(view: PCAView) -> QSplitter:
    return next(
        splitter for splitter in view.findChildren(QSplitter) if splitter.orientation() is Qt.Orientation.Vertical
    )


def _section_title(panel) -> str:
    title = panel.layout().itemAt(0).widget()
    assert isinstance(title, QLabel)
    assert title.textFormat() is Qt.TextFormat.PlainText
    assert title.font().bold()
    return title.text()


@pytest.mark.parametrize(("section", "small_height", "width"), [(1, 120, 1100), (2, 50, 300)])
def test_plots_and_comments_scroll_below_a_frozen_title(section, small_height, width):
    view = PCAView(dataclasses.replace(_result(), sampled=True))
    panel = _sections(view).widget(section)

    content = assert_section_scrolls_below_frozen_title(panel, small_height, width=width, result_section=section == 2)

    if section == 1:
        assert isinstance(content, QSplitter)
        assert content.orientation() is Qt.Orientation.Horizontal
        assert len(content.findChildren(FigureCanvasQTAgg)) == 2
    else:
        assert isinstance(content, QLabel)
        assert content.textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByMouse
        assert "features" in content.text()
    panel.deleteLater()
    view.close()


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
    assert table.selectionMode() is QTableWidget.SelectionMode.NoSelection
    assert table.rowCount() == 3
    assert table.columnCount() == 4
    assert [table.item(row, 0).text() for row in range(table.rowCount())] == list(result.columns)
    assert view.configuration() == (result.columns, True)


def test_layout_has_loadings_plots_and_comments_like_regression():
    view = PCAView(_result())

    splitters = view.findChildren(QSplitter)
    vertical = [splitter for splitter in splitters if splitter.orientation() is Qt.Orientation.Vertical]
    horizontal = [splitter for splitter in splitters if splitter.orientation() is Qt.Orientation.Horizontal]
    assert len(vertical) == 1
    assert len(horizontal) == 1
    assert all(not splitter.childrenCollapsible() for splitter in splitters)

    sections = vertical[0]
    assert sections.count() == 3
    assert [_section_title(sections.widget(index)) for index in range(3)] == [
        "Feature loadings",
        "PCA plots",
        "Model summary",
    ]
    table_layout = sections.widget(0).layout()
    assert table_layout.itemAt(1).widget() is view.loadings_table()
    assert table_layout.stretch(1) == 1
    assert len(sections.widget(1).findChildren(FigureCanvasQTAgg)) == 2


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


def test_result_returns_the_displayed_fit():
    result = _result()

    assert PCAView(result).result() is result


@pytest.mark.parametrize("sampled", [False, True])
def test_chart_labels_match_the_view_and_caption_only_a_sampled_plot(sampled):
    result = dataclasses.replace(_result(), sampled=sampled)
    view = PCAView(result)

    labels = view.chart_labels()

    assert labels.scree_metadata.accessible_name == "Scree plot"
    assert (labels.explained, labels.cumulative) == ("Explained variance", "Cumulative")
    assert (labels.component_axis, labels.variance_axis) == ("Component", "Explained variance (%)")
    assert labels.scatter_metadata.accessible_name == "PC1 vs PC2"
    pc1, pc2 = result.explained_variance_ratio[:2]
    assert labels.pc1_axis == f"PC1 ({fmt_pct(pc1)})"
    assert labels.pc2_axis == f"PC2 ({fmt_pct(pc2)})"
    expected = (
        (f"The PC1-vs-PC2 plot shows a deterministic sample of {len(result.sample_pc1)} rows.",) if sampled else ()
    )
    assert labels.scatter_metadata.captions == expected


def test_displayed_plots_use_the_shared_chart_labels():
    view = PCAView(_result())
    labels = view.chart_labels()

    axes = {ax.get_title(): ax for ax in _axes(view)}

    assert set(axes) == {labels.scree_metadata.accessible_name, labels.scatter_metadata.accessible_name}
    scores = axes[labels.scatter_metadata.accessible_name]
    assert (scores.get_xlabel(), scores.get_ylabel()) == (labels.pc1_axis, labels.pc2_axis)


def test_error_chart_labels_have_no_caption_or_variance():
    result = dataclasses.replace(analyze_pca(pd.DataFrame({"x": [1.0]})), sampled=True)

    labels = PCAView(result).chart_labels()

    assert labels.scatter_metadata.captions == ()
    assert (labels.pc1_axis, labels.pc2_axis) == ("PC1", "PC2")


def test_export_notes_are_the_plain_text_comments_and_features():
    result = dataclasses.replace(_result(), sampled=True)

    notes = PCAView(result).export_notes()

    assert notes[0].startswith("3 features, standardized.")
    assert all("<" not in line for line in notes)
    assert f"The PC1-vs-PC2 plot shows a deterministic sample of {len(result.sample_pc1)} rows." in notes
    assert notes[-2:] == ("Features: a, b, c", "Standardization: Standardized")


def test_error_view_has_no_export_notes():
    assert PCAView(analyze_pca(pd.DataFrame({"x": [1.0]}))).export_notes() == ()
