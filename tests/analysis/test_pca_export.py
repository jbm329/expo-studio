from __future__ import annotations

import dataclasses

import pandas as pd
import pytest

from expo_jbm329.services.analysis.chart_presentation import ChartPresentationMetadata
from expo_jbm329.services.analysis.pca import PCAResult, analyze_pca
from expo_jbm329.services.analysis.pca_charts import PCAChartLabels, build_pca_chart_labels
from expo_jbm329.services.analysis.pca_export import (
    PCA_COMPONENTS,
    PCAExportComponent,
    PCAExportRequest,
    PCAExportSnapshot,
    PCAMetric,
    component_name,
    explained_variance_table,
    feature_loadings_table,
    pca_export_tables,
    pca_model_summary_table,
)
from expo_jbm329.services.analysis.statistics import StatisticsExportFormat

CHART_LABELS = PCAChartLabels(
    scree_metadata=ChartPresentationMetadata("", "Scree plot"),
    explained="Explained variance",
    cumulative="Cumulative",
    component_axis="Component",
    variance_axis="Explained variance (%)",
    scatter_metadata=ChartPresentationMetadata("", "PC1 vs PC2"),
    pc1_axis="PC1 (80%)",
    pc2_axis="PC2 (15%)",
)
NOTES = ("3 features, standardized.", "Features: x, y, z")


def pca_frame() -> pd.DataFrame:
    """Return three related numeric features, one incomplete row and a text column."""
    return pd.DataFrame({
        "x": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, None],
        "y": [2.1, 3.9, 6.2, 8.1, 9.8, 12.2, 13.9, 1.0],
        "z": [5.0, 3.0, 4.0, 1.0, 2.0, 0.5, 1.5, 2.0],
        "name": list("abcdefgh"),
    })


def pca_result(**kwargs: object) -> PCAResult:
    """Return a successful fit of `pca_frame`."""
    result = analyze_pca(pca_frame(), ("x", "y", "z"), **kwargs)  # type: ignore[arg-type]
    assert result.error is None
    return result


def pca_snapshot(*, notes: tuple[str, ...] = NOTES, sampled: bool = False, **kwargs: object) -> PCAExportSnapshot:
    result = dataclasses.replace(pca_result(**kwargs), sampled=sampled)
    labels = build_pca_chart_labels(
        result, lambda _context, text: text, percent_format=lambda value: f"{value * 100:.2f}%"
    )
    return PCAExportSnapshot(result, labels, notes)


# ----------------------------------------------------------------------
# Snapshot
# ----------------------------------------------------------------------


def test_snapshot_offers_every_component():
    snapshot = pca_snapshot()

    assert snapshot.components == PCA_COMPONENTS
    assert snapshot.capture_id
    assert dataclasses.replace(snapshot).capture_id == snapshot.capture_id
    assert pca_snapshot().capture_id != snapshot.capture_id
    assert PCA_COMPONENTS == (
        PCAExportComponent.FEATURE_LOADINGS,
        PCAExportComponent.EXPLAINED_VARIANCE,
        PCAExportComponent.MODEL_SUMMARY,
        PCAExportComponent.CHARTS,
    )


def test_snapshot_requires_a_typed_result_and_labels():
    with pytest.raises(TypeError, match="PCA result"):
        PCAExportSnapshot(object(), CHART_LABELS)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="chart labels"):
        PCAExportSnapshot(pca_result(), object())  # type: ignore[arg-type]


def test_snapshot_rejects_failed_and_unfitted_results():
    failed = analyze_pca(pca_frame(), ("x",))
    assert failed.error is not None
    with pytest.raises(ValueError, match="failed"):
        PCAExportSnapshot(failed, CHART_LABELS)
    for changes in ({"rows_used": 0}, {"loadings": ()}, {"sample_pc1": ()}):
        with pytest.raises(ValueError, match="fitted"):
            PCAExportSnapshot(dataclasses.replace(pca_result(), **changes), CHART_LABELS)  # type: ignore[arg-type]


def test_component_names_are_one_based():
    assert [component_name(index) for index in range(3)] == ["PC1", "PC2", "PC3"]


# ----------------------------------------------------------------------
# Request
# ----------------------------------------------------------------------


@pytest.mark.parametrize("fmt", list(StatisticsExportFormat))
@pytest.mark.parametrize(
    "component",
    [PCAExportComponent.FEATURE_LOADINGS, PCAExportComponent.EXPLAINED_VARIANCE, PCAExportComponent.MODEL_SUMMARY],
)
def test_request_accepts_one_table_in_every_format(fmt, component):
    request = PCAExportRequest(pca_snapshot(), (component,), fmt)

    assert request.components == (component,)


def test_excel_request_accepts_tables_with_charts_and_charts_only():
    snapshot = pca_snapshot()

    assert PCAExportRequest(snapshot, PCA_COMPONENTS, StatisticsExportFormat.EXCEL)
    assert PCAExportRequest(snapshot, (PCAExportComponent.CHARTS,), StatisticsExportFormat.EXCEL)


@pytest.mark.parametrize("fmt", [StatisticsExportFormat.CSV, StatisticsExportFormat.BINARY])
@pytest.mark.parametrize(
    "components",
    [
        (PCAExportComponent.CHARTS,),
        (PCAExportComponent.FEATURE_LOADINGS, PCAExportComponent.MODEL_SUMMARY),
    ],
)
def test_non_excel_request_requires_exactly_one_table_without_charts(fmt, components):
    with pytest.raises(ValueError, match="exactly one table"):
        PCAExportRequest(pca_snapshot(), components, fmt)


@pytest.mark.parametrize(
    "components",
    [(), (PCAExportComponent.FEATURE_LOADINGS, PCAExportComponent.FEATURE_LOADINGS)],
)
def test_request_rejects_empty_or_duplicate_components(components):
    with pytest.raises(ValueError, match="distinct"):
        PCAExportRequest(pca_snapshot(), components, StatisticsExportFormat.EXCEL)


def test_request_rejects_untyped_values():
    snapshot = pca_snapshot()
    with pytest.raises(TypeError, match="snapshot"):
        PCAExportRequest(
            object(),  # type: ignore[arg-type]
            (PCAExportComponent.FEATURE_LOADINGS,),
            StatisticsExportFormat.EXCEL,
        )
    with pytest.raises(ValueError, match="Unknown PCA export component"):
        PCAExportRequest(snapshot, ("feature_loadings",), StatisticsExportFormat.EXCEL)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="format"):
        PCAExportRequest(snapshot, (PCAExportComponent.FEATURE_LOADINGS,), "excel")  # type: ignore[arg-type]


# ----------------------------------------------------------------------
# Tables
# ----------------------------------------------------------------------


def test_export_tables_follow_selection_order_and_skip_charts():
    tables = pca_export_tables(
        pca_snapshot(),
        (
            PCAExportComponent.CHARTS,
            PCAExportComponent.MODEL_SUMMARY,
            PCAExportComponent.EXPLAINED_VARIANCE,
            PCAExportComponent.FEATURE_LOADINGS,
        ),
    )

    assert list(tables) == [
        PCAExportComponent.MODEL_SUMMARY,
        PCAExportComponent.EXPLAINED_VARIANCE,
        PCAExportComponent.FEATURE_LOADINGS,
    ]


def test_feature_loadings_keep_displayed_features_and_values():
    snapshot = pca_snapshot()
    result = snapshot.result

    table = feature_loadings_table(snapshot)

    assert table.columns.tolist() == ["feature", "PC1", "PC2", "PC3"]
    assert table["feature"].tolist() == ["x", "y", "z"]
    for row, loadings in enumerate(result.loadings):
        assert table.iloc[row, 1:].tolist() == pytest.approx(list(loadings))
    assert isinstance(table["feature"].dtype, pd.StringDtype)
    assert all(table[name].dtype == "float64" for name in ("PC1", "PC2", "PC3"))


def test_feature_loadings_follow_the_fitted_component_count():
    # Fewer complete rows than features yields fewer components than features.
    frame = pd.DataFrame({"a": [1.0, 2.0], "b": [3.0, 1.0], "c": [0.5, 4.0]})
    result = analyze_pca(frame, ("a", "b", "c"))
    assert result.error is None
    snapshot = PCAExportSnapshot(result, CHART_LABELS)

    table = feature_loadings_table(snapshot)

    assert table.columns.tolist() == ["feature", *(component_name(index) for index in range(len(result.loadings[0])))]
    assert len(table) == 3


def test_explained_variance_matches_the_scree_plot_values():
    snapshot = pca_snapshot()
    result = snapshot.result

    table = explained_variance_table(snapshot)

    assert table.columns.tolist() == ["component", "variance", "share", "cumulative_share"]
    assert table["component"].tolist() == ["PC1", "PC2", "PC3"]
    assert table["variance"].tolist() == pytest.approx(list(result.explained_variance))
    assert table["share"].tolist() == pytest.approx(list(result.explained_variance_ratio))
    assert table["cumulative_share"].tolist() == pytest.approx(list(result.cumulative_variance_ratio))
    assert table["cumulative_share"].iloc[-1] == pytest.approx(1.0)
    assert isinstance(table["component"].dtype, pd.StringDtype)
    assert all(table[name].dtype == "float64" for name in ("variance", "share", "cumulative_share"))


def test_model_summary_lists_feature_and_row_counts_with_notes():
    table = pca_model_summary_table(pca_snapshot())

    assert table.columns.tolist() == ["metric", "value", "notes"]
    assert table["metric"].tolist() == [
        PCAMetric.FEATURES,
        PCAMetric.TOTAL_ROWS,
        PCAMetric.ROWS_USED,
        PCAMetric.ROWS_DROPPED,
    ]
    assert table["value"].tolist() == [3.0, 8.0, 7.0, 1.0]
    assert table["notes"].tolist()[: len(NOTES)] == list(NOTES)
    assert table["notes"].iloc[len(NOTES) :].isna().all()
    assert isinstance(table["metric"].dtype, pd.StringDtype)
    assert isinstance(table["notes"].dtype, pd.StringDtype)
    assert table["value"].dtype == "float64"


def test_more_notes_than_metrics_extend_the_table():
    notes = tuple(f"Line {index}" for index in range(6))

    table = pca_model_summary_table(pca_snapshot(notes=notes))

    assert len(table) == 6
    assert table["notes"].tolist() == list(notes)
    assert table["metric"].iloc[4:].isna().all()
    assert table["value"].iloc[4:].isna().all()
