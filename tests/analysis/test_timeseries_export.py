from __future__ import annotations

import dataclasses
import math

import pandas as pd
import pytest

from expo_jbm329.services.analysis.chart_presentation import ChartPresentationMetadata
from expo_jbm329.services.analysis.statistics import StatisticsExportFormat
from expo_jbm329.services.analysis.timeseries import TimeSeriesResult, analyze_time_series
from expo_jbm329.services.analysis.timeseries_charts import TimeSeriesChartLabels
from expo_jbm329.services.analysis.timeseries_export import (
    TIME_SERIES_COMPONENTS,
    TimeSeriesExportComponent,
    TimeSeriesExportRequest,
    TimeSeriesExportSnapshot,
    TimeSeriesMetric,
    autocorrelation_table,
    series_table,
    time_series_export_tables,
    time_series_model_summary_table,
)

CHART_LABELS = TimeSeriesChartLabels(
    series_metadata=ChartPresentationMetadata(worksheet_heading="", accessible_name="Series"),
    value_axis="sales",
    acf_metadata=ChartPresentationMetadata(worksheet_heading="", accessible_name="Autocorrelation"),
    lag_axis="Lag",
    acf_axis="Autocorrelation",
    decomposition_metadata=ChartPresentationMetadata(worksheet_heading="", accessible_name="Seasonal decomposition"),
    observed="Observed",
    trend="Trend",
    seasonal="Seasonal",
    residual="Residual",
)
NOTES = ("sales by day: 21 time points.", "Decomposition model: Additive")
IRREGULAR_NOTE = "The autocorrelation requires a regular time frequency."


def daily_frame() -> pd.DataFrame:
    """Return 21 regular days with a weekly pattern, one duplicate day and one invalid row."""
    days = list(pd.date_range("2024-01-01", periods=21, freq="D"))
    sales = [10.0 + (index % 7) + index * 0.5 for index in range(21)]
    return pd.DataFrame({
        "day": [*days, days[0], pd.NaT],
        "sales": [*sales, sales[0], 5.0],
        "name": list("abcdefghijklmnopqrstuvw"),
    })


def irregular_frame() -> pd.DataFrame:
    """Return an irregularly spaced series without autocorrelation or decomposition."""
    return pd.DataFrame({
        "day": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-05", "2024-01-11"]),
        "sales": [1.0, 2.0, 4.0, 3.0],
    })


def time_series_result(frame: pd.DataFrame | None = None) -> TimeSeriesResult:
    """Return a successful analysis of `daily_frame` or `frame`."""
    result = analyze_time_series(daily_frame() if frame is None else frame, "day", "sales")
    assert result.error is None
    return result


def time_series_snapshot(
    frame: pd.DataFrame | None = None, *, notes: tuple[str, ...] = NOTES
) -> TimeSeriesExportSnapshot:
    result = time_series_result(frame)
    reason = IRREGULAR_NOTE if not result.acf_values else ""
    return TimeSeriesExportSnapshot(result, CHART_LABELS, notes, reason)


def irregular_snapshot() -> TimeSeriesExportSnapshot:
    return time_series_snapshot(irregular_frame())


# ----------------------------------------------------------------------
# Snapshot
# ----------------------------------------------------------------------


def test_regular_snapshot_offers_every_component():
    snapshot = time_series_snapshot()

    assert snapshot.components == TIME_SERIES_COMPONENTS
    assert TIME_SERIES_COMPONENTS == (
        TimeSeriesExportComponent.SERIES,
        TimeSeriesExportComponent.AUTOCORRELATION,
        TimeSeriesExportComponent.MODEL_SUMMARY,
        TimeSeriesExportComponent.CHARTS,
    )


def test_snapshot_without_autocorrelation_omits_that_component():
    snapshot = irregular_snapshot()

    assert TimeSeriesExportComponent.AUTOCORRELATION not in snapshot.components
    assert snapshot.components == (
        TimeSeriesExportComponent.SERIES,
        TimeSeriesExportComponent.MODEL_SUMMARY,
        TimeSeriesExportComponent.CHARTS,
    )
    assert snapshot.autocorrelation_note == IRREGULAR_NOTE


def test_snapshot_requires_a_typed_result_and_labels():
    with pytest.raises(TypeError, match="time-series result"):
        TimeSeriesExportSnapshot(object(), CHART_LABELS)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="chart labels"):
        TimeSeriesExportSnapshot(time_series_result(), object())  # type: ignore[arg-type]


def test_snapshot_rejects_failed_and_unanalyzed_results():
    failed = analyze_time_series(pd.DataFrame({"sales": [1.0, 2.0]}))
    assert failed.error is not None
    with pytest.raises(ValueError, match="failed"):
        TimeSeriesExportSnapshot(failed, CHART_LABELS)
    with pytest.raises(ValueError, match="analyzed"):
        TimeSeriesExportSnapshot(dataclasses.replace(time_series_result(), timestamps=()), CHART_LABELS)


# ----------------------------------------------------------------------
# Request
# ----------------------------------------------------------------------


@pytest.mark.parametrize("fmt", list(StatisticsExportFormat))
@pytest.mark.parametrize(
    "component",
    [
        TimeSeriesExportComponent.SERIES,
        TimeSeriesExportComponent.AUTOCORRELATION,
        TimeSeriesExportComponent.MODEL_SUMMARY,
    ],
)
def test_request_accepts_one_table_in_every_format(fmt, component):
    request = TimeSeriesExportRequest(time_series_snapshot(), (component,), fmt)

    assert request.components == (component,)


def test_excel_request_accepts_tables_with_charts_and_charts_only():
    snapshot = time_series_snapshot()

    assert TimeSeriesExportRequest(snapshot, TIME_SERIES_COMPONENTS, StatisticsExportFormat.EXCEL)
    assert TimeSeriesExportRequest(snapshot, (TimeSeriesExportComponent.CHARTS,), StatisticsExportFormat.EXCEL)


def test_request_rejects_unavailable_autocorrelation():
    with pytest.raises(ValueError, match="unavailable"):
        TimeSeriesExportRequest(
            irregular_snapshot(), (TimeSeriesExportComponent.AUTOCORRELATION,), StatisticsExportFormat.CSV
        )


@pytest.mark.parametrize("fmt", [StatisticsExportFormat.CSV, StatisticsExportFormat.BINARY])
@pytest.mark.parametrize(
    "components",
    [
        (TimeSeriesExportComponent.CHARTS,),
        (TimeSeriesExportComponent.SERIES, TimeSeriesExportComponent.MODEL_SUMMARY),
    ],
)
def test_non_excel_request_requires_exactly_one_table_without_charts(fmt, components):
    with pytest.raises(ValueError, match="exactly one table"):
        TimeSeriesExportRequest(time_series_snapshot(), components, fmt)


@pytest.mark.parametrize(
    "components",
    [(), (TimeSeriesExportComponent.SERIES, TimeSeriesExportComponent.SERIES)],
)
def test_request_rejects_empty_or_duplicate_components(components):
    with pytest.raises(ValueError, match="distinct"):
        TimeSeriesExportRequest(time_series_snapshot(), components, StatisticsExportFormat.EXCEL)


def test_request_rejects_untyped_values():
    snapshot = time_series_snapshot()
    with pytest.raises(TypeError, match="snapshot"):
        TimeSeriesExportRequest(
            object(),  # type: ignore[arg-type]
            (TimeSeriesExportComponent.SERIES,),
            StatisticsExportFormat.EXCEL,
        )
    with pytest.raises(ValueError, match="Unknown time-series export component"):
        TimeSeriesExportRequest(snapshot, ("series",), StatisticsExportFormat.EXCEL)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="format"):
        TimeSeriesExportRequest(snapshot, (TimeSeriesExportComponent.SERIES,), "excel")  # type: ignore[arg-type]


# ----------------------------------------------------------------------
# Tables
# ----------------------------------------------------------------------


def test_export_tables_follow_selection_order_and_skip_charts():
    tables = time_series_export_tables(
        time_series_snapshot(),
        (
            TimeSeriesExportComponent.CHARTS,
            TimeSeriesExportComponent.MODEL_SUMMARY,
            TimeSeriesExportComponent.AUTOCORRELATION,
            TimeSeriesExportComponent.SERIES,
        ),
    )

    assert list(tables) == [
        TimeSeriesExportComponent.MODEL_SUMMARY,
        TimeSeriesExportComponent.AUTOCORRELATION,
        TimeSeriesExportComponent.SERIES,
    ]


def test_decomposed_series_has_the_prepared_values_and_components():
    snapshot = time_series_snapshot()
    result = snapshot.result
    assert result.trend

    table = series_table(snapshot)

    assert table.columns.tolist() == ["timestamp", "value", "trend", "seasonal", "residual"]
    assert len(table) == 21
    assert table["timestamp"].tolist() == list(result.timestamps)
    assert table["value"].tolist() == pytest.approx(list(result.values))
    assert table["trend"].tolist() == pytest.approx(list(result.trend), nan_ok=True)
    assert table["seasonal"].tolist() == pytest.approx(list(result.seasonal))
    assert table["residual"].tolist() == pytest.approx(list(result.residual), nan_ok=True)
    assert pd.api.types.is_datetime64_any_dtype(table["timestamp"])
    assert all(table[name].dtype == "float64" for name in ("value", "trend", "seasonal", "residual"))


def test_series_averages_duplicate_timestamps():
    table = series_table(time_series_snapshot())

    assert table["value"].iloc[0] == pytest.approx(10.0)


def test_undecomposed_series_has_only_timestamp_and_value():
    table = series_table(irregular_snapshot())

    assert table.columns.tolist() == ["timestamp", "value"]
    assert table["value"].tolist() == [1.0, 2.0, 4.0, 3.0]


def test_series_keeps_timezone_and_resampled_gaps():
    frame = pd.DataFrame({
        "day": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-04", "2024-01-05"]).tz_localize("Europe/Stockholm"),
        "sales": [1.0, 2.0, 4.0, 3.0],
    })
    result = analyze_time_series(frame, "day", "sales", resample_frequency="D")
    assert result.error is None

    table = series_table(TimeSeriesExportSnapshot(result, CHART_LABELS))

    assert str(table["timestamp"].dt.tz) == "Europe/Stockholm"
    assert len(table) == 5
    assert math.isnan(table["value"].iloc[2])


def test_autocorrelation_starts_at_lag_one():
    snapshot = time_series_snapshot()
    result = snapshot.result

    table = autocorrelation_table(snapshot)

    assert table.columns.tolist() == ["lag", "autocorrelation"]
    assert table["lag"].tolist() == list(range(1, len(result.acf_values) + 1))
    assert table["autocorrelation"].tolist() == pytest.approx(list(result.acf_values))
    assert isinstance(table["lag"].dtype, pd.Int64Dtype)
    assert table["autocorrelation"].dtype == "float64"


def test_model_summary_lists_row_diagnostics_period_and_notes():
    table = time_series_model_summary_table(time_series_snapshot())

    assert table.columns.tolist() == ["metric", "value", "notes"]
    assert table["metric"].tolist() == [
        TimeSeriesMetric.SOURCE_ROWS,
        TimeSeriesMetric.INVALID_ROWS,
        TimeSeriesMetric.DUPLICATE_ROWS,
        TimeSeriesMetric.TIME_POINTS,
        TimeSeriesMetric.SEASONAL_PERIOD,
    ]
    assert table["value"].tolist() == [23.0, 1.0, 1.0, 21.0, 7.0]
    assert table["notes"].tolist()[: len(NOTES)] == list(NOTES)
    assert table["notes"].iloc[len(NOTES) :].isna().all()
    assert isinstance(table["metric"].dtype, pd.StringDtype)
    assert isinstance(table["notes"].dtype, pd.StringDtype)
    assert table["value"].dtype == "float64"


def test_undetected_seasonal_period_is_missing():
    table = time_series_model_summary_table(irregular_snapshot())

    assert table["metric"].iloc[-1] == TimeSeriesMetric.SEASONAL_PERIOD
    assert math.isnan(table["value"].iloc[-1])


def test_more_notes_than_metrics_extend_the_table():
    notes = tuple(f"Line {index}" for index in range(7))

    table = time_series_model_summary_table(time_series_snapshot(notes=notes))

    assert len(table) == 7
    assert table["notes"].tolist() == list(notes)
    assert table["metric"].iloc[5:].isna().all()
    assert table["value"].iloc[5:].isna().all()
