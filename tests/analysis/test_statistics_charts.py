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
    build_statistics_chart_presentation,
    build_statistics_chart_presentations,
    draw_boxplot,
    draw_histogram,
    draw_statistics_charts,
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
    presentations = build_statistics_chart_presentations(result.columns, lambda _context, text: text)

    images = render_statistics_charts(result.columns, presentations, progress_cb=progress.append)

    assert [image.heading for image in images] == ["", "", ""]
    assert [image.accessible_name for image in images] == ["Original heading", "Constant", "All missing"]
    assert [image.captions for image in images] == [(), (), ()]
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
            build_statistics_chart_presentations(result.columns, lambda _context, text: text),
            cancel_cb=cancel,
        )


def test_empty_numeric_column_has_explicit_no_data_messages_in_both_axes() -> None:
    stats = analyze_descriptive_statistics(pd.DataFrame({"empty": pd.Series([None, None], dtype="float64")})).columns[0]
    figure = Figure()
    histogram, boxplot = figure.subplots(1, 2)
    presentation = build_statistics_chart_presentation(stats, lambda _context, text: text)

    draw_histogram(histogram, stats, presentation)
    draw_boxplot(boxplot, stats, presentation)

    assert [item.get_text() for item in histogram.texts] == ["No data"]
    assert [item.get_text() for item in boxplot.texts] == ["No data"]


def test_statistics_chart_presentation_drives_shared_pair_titles_and_preserves_column_data() -> None:
    stats = analyze_descriptive_statistics(pd.DataFrame({"ordered column": [1.0, 2.0, 3.0, 4.0]})).columns[0]
    presentation = build_statistics_chart_presentation(
        stats,
        lambda context, text: f"{context}: {text}",
    )
    figure = Figure()

    draw_statistics_charts(figure, stats, presentation)

    assert [axis.get_title() for axis in figure.axes] == [
        "StatisticsView: Histogram",
        "StatisticsView: Boxplot",
    ]
    assert figure._suptitle.get_text() == "ordered column"
    assert [patch.get_height() for patch in figure.axes[0].patches] == list(stats.histogram_counts)
    assert presentation.metadata.worksheet_heading == ""
    assert presentation.metadata.accessible_name == "ordered column"
    assert presentation.metadata.captions == ()


def test_statistics_renderer_rejects_mismatched_column_presentation() -> None:
    columns = analyze_descriptive_statistics(pd.DataFrame({"first": [1.0], "second": [2.0]})).columns
    presentations = build_statistics_chart_presentations(columns, lambda _context, text: text)

    with pytest.raises(ValueError, match="exactly one chart presentation"):
        render_statistics_charts(columns, presentations[:1])

    mismatched = (presentations[1], presentations[0])
    with pytest.raises(ValueError, match="does not match its column"):
        render_statistics_charts(columns, mismatched)


def test_statistics_chart_for_empty_column_name_has_an_accessible_fallback() -> None:
    columns = analyze_descriptive_statistics(pd.DataFrame({"": [1.0, 2.0, 3.0]})).columns
    presentations = build_statistics_chart_presentations(columns, lambda _context, text: text)

    assert presentations[0].metadata.accessible_name == "Distribution"
