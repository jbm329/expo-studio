from __future__ import annotations

import dataclasses
import math

import pandas as pd
import pytest

from expo_jbm329.services.analysis.multivariate_outliers import (
    MultivariateOutlierError,
    MultivariateOutlierMethod,
    MultivariateOutlierResult,
    analyze_multivariate_outliers,
)
from expo_jbm329.services.analysis.outliers import (
    ColumnOutlierStatus,
    OutlierColumnDetail,
    OutlierError,
    OutlierMethod,
    OutlierSummaryResult,
    analyze_outlier_column,
    analyze_outlier_summary,
)
from expo_jbm329.services.analysis.outliers_charts import OutlierHistogramLabels, OutlierProjectionLabels
from expo_jbm329.services.analysis.outliers_export import (
    MULTIVARIATE_COMPONENTS,
    UNIVARIATE_COMPONENTS,
    MultivariateOutlierExportSnapshot,
    OutlierExportComponent,
    OutlierExportRequest,
    OutlierMetric,
    UnivariateOutlierExportSnapshot,
    outlier_column_details_table,
    outlier_column_summary_table,
    outlier_export_tables,
    outlier_model_summary_table,
    potential_outliers_table,
    unique_headers,
)
from expo_jbm329.services.analysis.statistics import StatisticsExportFormat

HISTOGRAM_LABELS = OutlierHistogramLabels(inside="Inside", outliers="Flagged", count_axis="Count")
PROJECTION_LABELS = OutlierProjectionLabels(
    heading="PCA projection",
    title="PCA projection (visualization only)",
    pc1_axis="PC1",
    pc2_axis="PC2",
    inliers="Inliers",
    outliers="Potential outliers",
    captions=("Sampled",),
)
SUMMARY_NOTES = ("IQR, threshold 1.5: 1 of 10 rows.", "Flagged values are potential outliers.")
DETAIL_NOTES = ("Potential outliers, most extreme first", "a - IQR, threshold 1.5")


def outlier_frame() -> pd.DataFrame:
    """Return a dataset with one clear outlier, an unscreenable column and text."""
    return pd.DataFrame({
        "a": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 100.0],
        "b": [float(value) for value in range(10)],
        "few": [1.0, 2.0, *([None] * 8)],
        "Row": list(range(10, 20)),
        "label": list("abcdefghij"),
    })


def univariate_summary(method: OutlierMethod = OutlierMethod.IQR) -> OutlierSummaryResult:
    return analyze_outlier_summary(outlier_frame(), method)


def univariate_detail(column: str = "a", method: OutlierMethod = OutlierMethod.IQR) -> OutlierColumnDetail:
    return analyze_outlier_column(outlier_frame(), column, method)


def univariate_snapshot(
    method: OutlierMethod = OutlierMethod.IQR,
    column: str | None = "a",
    *,
    summary_notes: tuple[str, ...] = SUMMARY_NOTES,
    detail_notes: tuple[str, ...] = DETAIL_NOTES,
) -> UnivariateOutlierExportSnapshot:
    summary = univariate_summary(method)
    df = outlier_frame()
    return UnivariateOutlierExportSnapshot(
        summary=summary,
        data=df.loc[:, list(summary.available_columns)].copy(),
        chart_labels=HISTOGRAM_LABELS,
        summary_notes=summary_notes,
        detail=None if column is None else univariate_detail(column, method),
        detail_notes=() if column is None else detail_notes,
    )


def multivariate_result(
    method: MultivariateOutlierMethod = MultivariateOutlierMethod.ISOLATION_FOREST,
) -> MultivariateOutlierResult:
    df = pd.DataFrame({
        "x": [0.0, 0.1, -0.1, 10.0, 10.1, 9.9, 30.0],
        "y": [0.0, 0.1, -0.1, 10.0, 9.9, 10.1, 30.0],
        "name": list("abcdefg"),
    })
    result = analyze_multivariate_outliers(df, columns=("x", "y"), method=method, contamination=0.2, lof_neighbors=2)
    assert result.error is None
    return result


def multivariate_snapshot(
    method: MultivariateOutlierMethod = MultivariateOutlierMethod.ISOLATION_FOREST,
) -> MultivariateOutlierExportSnapshot:
    return MultivariateOutlierExportSnapshot(
        multivariate_result(method), PROJECTION_LABELS, ("Isolation Forest on 2 features.", "Features: x, y")
    )


# ----------------------------------------------------------------------
# Snapshots
# ----------------------------------------------------------------------


def test_univariate_snapshot_offers_every_displayed_component():
    snapshot = univariate_snapshot()

    assert snapshot.components == UNIVARIATE_COMPONENTS
    assert snapshot.chart_columns == ("a", "b", "Row")
    assert all(snapshot.is_available(component) for component in UNIVARIATE_COMPONENTS)
    assert not snapshot.is_available(OutlierExportComponent.MODEL_SUMMARY)


def test_univariate_snapshot_without_detail_offers_only_summary_and_charts():
    snapshot = univariate_snapshot(column=None)

    assert snapshot.is_available(OutlierExportComponent.COLUMN_SUMMARY)
    assert snapshot.is_available(OutlierExportComponent.CHARTS)
    assert not snapshot.is_available(OutlierExportComponent.COLUMN_DETAILS)
    assert not snapshot.is_available(OutlierExportComponent.POTENTIAL_OUTLIERS)


def test_column_without_flagged_rows_has_no_potential_outliers_component():
    snapshot = univariate_snapshot(column="b")

    assert snapshot.is_available(OutlierExportComponent.COLUMN_DETAILS)
    assert not snapshot.is_available(OutlierExportComponent.POTENTIAL_OUTLIERS)


def test_charts_are_unavailable_when_no_column_was_screened():
    df = pd.DataFrame({"few": [1.0, 2.0, None, None, None]})
    summary = analyze_outlier_summary(df)
    snapshot = UnivariateOutlierExportSnapshot(summary, df.copy(), HISTOGRAM_LABELS)

    assert snapshot.chart_columns == ()
    assert not snapshot.is_available(OutlierExportComponent.CHARTS)


def test_with_detail_replaces_only_the_selected_column():
    snapshot = univariate_snapshot()
    detail = univariate_detail("b")

    changed = snapshot.with_detail(detail, ("b notes",))
    cleared = snapshot.with_detail(None, ())

    assert changed.detail is detail
    assert changed.detail_notes == ("b notes",)
    assert changed.summary is snapshot.summary
    assert changed.data is snapshot.data
    assert cleared.detail is None
    assert snapshot.detail is not detail


@pytest.mark.parametrize(
    ("change", "error"),
    [
        (lambda s: {"summary": object()}, TypeError),
        (lambda s: {"summary": dataclasses.replace(s.summary, error=OutlierError.NO_NUMERIC_COLUMN)}, ValueError),
        (lambda s: {"summary": dataclasses.replace(s.summary, columns=())}, ValueError),
        (lambda s: {"data": [1, 2]}, TypeError),
        (lambda s: {"data": s.data.iloc[:, :2]}, ValueError),
        (lambda s: {"data": s.data.iloc[:5]}, ValueError),
        (lambda s: {"chart_labels": PROJECTION_LABELS}, TypeError),
        (lambda s: {"detail": dataclasses.replace(s.detail, error=OutlierError.INVALID_COLUMN)}, ValueError),
        (lambda s: {"detail": univariate_detail(method=OutlierMethod.Z_SCORE)}, ValueError),
        (lambda s: {"detail": dataclasses.replace(s.detail, threshold=2.0)}, ValueError),
        (
            lambda s: {
                "detail": dataclasses.replace(s.detail, summary=dataclasses.replace(s.detail.summary, column="x"))
            },
            ValueError,
        ),
    ],
)
def test_univariate_snapshot_rejects_invalid_state(change, error):
    snapshot = univariate_snapshot()

    with pytest.raises(error):
        dataclasses.replace(snapshot, **change(snapshot))


def test_multivariate_snapshot_offers_model_summary_rows_and_projection():
    snapshot = multivariate_snapshot()

    assert snapshot.components == MULTIVARIATE_COMPONENTS
    assert all(snapshot.is_available(component) for component in MULTIVARIATE_COMPONENTS)
    assert not snapshot.is_available(OutlierExportComponent.COLUMN_SUMMARY)
    assert not snapshot.is_available(OutlierExportComponent.COLUMN_DETAILS)


def test_multivariate_snapshot_without_rows_has_no_potential_outliers_component():
    snapshot = dataclasses.replace(
        multivariate_snapshot(), result=dataclasses.replace(multivariate_result(), extremes=())
    )

    assert not snapshot.is_available(OutlierExportComponent.POTENTIAL_OUTLIERS)


@pytest.mark.parametrize(
    ("change", "error"),
    [
        (lambda s: {"result": object()}, TypeError),
        (
            lambda s: {"result": dataclasses.replace(s.result, error=MultivariateOutlierError.NO_VARIATION)},
            ValueError,
        ),
        (lambda s: {"result": dataclasses.replace(s.result, rows_used=0)}, ValueError),
        (lambda s: {"result": dataclasses.replace(s.result, sample_pc1=())}, ValueError),
        (lambda s: {"chart_labels": HISTOGRAM_LABELS}, TypeError),
    ],
)
def test_multivariate_snapshot_rejects_invalid_state(change, error):
    snapshot = multivariate_snapshot()

    with pytest.raises(error):
        dataclasses.replace(snapshot, **change(snapshot))


# ----------------------------------------------------------------------
# Requests
# ----------------------------------------------------------------------


@pytest.mark.parametrize("excel_components", [UNIVARIATE_COMPONENTS])
def test_excel_request_accepts_every_available_component(excel_components):
    request = OutlierExportRequest(univariate_snapshot(), excel_components, StatisticsExportFormat.EXCEL)

    assert request.components == excel_components


@pytest.mark.parametrize("export_format", [StatisticsExportFormat.CSV, StatisticsExportFormat.BINARY])
def test_csv_and_binary_requests_accept_one_table(export_format):
    request = OutlierExportRequest(multivariate_snapshot(), (OutlierExportComponent.POTENTIAL_OUTLIERS,), export_format)

    assert request.format is export_format


@pytest.mark.parametrize(
    ("components", "export_format", "error"),
    [
        ((), StatisticsExportFormat.EXCEL, ValueError),
        (
            (OutlierExportComponent.COLUMN_SUMMARY, OutlierExportComponent.COLUMN_SUMMARY),
            StatisticsExportFormat.EXCEL,
            ValueError,
        ),
        (("column_summary",), StatisticsExportFormat.EXCEL, ValueError),
        ((OutlierExportComponent.COLUMN_SUMMARY,), "xlsx", TypeError),
        ((OutlierExportComponent.MODEL_SUMMARY,), StatisticsExportFormat.EXCEL, ValueError),
        ((OutlierExportComponent.CHARTS,), StatisticsExportFormat.CSV, ValueError),
        (
            (OutlierExportComponent.COLUMN_SUMMARY, OutlierExportComponent.COLUMN_DETAILS),
            StatisticsExportFormat.BINARY,
            ValueError,
        ),
    ],
)
def test_request_rejects_invalid_selection(components, export_format, error):
    with pytest.raises(error):
        OutlierExportRequest(univariate_snapshot(), components, export_format)


def test_request_rejects_empty_potential_outliers():
    with pytest.raises(ValueError, match="non-empty"):
        OutlierExportRequest(
            univariate_snapshot(column="b"),
            (OutlierExportComponent.POTENTIAL_OUTLIERS,),
            StatisticsExportFormat.EXCEL,
        )


# ----------------------------------------------------------------------
# Tables
# ----------------------------------------------------------------------


def test_column_summary_keeps_ranking_types_statuses_and_notes():
    snapshot = univariate_snapshot()
    frame = outlier_column_summary_table(snapshot)

    assert list(frame.columns) == [
        "column",
        "values",
        "missing",
        "outliers",
        "share",
        "low",
        "high",
        "lower_fence",
        "upper_fence",
        "status",
        "notes",
    ]
    assert list(frame["column"]) == [row.column for row in snapshot.summary.columns]
    assert frame["column"].dtype == pd.StringDtype()
    assert frame["values"].dtype == pd.Int64Dtype()
    assert frame["outliers"].dtype == pd.Int64Dtype()
    assert frame["share"].dtype == "float64"
    assert frame["status"].dtype == pd.StringDtype()
    first = snapshot.summary.columns[0]
    assert frame.loc[0, "outliers"] == first.outlier_count
    assert frame.loc[0, "share"] == pytest.approx(first.outlier_fraction)
    assert frame.loc[0, "lower_fence"] == pytest.approx(first.lower_fence)
    assert pd.isna(frame.loc[0, "status"])
    few = frame.index[frame["column"] == "few"][0]
    assert frame.loc[few, "values"] == 2
    assert pd.isna(frame.loc[few, "outliers"])
    assert math.isnan(frame.loc[few, "share"])
    assert math.isnan(frame.loc[few, "upper_fence"])
    assert frame.loc[few, "status"] == ColumnOutlierStatus.NOT_ENOUGH_OBSERVATIONS.value
    assert list(frame["notes"].dropna()) == list(SUMMARY_NOTES)


def test_column_summary_adds_rows_for_extra_notes():
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0, 50.0]})
    summary = analyze_outlier_summary(df)
    notes = ("one", "two", "three")
    frame = outlier_column_summary_table(UnivariateOutlierExportSnapshot(summary, df.copy(), HISTOGRAM_LABELS, notes))

    assert len(frame) == 3
    assert list(frame["notes"]) == list(notes)
    assert pd.isna(frame.loc[1, "column"])
    assert pd.isna(frame.loc[1, "values"])
    assert frame["values"].dtype == pd.Int64Dtype()


@pytest.mark.parametrize(
    ("method", "method_metrics"),
    [
        (OutlierMethod.IQR, [OutlierMetric.Q1, OutlierMetric.Q3, OutlierMetric.IQR]),
        (OutlierMethod.Z_SCORE, [OutlierMetric.MEAN, OutlierMetric.STD]),
        (OutlierMethod.MODIFIED_Z_SCORE, [OutlierMetric.MEDIAN, OutlierMetric.MAD]),
    ],
)
def test_column_details_list_the_displayed_method_statistics(method, method_metrics):
    snapshot = univariate_snapshot(method)
    frame = outlier_column_details_table(snapshot)
    detail = snapshot.detail
    assert detail is not None

    assert list(frame["metric"].dropna()) == [
        OutlierMetric.THRESHOLD,
        OutlierMetric.VALUES,
        OutlierMetric.MISSING,
        OutlierMetric.OUTLIERS,
        OutlierMetric.OUTLIER_SHARE,
        OutlierMetric.LOW,
        OutlierMetric.HIGH,
        OutlierMetric.LOWER_FENCE,
        OutlierMetric.UPPER_FENCE,
        *method_metrics,
    ]
    values = dict(zip(frame["metric"], frame["value"], strict=True))
    assert values[OutlierMetric.THRESHOLD] == pytest.approx(detail.threshold)
    assert values[OutlierMetric.OUTLIERS] == detail.summary.outlier_count
    assert frame["value"].dtype == "float64"
    assert list(frame["notes"].dropna()) == list(DETAIL_NOTES)


def test_column_details_of_unscreened_column_keep_only_counts():
    frame = outlier_column_details_table(univariate_snapshot(column="few", detail_notes=("Too few values",) * 4))

    assert list(frame["metric"].dropna()) == [OutlierMetric.THRESHOLD, OutlierMetric.VALUES, OutlierMetric.MISSING]
    assert len(frame) == 4
    assert pd.isna(frame.loc[3, "metric"])
    assert math.isnan(frame.loc[3, "value"])


def test_column_details_require_a_displayed_column():
    with pytest.raises(ValueError, match="No column detail"):
        outlier_column_details_table(univariate_snapshot(column=None))


@pytest.mark.parametrize(
    ("method", "neighbors"),
    [(MultivariateOutlierMethod.ISOLATION_FOREST, False), (MultivariateOutlierMethod.LOCAL_OUTLIER_FACTOR, True)],
)
def test_model_summary_lists_settings_counts_and_comments(method, neighbors):
    snapshot = multivariate_snapshot(method)
    result = snapshot.result
    frame = outlier_model_summary_table(snapshot)
    values = dict(zip(frame["metric"], frame["value"], strict=True))

    assert (OutlierMetric.LOF_NEIGHBORS in values) is neighbors
    assert values[OutlierMetric.FEATURES] == 2
    assert values[OutlierMetric.CONTAMINATION] == pytest.approx(0.2)
    assert values[OutlierMetric.TOTAL_ROWS] == result.total_rows
    assert values[OutlierMetric.ROWS_USED] == result.rows_used
    assert values[OutlierMetric.ROWS_DROPPED] == result.rows_dropped
    assert values[OutlierMetric.OUTLIERS] == result.outlier_count
    assert values[OutlierMetric.OUTLIER_SHARE] == pytest.approx(result.outlier_count / result.rows_used)
    assert values[OutlierMetric.INLIERS] == result.inlier_count
    assert list(frame["notes"].dropna()) == list(snapshot.notes)
    if neighbors:
        assert values[OutlierMetric.LOF_NEIGHBORS] == 2


def test_univariate_potential_outliers_put_value_and_score_first_and_rename_collisions():
    snapshot = univariate_snapshot()
    detail = snapshot.detail
    assert detail is not None
    frame = potential_outliers_table(snapshot, row_label="Row", score_label="Distance past fence")

    assert list(frame.columns) == ["Row (2)", "a", "Distance past fence", "b", "few", "Row", "label"]
    assert len(frame) == len(detail.extremes) == 1
    assert frame["Row (2)"].dtype == "int64"
    assert frame.loc[0, "Row (2)"] == 10
    assert frame.loc[0, "a"] == pytest.approx(100.0)
    assert frame.loc[0, "Distance past fence"] == pytest.approx(detail.extremes[0].score)
    assert frame.loc[0, "Row"] == 19
    assert frame["label"].dtype == pd.StringDtype()
    assert frame.loc[0, "label"] == "j"


def test_multivariate_potential_outliers_list_every_dataset_column():
    snapshot = multivariate_snapshot()
    result = snapshot.result
    frame = potential_outliers_table(snapshot, row_label="Rad", score_label="Avvikelsepoäng")

    assert list(frame.columns) == ["Rad", "Avvikelsepoäng", "x", "y", "name"]
    assert len(frame) == len(result.extremes)
    assert list(frame["Rad"]) == [item.row_number for item in result.extremes]
    assert frame["Avvikelsepoäng"].dtype == "float64"
    assert frame["x"].dtype == "float64"
    assert frame["name"].dtype == pd.StringDtype()


def test_potential_outliers_require_displayed_rows():
    with pytest.raises(ValueError, match="No potential outliers"):
        potential_outliers_table(univariate_snapshot(column="b"))


def test_mixed_value_types_stay_objects():
    result = dataclasses.replace(
        multivariate_result(),
        row_columns=("mixed",),
        extremes=tuple(
            dataclasses.replace(item, row_values=(value,))
            for item, value in zip(multivariate_result().extremes, ["x", 1], strict=False)
        ),
    )
    frame = potential_outliers_table(MultivariateOutlierExportSnapshot(result, PROJECTION_LABELS))

    assert frame["mixed"].dtype == object


def test_export_tables_follow_selection_order_and_skip_charts():
    tables = outlier_export_tables(
        univariate_snapshot(),
        (
            OutlierExportComponent.POTENTIAL_OUTLIERS,
            OutlierExportComponent.CHARTS,
            OutlierExportComponent.COLUMN_DETAILS,
            OutlierExportComponent.COLUMN_SUMMARY,
        ),
        row_label="Rad",
        score_label="Avstånd",
    )

    assert list(tables) == [
        OutlierExportComponent.POTENTIAL_OUTLIERS,
        OutlierExportComponent.COLUMN_DETAILS,
        OutlierExportComponent.COLUMN_SUMMARY,
    ]
    assert list(tables[OutlierExportComponent.POTENTIAL_OUTLIERS].columns[:3]) == ["Rad", "a", "Avstånd"]


def test_export_tables_build_the_multivariate_model_summary():
    tables = outlier_export_tables(multivariate_snapshot(), (OutlierExportComponent.MODEL_SUMMARY,))

    assert list(tables[OutlierExportComponent.MODEL_SUMMARY].columns) == ["metric", "value", "notes"]


def test_export_tables_reject_components_of_the_other_mode():
    with pytest.raises(ValueError, match="column_summary"):
        outlier_export_tables(multivariate_snapshot(), (OutlierExportComponent.COLUMN_SUMMARY,))


def test_export_tables_return_fresh_frames():
    snapshot = univariate_snapshot()
    first = outlier_export_tables(snapshot, (OutlierExportComponent.COLUMN_SUMMARY,))
    first[OutlierExportComponent.COLUMN_SUMMARY].loc[0, "column"] = "changed"

    second = outlier_export_tables(snapshot, (OutlierExportComponent.COLUMN_SUMMARY,))

    assert second[OutlierExportComponent.COLUMN_SUMMARY].loc[0, "column"] == "a"


@pytest.mark.parametrize(
    ("fixed", "existing", "expected"),
    [
        (("Row", "Score"), ("a", "b"), ("Row", "Score")),
        (("Row", "Score"), ("Row",), ("Row (2)", "Score")),
        (("Row", "Score"), ("Row", "Row (2)", "Score"), ("Row (3)", "Score (2)")),
        (("Row", "Row"), (), ("Row", "Row (2)")),
    ],
)
def test_unique_headers_keep_dataset_columns_and_number_collisions(fixed, existing, expected):
    assert unique_headers(fixed, existing) == expected
