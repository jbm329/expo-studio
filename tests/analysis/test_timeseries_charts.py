from __future__ import annotations

import pandas as pd
import pytest
from matplotlib.figure import Figure
from openpyxl import load_workbook

from expo_jbm329.services.analysis.timeseries_charts import (
    draw_acf_plot,
    draw_decomposition,
    draw_series_plot,
    render_time_series_charts,
)
from expo_jbm329.services.analysis.timeseries_export import (
    TimeSeriesExportComponent,
    series_table,
    time_series_export_tables,
)
from expo_jbm329.services.excel_chart import ExcelChartCancelledError
from expo_jbm329.services.file_writer import FileWriter
from tests.analysis.test_timeseries_export import CHART_LABELS, irregular_snapshot, time_series_snapshot

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def test_series_plot_draws_the_prepared_values():
    result = time_series_snapshot().result
    ax = Figure().add_subplot(111)

    draw_series_plot(ax, result, CHART_LABELS)

    (line,) = ax.get_lines()
    assert list(line.get_ydata()) == pytest.approx(list(result.values))
    assert ax.get_title() == "Series"
    assert ax.get_ylabel() == "sales"


def test_acf_plot_draws_one_stem_per_lag():
    result = time_series_snapshot().result
    ax = Figure().add_subplot(111)

    draw_acf_plot(ax, result, CHART_LABELS)

    stems, points = ax.collections
    assert len(stems.get_segments()) == len(result.acf_values)
    assert points.get_offsets()[:, 1].tolist() == pytest.approx(list(result.acf_values))
    assert ax.get_title() == "Autocorrelation"
    assert (ax.get_xlabel(), ax.get_ylabel()) == ("Lag", "Autocorrelation")


def test_decomposition_draws_four_labeled_panels():
    result = time_series_snapshot().result
    axes = list(Figure().subplots(4, 1, sharex=True))

    draw_decomposition(axes, result, CHART_LABELS)

    assert [ax.get_ylabel() for ax in axes] == ["Observed", "Trend", "Seasonal", "Residual"]
    assert axes[0].get_title() == "Seasonal decomposition"
    assert list(axes[2].get_lines()[0].get_ydata()) == pytest.approx(list(result.seasonal))


def test_decomposition_requires_four_axes():
    with pytest.raises(ValueError, match="four axes"):
        draw_decomposition([Figure().add_subplot(111)], time_series_snapshot().result, CHART_LABELS)


def test_render_returns_every_available_plot_with_progress():
    progress: list[int] = []

    images = render_time_series_charts(time_series_snapshot(), progress_cb=progress.append, cancel_cb=lambda: False)

    assert [image.heading for image in images] == ["Series", "Autocorrelation", "Seasonal decomposition"]
    assert [(image.width_px, image.height_px) for image in images] == [(960, 480), (960, 480), (960, 960)]
    assert all(image.image_data.startswith(_PNG_SIGNATURE) and image.captions == () for image in images)
    assert progress == [33, 66, 100]


def test_render_skips_unavailable_plots():
    progress: list[int] = []

    (image,) = render_time_series_charts(irregular_snapshot(), progress_cb=progress.append)

    assert image.heading == "Series"
    assert progress == [100]


@pytest.mark.parametrize("cancel_after", [0, 1, 3])
def test_render_honors_cancellation_before_each_image_and_at_the_end(cancel_after):
    calls = 0

    def cancel() -> bool:
        nonlocal calls
        calls += 1
        return calls > cancel_after

    with pytest.raises(ExcelChartCancelledError):
        render_time_series_charts(time_series_snapshot(), cancel_cb=cancel)


@pytest.mark.parametrize("streaming", [False, True])
def test_workbook_keeps_typed_tables_and_every_plot(tmp_path, streaming):
    snapshot = time_series_snapshot()
    frames = time_series_export_tables(
        snapshot,
        (
            TimeSeriesExportComponent.SERIES,
            TimeSeriesExportComponent.AUTOCORRELATION,
            TimeSeriesExportComponent.MODEL_SUMMARY,
        ),
    )
    sheets = {key.value: frame for key, frame in frames.items()}
    path = tmp_path / "time_series.xlsx"

    FileWriter().save_excel_sheets(
        sheets,
        path,
        chart_images=render_time_series_charts(snapshot),
        chart_sheet_name="Charts",
        streaming=streaming,
    )

    workbook = load_workbook(path)
    try:
        assert workbook.sheetnames == ["series", "autocorrelation", "model_summary", "Charts"]
        assert len(workbook["Charts"]._images) == 3
        assert workbook["Charts"]["A1"].value == "Series"
        series = workbook["series"]
        assert [cell.value for cell in series[1]] == ["timestamp", "value", "trend", "seasonal", "residual"]
        assert series["A2"].is_date
        assert series["B2"].value == pytest.approx(10.0)
        acf = workbook["autocorrelation"]
        assert [cell.value for cell in acf[1]] == ["lag", "autocorrelation"]
        assert acf["A2"].value == 1
        summary = workbook["model_summary"]
        assert summary["A2"].value == "source_rows"
        assert summary["B2"].value == pytest.approx(23.0)
    finally:
        workbook.close()


@pytest.mark.parametrize("streaming", [False, True])
def test_workbook_accepts_timezone_aware_series(tmp_path, streaming):
    frame = pd.DataFrame({
        "day": pd.date_range("2024-01-01", periods=4, freq="D", tz="Europe/Stockholm"),
        "sales": [1.0, 2.0, 4.0, 3.0],
    })
    snapshot = time_series_snapshot(frame)
    path = tmp_path / "time_series_tz.xlsx"

    FileWriter().save_excel_sheets({"series": series_table(snapshot)}, path, streaming=streaming)

    workbook = load_workbook(path)
    try:
        assert workbook["series"]["A2"].is_date
        assert workbook["series"]["A2"].value.isoformat().startswith("2024-01-01")
    finally:
        workbook.close()
