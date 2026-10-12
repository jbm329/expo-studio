from __future__ import annotations

import numpy as np
import pytest
from matplotlib.figure import Figure
from openpyxl import load_workbook

from expo_jbm329.services.analysis.clustering import ClusteringMethod
from expo_jbm329.services.analysis.clustering_charts import draw_cluster_projection, render_clustering_charts
from expo_jbm329.services.analysis.clustering_export import ClusteringExportComponent, clustering_export_tables
from expo_jbm329.services.excel_chart import ExcelChartCancelledError
from expo_jbm329.services.file_writer import FileWriter
from tests.analysis.test_clustering_export import PROJECTION_LABELS, clustering_snapshot

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def test_projection_draws_one_series_per_cluster_with_gray_noise_last():
    snapshot = clustering_snapshot(ClusteringMethod.DBSCAN, dbscan_min_samples=3)
    result = snapshot.result
    ax = Figure().add_subplot(111)

    draw_cluster_projection(ax, result, PROJECTION_LABELS)

    noise, *clusters = ax.collections
    labels = np.asarray(result.sample_labels)
    assert len(noise.get_offsets()) == int((labels == -1).sum())
    assert [len(series.get_offsets()) for series in clusters] == [4, 4]
    assert tuple(noise.get_facecolor()[0][:3]) == pytest.approx((0.5, 0.5, 0.5))
    assert ax.get_title() == "Cluster projection (internal PCA)"
    assert (ax.get_xlabel(), ax.get_ylabel()) == ("PC1", "PC2")
    assert [text.get_text() for text in ax.get_legend().get_texts()] == ["Noise", "Cluster 1", "Cluster 2"]


def test_render_returns_the_projection_with_its_caption_and_progress():
    progress: list[int] = []

    (image,) = render_clustering_charts(clustering_snapshot(), progress_cb=progress.append, cancel_cb=lambda: False)

    assert image.heading == "Cluster projection"
    assert image.captions == ("Sampled",)
    assert image.image_data.startswith(_PNG_SIGNATURE)
    assert (image.width_px, image.height_px) == (960, 720)
    assert progress == [100]


@pytest.mark.parametrize("cancel_after", [0, 1])
def test_render_honors_cancellation_before_and_after_drawing(cancel_after):
    calls = 0

    def cancel() -> bool:
        nonlocal calls
        calls += 1
        return calls > cancel_after

    with pytest.raises(ExcelChartCancelledError):
        render_clustering_charts(clustering_snapshot(), cancel_cb=cancel)


@pytest.mark.parametrize("streaming", [False, True])
def test_workbook_keeps_typed_tables_and_the_projection(tmp_path, streaming):
    snapshot = clustering_snapshot()
    frames = clustering_export_tables(
        snapshot, (ClusteringExportComponent.CLUSTER_SIZES, ClusteringExportComponent.MODEL_SUMMARY)
    )
    sheets = {key.value: frame for key, frame in frames.items()}
    path = tmp_path / "clustering.xlsx"

    FileWriter().save_excel_sheets(
        sheets,
        path,
        chart_images=render_clustering_charts(snapshot),
        chart_sheet_name="Charts",
        streaming=streaming,
    )

    workbook = load_workbook(path)
    try:
        assert workbook.sheetnames == ["cluster_sizes", "model_summary", "Charts"]
        assert len(workbook["Charts"]._images) == 1
        assert workbook["Charts"]["A1"].value == "Cluster projection"
        sizes = workbook["cluster_sizes"]
        assert [cell.value for cell in sizes[1]] == ["cluster", "rows", "share"]
        assert sizes["A2"].value == "Cluster 1"
        assert isinstance(sizes["B2"].value, int)
        assert isinstance(sizes["C2"].value, float)
        summary = workbook["model_summary"]
        assert summary["A2"].value == "features"
        assert summary["B2"].value == pytest.approx(2.0)
    finally:
        workbook.close()
