from __future__ import annotations

import pytest
from matplotlib.figure import Figure
from openpyxl import load_workbook

from expo_jbm329.services.analysis.pca_charts import draw_score_plot, draw_scree_plot, render_pca_charts
from expo_jbm329.services.analysis.pca_export import PCAExportComponent, pca_export_tables
from expo_jbm329.services.excel_chart import ExcelChartCancelledError
from expo_jbm329.services.file_writer import FileWriter
from tests.analysis.test_pca_export import CHART_LABELS, pca_snapshot

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def test_scree_plot_draws_component_bars_and_the_cumulative_line():
    result = pca_snapshot().result
    ax = Figure().add_subplot(111)

    draw_scree_plot(ax, result, CHART_LABELS)

    assert [bar.get_height() for bar in ax.patches] == pytest.approx([
        ratio * 100 for ratio in result.explained_variance_ratio
    ])
    (line,) = ax.get_lines()
    assert list(line.get_ydata()) == pytest.approx([ratio * 100 for ratio in result.cumulative_variance_ratio])
    assert ax.get_title() == "Scree plot"
    assert (ax.get_xlabel(), ax.get_ylabel()) == ("Component", "Explained variance (%)")
    assert [text.get_text() for text in ax.get_legend().get_texts()] == ["Cumulative", "Explained variance"]


def test_score_plot_draws_the_sampled_scores():
    result = pca_snapshot().result
    ax = Figure().add_subplot(111)

    draw_score_plot(ax, result, CHART_LABELS)

    (scores,) = ax.collections
    offsets = scores.get_offsets()
    assert offsets[:, 0].tolist() == pytest.approx(list(result.sample_pc1))
    assert offsets[:, 1].tolist() == pytest.approx(list(result.sample_pc2))
    assert ax.get_title() == "PC1 vs PC2"
    assert (ax.get_xlabel(), ax.get_ylabel()) == ("PC1 (80%)", "PC2 (15%)")


def test_render_returns_both_plots_with_captions_and_progress():
    progress: list[int] = []

    scree, scores = render_pca_charts(pca_snapshot(), progress_cb=progress.append, cancel_cb=lambda: False)

    assert (scree.heading, scores.heading) == ("Scree plot", "PC1 vs PC2")
    assert scree.captions == ()
    assert scores.captions == ("Sampled",)
    for image in (scree, scores):
        assert image.image_data.startswith(_PNG_SIGNATURE)
        assert (image.width_px, image.height_px) == (960, 600)
    assert progress == [50, 100]


@pytest.mark.parametrize("cancel_after", [0, 1, 2])
def test_render_honors_cancellation_before_each_image_and_at_the_end(cancel_after):
    calls = 0

    def cancel() -> bool:
        nonlocal calls
        calls += 1
        return calls > cancel_after

    with pytest.raises(ExcelChartCancelledError):
        render_pca_charts(pca_snapshot(), cancel_cb=cancel)


@pytest.mark.parametrize("streaming", [False, True])
def test_workbook_keeps_typed_tables_and_both_plots(tmp_path, streaming):
    snapshot = pca_snapshot()
    frames = pca_export_tables(
        snapshot,
        (PCAExportComponent.FEATURE_LOADINGS, PCAExportComponent.EXPLAINED_VARIANCE, PCAExportComponent.MODEL_SUMMARY),
    )
    sheets = {key.value: frame for key, frame in frames.items()}
    path = tmp_path / "pca.xlsx"

    FileWriter().save_excel_sheets(
        sheets,
        path,
        chart_images=render_pca_charts(snapshot),
        chart_sheet_name="Charts",
        streaming=streaming,
    )

    workbook = load_workbook(path)
    try:
        assert workbook.sheetnames == ["feature_loadings", "explained_variance", "model_summary", "Charts"]
        assert len(workbook["Charts"]._images) == 2
        assert workbook["Charts"]["A1"].value == "Scree plot"
        loadings = workbook["feature_loadings"]
        assert [cell.value for cell in loadings[1]] == ["feature", "PC1", "PC2", "PC3"]
        assert loadings["A2"].value == "x"
        assert isinstance(loadings["B2"].value, float)
        variance = workbook["explained_variance"]
        assert [cell.value for cell in variance[1]] == ["component", "variance", "share", "cumulative_share"]
        assert variance["A2"].value == "PC1"
        assert isinstance(variance["C2"].value, float)
        summary = workbook["model_summary"]
        assert summary["A2"].value == "features"
        assert summary["B2"].value == pytest.approx(3.0)
    finally:
        workbook.close()
