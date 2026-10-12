from __future__ import annotations

from enum import StrEnum

import pandas as pd
import pytest

from expo_jbm329.services.analysis.categories import AnalysisCategory
from expo_jbm329.services.analysis.overview import analyze_dataset_overview
from expo_jbm329.services.analysis.report import (
    ReportComponent,
    ReportDocument,
    ReportEntry,
    _json_value,
    available_report_components,
    create_report_entry,
    report_entry_identity,
)
from expo_jbm329.services.analysis.statistics import analyze_descriptive_statistics
from expo_jbm329.utils.dataset_ref import DatasetRef
from tests.analysis.test_clustering_export import clustering_snapshot
from tests.analysis.test_correlation_export import _snapshot as correlation_snapshot
from tests.analysis.test_hypothesis_export import group_snapshot
from tests.analysis.test_outliers_export import multivariate_snapshot, univariate_snapshot
from tests.analysis.test_pca_export import pca_snapshot
from tests.analysis.test_regression_export import linear_snapshot
from tests.analysis.test_timeseries_export import irregular_snapshot, time_series_snapshot

DATASET = DatasetRef("tab-1", "Employees", 100, 4)


def test_report_components_validate_keys_and_kinds():
    with pytest.raises(ValueError, match="key, label"):
        ReportComponent("", "Table", "table")
    with pytest.raises(ValueError, match="supported kind"):
        ReportComponent("table", "Table", "image")


def test_report_entry_requires_nonempty_unique_component_selection():
    entry = create_report_entry(AnalysisCategory.PCA, DATASET, pca_snapshot())

    with pytest.raises(ValueError, match="at least one"):
        entry.with_selection((), "")
    with pytest.raises(ValueError, match="at least one"):
        entry.with_selection(("unknown",), "")


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"entry_id": ""}, "dataset identity"),
        ({"dataset_rows": -1}, "dimensions"),
        ({"dataset_columns": -1}, "dimensions"),
        (
            {"components": (ReportComponent("same", "First", "table"), ReportComponent("same", "Second", "chart"))},
            "distinct keys",
        ),
        ({"selected_components": ("feature_loadings", "feature_loadings")}, "at least one"),
    ],
)
def test_report_entry_rejects_invalid_identity_dimensions_and_components(changes, message):
    entry = create_report_entry(AnalysisCategory.PCA, DATASET, pca_snapshot())
    values = {
        "entry_id": entry.entry_id,
        "dataset_id": entry.dataset_id,
        "dataset_name": entry.dataset_name,
        "dataset_rows": entry.dataset_rows,
        "dataset_columns": entry.dataset_columns,
        "category": entry.category,
        "analysis_date": entry.analysis_date,
        "app_version": entry.app_version,
        "snapshot": entry.snapshot,
        "components": entry.components,
        "selected_components": entry.selected_components,
        "note": entry.note,
    }
    values.update(changes)
    with pytest.raises(ValueError, match=message):
        ReportEntry(**values)


def test_report_entry_captures_metadata_and_defaults_all_components():
    snapshot = pca_snapshot()

    entry = create_report_entry(AnalysisCategory.PCA, DATASET, snapshot)

    assert entry.dataset_id == DATASET.tab_id
    assert entry.dataset_name == DATASET.title
    assert (entry.dataset_rows, entry.dataset_columns) == (100, 4)
    assert entry.analysis_date
    assert entry.app_version
    assert entry.snapshot is snapshot
    assert entry.selected_components == tuple(component.key for component in entry.components)
    assert {component.kind for component in entry.components} == {"table", "chart"}


def test_report_entry_identity_uses_dataset_category_and_applied_configuration():
    snapshot = pca_snapshot()

    identity = report_entry_identity(AnalysisCategory.PCA, "tab-1", snapshot)

    assert identity == report_entry_identity(AnalysisCategory.PCA, "tab-1", pca_snapshot())
    assert identity != report_entry_identity(AnalysisCategory.PCA, "tab-2", snapshot)
    assert identity != report_entry_identity(AnalysisCategory.CLUSTERING, "tab-1", clustering_snapshot())


def test_report_document_upserts_moves_and_removes_without_duplicates():
    snapshot = pca_snapshot()
    entry = create_report_entry(AnalysisCategory.PCA, DATASET, snapshot)
    other = create_report_entry(AnalysisCategory.REGRESSION, DATASET, linear_snapshot())
    document = ReportDocument()

    document.upsert(entry)
    document.upsert(entry.with_selection((entry.components[0].key,), "Updated note"))
    document.upsert(other)

    assert len(document.entries) == 2
    assert document.get(entry.entry_id).note == "Updated note"
    assert document.move(other.entry_id, -1)
    assert document.entries[0].entry_id == other.entry_id
    assert not document.move(other.entry_id, -1)
    assert not document.move("missing", 1)
    assert not document.move(other.entry_id, 0)
    assert not document.move(other.entry_id, 2)
    assert document.remove(entry.entry_id)
    assert not document.remove(entry.entry_id)


def test_overview_report_offers_nonempty_tables_only():
    result = analyze_dataset_overview(pd.DataFrame({"value": [1, 2, 3]}))

    components = available_report_components(AnalysisCategory.OVERVIEW, result)

    assert [component.key for component in components] == ["Summary", "Columns", "Sample"]
    assert all(component.kind == "table" for component in components)


def test_overview_report_omits_empty_columns_and_sample_tables():
    result = analyze_dataset_overview(pd.DataFrame())

    assert [component.key for component in available_report_components(AnalysisCategory.OVERVIEW, result)] == [
        "Summary"
    ]


def test_statistics_report_offers_available_tables_and_charts():
    result = analyze_descriptive_statistics(pd.DataFrame({"number": [1.0, 2.0, 3.0], "group": ["a", "a", "b"]}))

    components = available_report_components(AnalysisCategory.STATISTICS, result)

    assert [component.key for component in components] == ["Continuous", "Charts", "Categorical"]


@pytest.mark.parametrize(
    ("category", "snapshot", "expected"),
    [
        (
            AnalysisCategory.HYPOTHESIS_TESTS,
            group_snapshot(),
            ["summary", "test_results", "charts"],
        ),
        (
            AnalysisCategory.CORRELATION,
            correlation_snapshot(),
            ["strongest_correlations", "matrix_plot", "scatterplots"],
        ),
        (
            AnalysisCategory.REGRESSION,
            linear_snapshot(),
            ["coefficients", "model_metrics", "charts"],
        ),
        (
            AnalysisCategory.CLUSTERING,
            clustering_snapshot(),
            ["cluster_sizes", "model_summary", "charts"],
        ),
        (
            AnalysisCategory.PCA,
            pca_snapshot(),
            ["feature_loadings", "explained_variance", "model_summary", "charts"],
        ),
        (
            AnalysisCategory.TIME_SERIES,
            time_series_snapshot(),
            ["series", "autocorrelation", "model_summary", "charts"],
        ),
    ],
)
def test_report_offers_expected_components(category, snapshot, expected):
    components = available_report_components(category, snapshot)

    assert [component.key for component in components] == expected


@pytest.mark.parametrize(
    ("category", "snapshot"),
    [
        (AnalysisCategory.OVERVIEW, analyze_dataset_overview(pd.DataFrame({"value": [1, 2, 3]}))),
        (AnalysisCategory.STATISTICS, analyze_descriptive_statistics(pd.DataFrame({"value": [1, 2, 3]}))),
        (AnalysisCategory.HYPOTHESIS_TESTS, group_snapshot()),
        (AnalysisCategory.CORRELATION, correlation_snapshot()),
        (AnalysisCategory.REGRESSION, linear_snapshot()),
        (AnalysisCategory.OUTLIERS, univariate_snapshot()),
        (AnalysisCategory.OUTLIERS, multivariate_snapshot()),
        (AnalysisCategory.CLUSTERING, clustering_snapshot()),
        (AnalysisCategory.PCA, pca_snapshot()),
        (AnalysisCategory.TIME_SERIES, time_series_snapshot()),
    ],
)
def test_report_identity_is_deterministic_for_each_analysis(category, snapshot):
    first = report_entry_identity(category, DATASET.tab_id, snapshot)

    assert first == report_entry_identity(category, DATASET.tab_id, snapshot)
    assert first != report_entry_identity(category, "another-dataset", snapshot)


def test_time_series_report_omits_unavailable_autocorrelation():
    components = available_report_components(AnalysisCategory.TIME_SERIES, irregular_snapshot())

    assert [component.key for component in components] == ["series", "model_summary", "charts"]


@pytest.mark.parametrize(
    ("snapshot", "expected"),
    [
        (
            univariate_snapshot(),
            ["column_summary", "column_details", "potential_outliers", "charts"],
        ),
        (
            multivariate_snapshot(),
            ["model_summary", "potential_outliers", "charts"],
        ),
    ],
)
def test_outlier_report_offers_only_displayed_components(snapshot, expected):
    assert [component.key for component in available_report_components(AnalysisCategory.OUTLIERS, snapshot)] == expected


def test_report_component_request_rejects_category_snapshot_mismatch():
    with pytest.raises(TypeError, match="do not match"):
        available_report_components(AnalysisCategory.PCA, linear_snapshot())
    with pytest.raises(TypeError, match="do not match"):
        report_entry_identity(AnalysisCategory.PCA, DATASET.tab_id, linear_snapshot())


def test_report_entry_snapshot_is_an_owned_applied_result():
    snapshot = pca_snapshot()
    entry = create_report_entry(AnalysisCategory.PCA, DATASET, snapshot)

    updated_entry = entry.with_selection(entry.selected_components, "Report note")

    assert updated_entry.snapshot is snapshot
    assert updated_entry.note == "Report note"


def test_configuration_json_normalizes_nested_values():
    class ExampleEnum(StrEnum):
        VALUE = "value"

    assert _json_value((ExampleEnum.VALUE, ["text", 1, None])) == ["value", ["text", 1, None]]
    assert _json_value({"unexpected": "value"}) == "{'unexpected': 'value'}"
