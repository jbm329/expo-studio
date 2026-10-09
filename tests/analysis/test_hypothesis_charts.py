from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest
from matplotlib.figure import Figure
from openpyxl import load_workbook

from expo_jbm329.services.analysis.hypothesis_charts import (
    HypothesisChartLabels,
    draw_group_distribution,
    draw_paired_charts,
    draw_residual_heatmap,
    heatmap_color_limit,
    render_hypothesis_charts,
)
from expo_jbm329.services.analysis.hypothesis_export import HypothesisExportComponent, hypothesis_export_tables
from expo_jbm329.services.excel_chart import ExcelChartCancelledError
from expo_jbm329.services.file_writer import FileWriter
from tests.analysis.test_hypothesis_export import chi_snapshot, group_snapshot, paired_snapshot

LABELS = HypothesisChartLabels("Distribution", "Adjusted residuals", "Trajectories", "Value", "Occasion")


@pytest.mark.parametrize("factory", [group_snapshot, chi_snapshot, paired_snapshot])
def test_render_exact_displayed_images_is_deterministic_and_reports_progress(factory):
    snapshot = factory()
    progress = []
    images = render_hypothesis_charts(snapshot, LABELS, progress_cb=progress.append)
    assert len(images) == 1
    assert images[0].heading == " / ".join(snapshot.columns)
    assert images[0].image_data.startswith(b"\x89PNG")
    assert (images[0].width_px, images[0].height_px) == (1080, 420)
    assert progress == [100]
    assert images == render_hypothesis_charts(snapshot, LABELS)


@pytest.mark.parametrize("cancel_at", [1, 2])
def test_renderer_cancellation_never_reports_completed_progress(cancel_at):
    calls = 0
    progress = []

    def cancel():
        nonlocal calls
        calls += 1
        return calls == cancel_at

    with pytest.raises(ExcelChartCancelledError):
        render_hypothesis_charts(group_snapshot(), LABELS, cancel_cb=cancel, progress_cb=progress.append)
    assert progress == []


def test_group_boxes_use_full_summary_min_max_and_literal_labels():
    snapshot = group_snapshot()
    figure = Figure()
    ax = figure.add_subplot(111)
    draw_group_distribution(ax, snapshot.result.groups, LABELS.distribution)
    assert [label.get_text() for label in ax.get_xticklabels()] == [group.label for group in snapshot.result.groups]
    assert ax.lines[1].get_ydata()[1] == snapshot.result.groups[0].minimum
    assert ax.lines[2].get_ydata()[1] == snapshot.result.groups[0].maximum


def test_residual_heatmap_orientation_color_scale_and_undefined_cells():
    snapshot = chi_snapshot(3)
    figure = Figure()
    ax = figure.add_subplot(111)
    draw_residual_heatmap(figure, ax, snapshot.result, LABELS.residuals)
    np.testing.assert_allclose(ax.images[0].get_array(), snapshot.result.adjusted_residuals)
    assert ax.get_xlabel() == snapshot.columns[1]
    assert ax.get_ylabel() == snapshot.columns[0]
    assert [label.get_text() for label in ax.get_xticklabels()] == list(snapshot.result.column_labels)
    assert len(ax.texts) == 6
    assert heatmap_color_limit(np.array([[np.nan]])) == 1.96
    assert heatmap_color_limit(np.array([[-4.0, 2.0]])) == 4
    malformed = replace(snapshot.result, adjusted_residuals=((float("nan"), 2, 3), (4, 5, 6)))
    figure = Figure()
    ax = figure.add_subplot(111)
    draw_residual_heatmap(figure, ax, malformed, LABELS.residuals)
    assert len(ax.texts) == 5
    figure = Figure()
    ax = figure.add_subplot(111)
    annotations = tuple(tuple("translated" for _ in row) for row in malformed.adjusted_residuals)
    draw_residual_heatmap(figure, ax, malformed, LABELS.residuals, annotations)
    assert all(text.get_text() == "translated" for text in ax.texts)


def test_large_heatmap_omits_annotations():
    result = chi_snapshot().result
    result = replace(
        result,
        adjusted_residuals=tuple(tuple(0.1 for _ in range(11)) for _ in range(10)),
        row_labels=tuple(map(str, range(10))),
        column_labels=tuple(map(str, range(11))),
    )
    figure = Figure()
    ax = figure.add_subplot(111)
    draw_residual_heatmap(figure, ax, result, LABELS.residuals)
    assert not ax.texts


def test_paired_charts_preserve_selected_order_full_boxes_and_deterministic_sample():
    snapshot = paired_snapshot(3, 250)
    result = snapshot.result
    assert result.plot_data.sampled
    figure = Figure()
    draw_paired_charts(figure, result, LABELS)
    boxes, trajectories = figure.axes
    assert [label.get_text() for label in boxes.get_xticklabels()] == list(snapshot.columns)
    assert [label.get_text() for label in trajectories.get_xticklabels()] == list(snapshot.columns)
    assert len(trajectories.lines) == 200
    assert list(trajectories.lines[0].get_ydata()) == list(result.plot_data.trajectories[0])
    assert boxes.lines[1].get_ydata()[1] == result.summaries[0].minimum
    assert boxes.lines[2].get_ydata()[1] == result.summaries[0].maximum
    figure = Figure()
    draw_paired_charts(figure, replace(result, plot_data=None), LABELS)
    assert not figure.axes[1].lines


@pytest.mark.parametrize("factory", [group_snapshot, chi_snapshot, paired_snapshot])
@pytest.mark.parametrize("charts_only", [False, True])
@pytest.mark.parametrize("streaming", [False, True])
def test_real_workbooks_preserve_typed_tables_and_one_chart_sheet(tmp_path, factory, charts_only, streaming):
    snapshot = factory()
    frames = (
        hypothesis_export_tables(
            snapshot,
            (HypothesisExportComponent.SUMMARY, HypothesisExportComponent.TEST_RESULTS),
        )
        if not charts_only
        else {}
    )
    sheets = {key.value: frame for key, frame in frames.items()}
    images = render_hypothesis_charts(snapshot, LABELS)
    path = tmp_path / "hypothesis.xlsx"
    FileWriter().save_excel_sheets(sheets, path, chart_images=images, chart_sheet_name="Charts", streaming=streaming)
    workbook = load_workbook(path)
    try:
        assert workbook.sheetnames == [*sheets, "Charts"]
        assert len(workbook["Charts"]._images) == 1
        assert workbook["Charts"]["A1"].value == " / ".join(snapshot.columns)
        for name, frame in sheets.items():
            worksheet = workbook[name]
            assert [cell.value for cell in worksheet[1]] == list(frame.columns)
            assert worksheet.max_row == len(frame) + 1
        if not charts_only:
            assert isinstance(workbook["Test results"]["B2"].value, (float, int))
    finally:
        workbook.close()
