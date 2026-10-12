from __future__ import annotations

import pandas as pd
import pytest
from matplotlib.figure import Figure

from expo_jbm329.services.analysis.statistics import (
    StatisticsExportTable,
    analyze_descriptive_statistics,
    statistics_export_tables,
)
from expo_jbm329.services.analysis.statistics_charts import (
    StatisticsChartLabels,
    draw_boxplot,
    draw_histogram,
    render_statistics_charts,
)
from expo_jbm329.services.excel_chart import ExcelChartCancelledError


def test_statistics_export_tables_keep_numeric_values_and_explicit_recommendation() -> None:
    result = analyze_descriptive_statistics(
        pd.DataFrame({
            "Normal": [1.0, 2.0, 3.0, 4.0, 5.0],
            "Empty": pd.Series([None, None, None, None, None], dtype="float64"),
            "Group": ["A", "A", "B", None, "B"],
        })
    )

    tables = statistics_export_tables(result, (StatisticsExportTable.CONTINUOUS, StatisticsExportTable.CATEGORICAL))

    continuous = tables[StatisticsExportTable.CONTINUOUS.value]
    assert continuous["column"].tolist() == ["Normal", "Empty"]
    assert continuous.loc[0, "count"] == 5
    assert continuous.loc[0, "missing_fraction"] == 0.0
    assert continuous.loc[0, "mean"] == 3.0
    assert continuous.loc[0, "recommended_summary_method"] == "mean_sd"
    assert pd.isna(continuous.loc[1, "recommended_summary_method"])
    assert continuous.loc[0, "shapiro_p_value"] > 0.05
    assert "mean_sd_summary" in continuous
    assert "median_iqr_summary" in continuous
    assert pd.api.types.is_numeric_dtype(continuous["count"])
    assert pd.api.types.is_numeric_dtype(continuous["missing_fraction"])
    assert pd.api.types.is_numeric_dtype(continuous["shapiro_p_value"])

    categorical = tables[StatisticsExportTable.CATEGORICAL.value]
    group_frequencies = categorical.loc[categorical["column"] == "Group", ["column", "value", "count"]]
    assert group_frequencies.to_numpy().tolist() == [
        ["Group", "A", 2],
        ["Group", "B", 2],
    ]
    assert categorical.loc[categorical["column"] == "Group", "fraction"].tolist() == pytest.approx([0.5, 0.5])
    assert categorical.loc[categorical["column"] == "Group", "valid_count"].tolist() == [4, 4]
    assert categorical.loc[categorical["column"] == "Group", "missing_count"].tolist() == [1, 1]
    assert categorical.loc[categorical["column"] == "Group", "missing_fraction"].tolist() == pytest.approx([0.2, 0.2])


@pytest.mark.parametrize(
    "selection",
    [
        (),
        (StatisticsExportTable.CHARTS,),
        (StatisticsExportTable.CONTINUOUS, StatisticsExportTable.CONTINUOUS),
    ],
)
def test_statistics_table_builder_rejects_invalid_or_unavailable_tables(selection) -> None:
    result = analyze_descriptive_statistics(pd.DataFrame({"text": ["a", "b"]}))

    with pytest.raises(ValueError):
        statistics_export_tables(result, selection)


def test_statistics_chart_renderer_draws_every_numeric_column_and_reports_progress() -> None:
    result = analyze_descriptive_statistics(
        pd.DataFrame({
            "Original heading": [1.0, 2.0, 3.0, 4.0],
            "Constant": [5.0, 5.0, 5.0, 5.0],
            "All missing": pd.Series([None, None, None, None], dtype="float64"),
        })
    )
    progress: list[int] = []
    labels = StatisticsChartLabels("Histogram", "Boxplot", "No data")

    images = render_statistics_charts(result.columns, labels, progress_cb=progress.append)

    assert [image.heading for image in images] == ["Original heading", "Constant", "All missing"]
    assert all(image.image_data.startswith(b"\x89PNG\r\n\x1a\n") for image in images)
    assert all(image.width_px > 0 and image.height_px > 0 for image in images)
    assert progress == [34, 67, 100]


def test_statistics_chart_renderer_honors_cancellation_between_column_pairs() -> None:
    result = analyze_descriptive_statistics(pd.DataFrame({"first": [1, 2, 3], "second": [3, 4, 5]}))
    checks = 0

    def cancel() -> bool:
        nonlocal checks
        checks += 1
        return checks == 2

    with pytest.raises(ExcelChartCancelledError):
        render_statistics_charts(
            result.columns,
            StatisticsChartLabels("Histogram", "Boxplot", "No data"),
            cancel_cb=cancel,
        )


def test_empty_numeric_column_has_explicit_no_data_messages_in_both_axes() -> None:
    stats = analyze_descriptive_statistics(pd.DataFrame({"empty": pd.Series([None, None], dtype="float64")})).columns[0]
    figure = Figure()
    histogram, boxplot = figure.subplots(1, 2)
    labels = StatisticsChartLabels("Histogram", "Boxplot", "No data")

    draw_histogram(histogram, stats, labels)
    draw_boxplot(boxplot, stats, labels)

    assert [item.get_text() for item in histogram.texts] == ["No data"]
    assert [item.get_text() for item in boxplot.texts] == ["No data"]
