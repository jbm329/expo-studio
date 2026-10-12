from __future__ import annotations

import dataclasses
import math

import pytest
from matplotlib.figure import Figure
from openpyxl import load_workbook

from expo_jbm329.services.analysis.outliers_charts import (
    draw_outlier_histogram,
    draw_outlier_projection,
    render_multivariate_outlier_charts,
    render_univariate_outlier_charts,
)
from expo_jbm329.services.analysis.outliers_export import OutlierExportComponent, outlier_export_tables
from expo_jbm329.services.excel_chart import ExcelChartCancelledError
from expo_jbm329.services.file_writer import FileWriter
from tests.analysis.test_outliers_export import (
    HISTOGRAM_LABELS,
    PROJECTION_LABELS,
    multivariate_snapshot,
    univariate_detail,
    univariate_snapshot,
)

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _axes():
    return Figure().add_subplot(111)


# ----------------------------------------------------------------------
# Drawing
# ----------------------------------------------------------------------


def test_histogram_stacks_flagged_bars_and_marks_both_fences():
    detail = univariate_detail()
    ax = _axes()

    draw_outlier_histogram(ax, detail, HISTOGRAM_LABELS)

    bins = len(detail.histogram_edges) - 1
    assert len(ax.patches) == 2 * bins
    assert [patch.get_height() for patch in ax.patches[bins:]] == list(detail.outlier_counts)
    assert [patch.get_y() for patch in ax.patches[bins:]] == list(detail.inlier_counts)
    fences = [line.get_xdata()[0] for line in ax.get_lines()]
    assert fences == pytest.approx([detail.summary.lower_fence, detail.summary.upper_fence])
    assert ax.get_title() == "a"
    assert ax.get_ylabel() == "Count"
    assert [text.get_text() for text in ax.get_legend().get_texts()] == ["Inside", "Flagged"]


def test_histogram_of_a_column_without_values_shows_only_its_title():
    detail = univariate_detail("few")
    empty = dataclasses.replace(detail, histogram_edges=())
    ax = _axes()

    draw_outlier_histogram(ax, empty, HISTOGRAM_LABELS)

    assert ax.get_title() == "few"
    assert len(ax.patches) == 0
    assert ax.get_legend() is None


def test_histogram_skips_undefined_fences():
    detail = univariate_detail("few")
    ax = _axes()

    draw_outlier_histogram(ax, detail, HISTOGRAM_LABELS)

    assert math.isnan(detail.summary.lower_fence)
    assert len(ax.get_lines()) == 0


def test_projection_colors_flagged_rows_and_states_it_is_a_visualization():
    snapshot = multivariate_snapshot()
    result = snapshot.result
    ax = _axes()

    draw_outlier_projection(ax, result, PROJECTION_LABELS)

    inliers, outliers = ax.collections
    assert len(outliers.get_offsets()) == sum(result.sample_outliers)
    assert len(inliers.get_offsets()) == len(result.sample_outliers) - sum(result.sample_outliers)
    assert ax.get_title() == "PCA projection (visualization only)"
    assert (ax.get_xlabel(), ax.get_ylabel()) == ("PC1", "PC2")
    assert [text.get_text() for text in ax.get_legend().get_texts()] == ["Inliers", "Potential outliers"]


# ----------------------------------------------------------------------
# Univariate rendering
# ----------------------------------------------------------------------


def test_univariate_render_returns_one_histogram_per_screened_column_with_progress():
    snapshot = univariate_snapshot()
    progress: list[int] = []

    images = render_univariate_outlier_charts(snapshot, progress_cb=progress.append, cancel_cb=lambda: False)

    assert [image.heading for image in images] == list(snapshot.chart_columns)
    assert all(image.image_data.startswith(_PNG_SIGNATURE) for image in images)
    assert {(image.width_px, image.height_px) for image in images} == {(960, 450)}
    assert progress == [34, 67, 100]


@pytest.mark.parametrize("cancel_after", [0, 1, 3])
def test_univariate_render_honors_cancellation_before_each_column_and_at_the_end(cancel_after):
    calls = 0

    def cancel() -> bool:
        nonlocal calls
        calls += 1
        return calls > cancel_after

    with pytest.raises(ExcelChartCancelledError):
        render_univariate_outlier_charts(univariate_snapshot(), cancel_cb=cancel)


def test_univariate_render_requires_a_screened_column(monkeypatch):
    snapshot = univariate_snapshot()
    monkeypatch.setattr(type(snapshot), "chart_columns", property(lambda _self: ()))

    with pytest.raises(ValueError, match="no screened column"):
        render_univariate_outlier_charts(snapshot)


def test_univariate_render_rejects_data_that_can_no_longer_be_screened():
    snapshot = univariate_snapshot()
    snapshot.data["a"] = "text"

    with pytest.raises(ValueError, match="could not be screened"):
        render_univariate_outlier_charts(snapshot)


# ----------------------------------------------------------------------
# Multivariate rendering
# ----------------------------------------------------------------------


def test_multivariate_render_returns_the_projection_with_its_caption():
    progress: list[int] = []

    (image,) = render_multivariate_outlier_charts(
        multivariate_snapshot(), progress_cb=progress.append, cancel_cb=lambda: False
    )

    assert image.heading == "PCA projection"
    assert image.captions == ("Sampled",)
    assert image.image_data.startswith(_PNG_SIGNATURE)
    assert (image.width_px, image.height_px) == (960, 720)
    assert progress == [100]


@pytest.mark.parametrize("cancel_after", [0, 1])
def test_multivariate_render_honors_cancellation_before_and_after_drawing(cancel_after):
    calls = 0

    def cancel() -> bool:
        nonlocal calls
        calls += 1
        return calls > cancel_after

    with pytest.raises(ExcelChartCancelledError):
        render_multivariate_outlier_charts(multivariate_snapshot(), cancel_cb=cancel)


# ----------------------------------------------------------------------
# Workbooks
# ----------------------------------------------------------------------


@pytest.mark.parametrize("streaming", [False, True])
def test_univariate_workbook_keeps_typed_tables_and_one_chart_per_column(tmp_path, streaming):
    snapshot = univariate_snapshot()
    frames = outlier_export_tables(
        snapshot,
        (
            OutlierExportComponent.COLUMN_SUMMARY,
            OutlierExportComponent.COLUMN_DETAILS,
            OutlierExportComponent.POTENTIAL_OUTLIERS,
        ),
    )
    sheets = {key.value: frame for key, frame in frames.items()}
    images = render_univariate_outlier_charts(snapshot)
    path = tmp_path / "outliers.xlsx"

    FileWriter().save_excel_sheets(sheets, path, chart_images=images, chart_sheet_name="Charts", streaming=streaming)

    workbook = load_workbook(path)
    try:
        assert workbook.sheetnames == [*sheets, "Charts"]
        assert len(workbook["Charts"]._images) == len(snapshot.chart_columns)
        assert workbook["Charts"]["A1"].value == "a"
        summary = workbook["column_summary"]
        assert [cell.value for cell in summary[1]] == list(frames[OutlierExportComponent.COLUMN_SUMMARY].columns)
        assert summary["A2"].value == "a"
        assert isinstance(summary["E2"].value, float)
        details = workbook["column_details"]
        assert details["A2"].value == "threshold"
        assert details["B2"].value == pytest.approx(1.5)
        rows = workbook["potential_outliers"]
        assert [cell.value for cell in rows[1]][:3] == ["Row (2)", "a", "Score"]
        assert rows["A2"].value == 10
    finally:
        workbook.close()


def test_multivariate_workbook_keeps_model_summary_and_projection(tmp_path):
    snapshot = multivariate_snapshot()
    frames = outlier_export_tables(snapshot, (OutlierExportComponent.MODEL_SUMMARY,))
    sheets = {key.value: frame for key, frame in frames.items()}
    path = tmp_path / "multivariate.xlsx"

    FileWriter().save_excel_sheets(
        sheets,
        path,
        chart_images=render_multivariate_outlier_charts(snapshot),
        chart_sheet_name="Charts",
        streaming=False,
    )

    workbook = load_workbook(path)
    try:
        assert workbook.sheetnames == ["model_summary", "Charts"]
        assert len(workbook["Charts"]._images) == 1
        assert workbook["Charts"]["A1"].value == "PCA projection"
        assert workbook["model_summary"]["A2"].value == "features"
    finally:
        workbook.close()
