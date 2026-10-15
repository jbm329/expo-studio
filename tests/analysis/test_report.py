from __future__ import annotations

from dataclasses import replace
from enum import StrEnum

import pandas as pd
import pytest

from expo_jbm329.services.analysis.categories import AnalysisCategory
from expo_jbm329.services.analysis.chi_square import analyze_chi_square
from expo_jbm329.services.analysis.clustering import ClusteringMethod
from expo_jbm329.services.analysis.correlation import CorrelationMethod, analyze_correlation_matrix
from expo_jbm329.services.analysis.correlation_export import CorrelationExportSnapshot
from expo_jbm329.services.analysis.group_comparison import analyze_group_comparison
from expo_jbm329.services.analysis.hypothesis_export import HypothesisExportSnapshot
from expo_jbm329.services.analysis.multivariate_outliers import MultivariateOutlierMethod
from expo_jbm329.services.analysis.outliers import OutlierMethod
from expo_jbm329.services.analysis.outliers_export import (
    MultivariateOutlierExportSnapshot,
    UnivariateOutlierExportSnapshot,
)
from expo_jbm329.services.analysis.overview import analyze_dataset_overview
from expo_jbm329.services.analysis.paired_comparison import analyze_paired_comparison
from expo_jbm329.services.analysis.pca import analyze_pca
from expo_jbm329.services.analysis.pca_export import PCAExportSnapshot
from expo_jbm329.services.analysis.presentation import build_analysis_presentation
from expo_jbm329.services.analysis.regression_export import RegressionExportSnapshot
from expo_jbm329.services.analysis.regression_glm import RegressionModel
from expo_jbm329.services.analysis.report import (
    ReportComponent,
    ReportDocument,
    ReportEntry,
    _json_value,
    available_report_components,
    correlation_report_configuration,
    create_report_entry,
    outlier_report_configuration,
    report_entry_identity,
)
from expo_jbm329.services.analysis.statistics import analyze_descriptive_statistics
from expo_jbm329.services.analysis.timeseries import DecompositionModel, analyze_time_series
from expo_jbm329.services.analysis.timeseries_export import (
    TimeSeriesAppliedConfiguration,
    TimeSeriesExportSnapshot,
)
from expo_jbm329.utils.dataset_ref import DatasetRef
from tests.analysis.test_clustering_export import clustering_snapshot
from tests.analysis.test_correlation_export import _snapshot as correlation_snapshot
from tests.analysis.test_hypothesis_export import chi_snapshot, group_snapshot, paired_snapshot
from tests.analysis.test_outliers_export import (
    multivariate_snapshot,
    univariate_snapshot,
)
from tests.analysis.test_pca_export import CHART_LABELS, pca_frame, pca_snapshot
from tests.analysis.test_regression_export import (
    cox_snapshot,
    linear_snapshot,
    logistic_snapshot,
    negative_binomial_snapshot,
    poisson_snapshot,
)
from tests.analysis.test_timeseries_export import (
    CHART_LABELS as TIME_SERIES_CHART_LABELS,
)
from tests.analysis.test_timeseries_export import (
    daily_frame,
    irregular_snapshot,
    time_series_snapshot,
)

DATASET = DatasetRef("tab-1", "Employees", 100, 4)


def test_report_components_validate_keys_and_kinds():
    with pytest.raises(ValueError, match="key, label"):
        ReportComponent("", "Table", "table")
    with pytest.raises(ValueError, match="supported kind"):
        ReportComponent("table", "Table", "image")


@pytest.mark.parametrize("method", list(ClusteringMethod))
def test_clustering_identity_normalizes_inactive_parameters_and_preserves_active_configuration(method):
    snapshot = clustering_snapshot(method)
    identity = report_entry_identity(AnalysisCategory.CLUSTERING, DATASET.tab_id, snapshot)
    inactive = (
        {"cluster_count": snapshot.result.cluster_count + 1}
        if method is ClusteringMethod.DBSCAN
        else {"dbscan_epsilon": 99.0, "dbscan_min_samples": 99}
    )
    changed = replace(snapshot, result=replace(snapshot.result, **inactive))
    assert report_entry_identity(AnalysisCategory.CLUSTERING, DATASET.tab_id, changed) == identity
    active_changes = [
        {"columns": tuple(reversed(snapshot.result.columns))},
        {"standardize": not snapshot.result.standardize},
        {"method": ClusteringMethod.K_MEANS if method is not ClusteringMethod.K_MEANS else ClusteringMethod.DBSCAN},
    ]
    if method is ClusteringMethod.DBSCAN:
        active_changes.extend(({"dbscan_epsilon": 1.5}, {"dbscan_min_samples": 99}))
    else:
        active_changes.append({"cluster_count": snapshot.result.cluster_count + 1})
    for changes in active_changes:
        configured = replace(snapshot, result=replace(snapshot.result, **changes))
        assert report_entry_identity(AnalysisCategory.CLUSTERING, DATASET.tab_id, configured) != identity


def test_clustering_report_entry_owns_stable_capture_provenance():
    snapshot = clustering_snapshot()
    entry = create_report_entry(AnalysisCategory.CLUSTERING, DATASET, snapshot)
    inspected = create_report_entry(AnalysisCategory.CLUSTERING, DATASET, snapshot)
    assert entry.capture_id == inspected.capture_id == snapshot.capture_id
    assert entry.with_selection(("charts",), "Keep").capture_id == entry.capture_id
    with pytest.raises(ValueError, match="capture identifier"):
        replace(entry, capture_id="wrong")
    rerun = create_report_entry(AnalysisCategory.CLUSTERING, DATASET, clustering_snapshot())
    assert rerun.entry_id == entry.entry_id
    assert rerun.capture_id != entry.capture_id


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
        "capture_id": entry.capture_id,
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


def test_correlation_report_slot_uses_dataset_and_method_but_not_columns():
    first = correlation_snapshot()
    reordered_columns = tuple(reversed(first.matrix.columns[:3]))
    reordered_data = first.matrix_data.loc[:, list(reordered_columns)].copy(deep=True)
    reordered_matrix = analyze_correlation_matrix(reordered_data, reordered_columns, first.matrix.method)
    assert reordered_matrix is not None
    reordered = CorrelationExportSnapshot(reordered_matrix, reordered_data)
    another_method_matrix = analyze_correlation_matrix(
        first.matrix_data,
        first.matrix.columns,
        CorrelationMethod.SPEARMAN,
    )
    assert another_method_matrix is not None
    another_method = CorrelationExportSnapshot(another_method_matrix, first.matrix_data.copy(deep=True))

    assert report_entry_identity(AnalysisCategory.CORRELATION, "tab-1", first) == report_entry_identity(
        AnalysisCategory.CORRELATION, "tab-1", reordered
    )
    assert report_entry_identity(AnalysisCategory.CORRELATION, "tab-1", first) != report_entry_identity(
        AnalysisCategory.CORRELATION, "tab-1", another_method
    )
    assert report_entry_identity(AnalysisCategory.CORRELATION, "tab-1", first) != report_entry_identity(
        AnalysisCategory.CORRELATION, "tab-2", first
    )
    assert correlation_report_configuration(create_report_entry(AnalysisCategory.CORRELATION, DATASET, reordered)) == (
        first.matrix.method.value,
        reordered_columns,
    )


def test_correlation_capture_identity_is_stable_for_candidate_inspection_and_changes_on_rerun():
    snapshot = correlation_snapshot()
    first = create_report_entry(AnalysisCategory.CORRELATION, DATASET, snapshot)
    inspected_again = create_report_entry(AnalysisCategory.CORRELATION, DATASET, snapshot)
    rerun_snapshot = CorrelationExportSnapshot(snapshot.matrix, snapshot.matrix_data.copy(deep=True))
    rerun = create_report_entry(AnalysisCategory.CORRELATION, DATASET, rerun_snapshot)

    assert first.capture_id == snapshot.capture_id
    assert inspected_again.capture_id == first.capture_id
    assert rerun.capture_id == rerun_snapshot.capture_id
    assert rerun.capture_id != first.capture_id
    assert rerun.entry_id == first.entry_id
    assert first.with_selection(first.selected_components, "Saved note").capture_id == first.capture_id


def test_correlation_report_entry_requires_its_snapshot_capture_identifier():
    entry = create_report_entry(AnalysisCategory.CORRELATION, DATASET, correlation_snapshot())

    with pytest.raises(ValueError, match="applied-result capture identifier"):
        replace(entry, capture_id="unrelated-capture")


def test_hypothesis_slots_preserve_family_and_ordered_roles_and_capture_identity():
    group = group_snapshot()
    categorical = chi_snapshot()
    paired = paired_snapshot()
    rerun = group_snapshot()
    group_entry = create_report_entry(AnalysisCategory.HYPOTHESIS_TESTS, DATASET, group)
    alternate_group_result = analyze_group_comparison(
        pd.DataFrame({
            "Other value": [1.0, 2.0, 3.0, 4.0],
            "Other group": ["A", "A", "B", "B"],
        }),
        "Other value",
        "Other group",
    )
    alternate_group = HypothesisExportSnapshot(
        group.test,
        alternate_group_result,
        ("Other value", "Other group"),
    )
    paired_data = pd.DataFrame({"first": range(8), "second": range(1, 9), "third": range(2, 10)})
    paired_columns = ("first", "second", "third")
    reversed_paired_columns = tuple(reversed(paired_columns))
    reversed_paired = HypothesisExportSnapshot(
        paired.test,
        analyze_paired_comparison(paired_data, reversed_paired_columns),
        reversed_paired_columns,
    )
    categorical_data = pd.DataFrame({
        "row": ["A", "A", "B", "B"],
        "column": ["X", "Y", "X", "Y"],
    })
    reversed_categorical = HypothesisExportSnapshot(
        categorical.test,
        analyze_chi_square(categorical_data, "column", "row"),
        ("column", "row"),
    )

    assert group_entry.capture_id == group.capture_id
    assert group_entry.entry_id == report_entry_identity(AnalysisCategory.HYPOTHESIS_TESTS, DATASET.tab_id, group)
    assert group_entry.entry_id == create_report_entry(AnalysisCategory.HYPOTHESIS_TESTS, DATASET, group).entry_id
    assert group_entry.capture_id == create_report_entry(AnalysisCategory.HYPOTHESIS_TESTS, DATASET, group).capture_id
    assert group_entry.entry_id != create_report_entry(AnalysisCategory.HYPOTHESIS_TESTS, DATASET, categorical).entry_id
    assert group_entry.entry_id != create_report_entry(AnalysisCategory.HYPOTHESIS_TESTS, DATASET, paired).entry_id
    assert group_entry.entry_id != report_entry_identity(
        AnalysisCategory.HYPOTHESIS_TESTS, DATASET.tab_id, alternate_group
    )
    assert report_entry_identity(
        AnalysisCategory.HYPOTHESIS_TESTS, DATASET.tab_id, categorical
    ) != report_entry_identity(AnalysisCategory.HYPOTHESIS_TESTS, DATASET.tab_id, reversed_categorical)
    assert report_entry_identity(AnalysisCategory.HYPOTHESIS_TESTS, DATASET.tab_id, paired) != report_entry_identity(
        AnalysisCategory.HYPOTHESIS_TESTS, DATASET.tab_id, reversed_paired
    )

    rerun_entry = create_report_entry(AnalysisCategory.HYPOTHESIS_TESTS, DATASET, rerun)
    assert rerun_entry.entry_id == group_entry.entry_id
    assert rerun_entry.capture_id != group_entry.capture_id
    assert group_entry.with_selection(group_entry.selected_components, "reviewed").capture_id == group_entry.capture_id


def test_hypothesis_report_entry_requires_its_snapshot_capture_identifier():
    entry = create_report_entry(AnalysisCategory.HYPOTHESIS_TESTS, DATASET, group_snapshot())

    with pytest.raises(ValueError, match="hypothesis report entry requires"):
        replace(entry, capture_id=None)


def test_regression_identity_retains_model_roles_predictor_order_terms_and_reference_coding():
    snapshot = linear_snapshot()
    result = snapshot.result
    same_configuration = linear_snapshot()
    changed_outcome = RegressionExportSnapshot(replace(result, target="other outcome"), snapshot.chart_labels)
    changed_predictors = RegressionExportSnapshot(
        replace(result, predictors=tuple(reversed(result.predictors))),
        snapshot.chart_labels,
    )
    changed_terms = RegressionExportSnapshot(
        replace(result, terms=(replace(result.terms[0], column="different"), *result.terms[1:])),
        snapshot.chart_labels,
    )
    changed_references = RegressionExportSnapshot(
        replace(
            result,
            references=(replace(result.references[0], reference_level="different"), *result.references[1:]),
        ),
        snapshot.chart_labels,
    )

    identity = report_entry_identity(AnalysisCategory.REGRESSION, DATASET.tab_id, snapshot)
    assert identity == report_entry_identity(AnalysisCategory.REGRESSION, DATASET.tab_id, same_configuration)
    for variant in (changed_outcome, changed_predictors, changed_terms, changed_references):
        assert identity != report_entry_identity(AnalysisCategory.REGRESSION, DATASET.tab_id, variant)


def test_regression_report_slots_coexist_for_each_model_family_and_different_outcomes():
    snapshots = (
        linear_snapshot(),
        logistic_snapshot(),
        poisson_snapshot(),
        negative_binomial_snapshot(),
        cox_snapshot(),
    )
    entries = tuple(create_report_entry(AnalysisCategory.REGRESSION, DATASET, snapshot) for snapshot in snapshots)
    document = ReportDocument()

    for entry in entries:
        document.upsert(entry)

    assert len(document.entries) == len(RegressionModel)
    assert len({entry.entry_id for entry in document.entries}) == len(RegressionModel)
    assert tuple(entry.snapshot.model for entry in document.entries) == tuple(RegressionModel)


def test_regression_capture_identity_is_stable_during_inspection_and_changes_on_rerun():
    snapshot = linear_snapshot()
    entry = create_report_entry(AnalysisCategory.REGRESSION, DATASET, snapshot)
    inspected_again = create_report_entry(AnalysisCategory.REGRESSION, DATASET, snapshot)
    rerun = linear_snapshot()
    rerun_entry = create_report_entry(AnalysisCategory.REGRESSION, DATASET, rerun)

    assert entry.capture_id == snapshot.capture_id
    assert inspected_again.capture_id == entry.capture_id
    assert rerun_entry.entry_id == entry.entry_id
    assert rerun_entry.capture_id == rerun.capture_id != entry.capture_id
    assert entry.with_selection(("coefficients",), "Reviewed").capture_id == entry.capture_id


def test_regression_report_entry_requires_its_snapshot_capture_identifier():
    entry = create_report_entry(AnalysisCategory.REGRESSION, DATASET, linear_snapshot())

    with pytest.raises(ValueError, match="regression report entry requires"):
        replace(entry, capture_id="unrelated-capture")


def test_correlation_report_upsert_preserves_position_note_and_valid_component_selection():
    first_snapshot = correlation_snapshot()
    first = create_report_entry(AnalysisCategory.CORRELATION, DATASET, first_snapshot).with_selection(
        ("strongest_correlations", "matrix_plot"),
        "Keep this note",
    )
    other = create_report_entry(AnalysisCategory.PCA, DATASET, pca_snapshot())
    rerun_snapshot = CorrelationExportSnapshot(first_snapshot.matrix, first_snapshot.matrix_data.copy(deep=True))
    incoming = create_report_entry(AnalysisCategory.CORRELATION, DATASET, rerun_snapshot).with_selection(
        first.selected_components,
        first.note,
    )
    document = ReportDocument()
    document.upsert(first)
    document.upsert(other)

    document.upsert(incoming)

    assert document.entries == (incoming, other)
    assert document.entries[0].note == "Keep this note"
    assert document.entries[0].selected_components == ("strongest_correlations", "matrix_plot")
    assert document.entries[0].snapshot is rerun_snapshot


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


def test_pca_report_slot_preserves_feature_order_standardization_and_capture_provenance():
    def fit(columns: tuple[str, ...], standardize: bool) -> PCAExportSnapshot:
        return PCAExportSnapshot(analyze_pca(pca_frame(), columns, standardize=standardize), CHART_LABELS)

    initial = fit(("x", "y", "z"), True)
    same_slot = fit(("x", "y", "z"), True)
    reordered = fit(("z", "y", "x"), True)
    different_features = fit(("x", "y"), True)
    different_standardization = fit(("x", "y", "z"), False)
    identity = report_entry_identity(AnalysisCategory.PCA, DATASET.tab_id, initial)
    entry = create_report_entry(AnalysisCategory.PCA, DATASET, initial)
    inspected = create_report_entry(AnalysisCategory.PCA, DATASET, initial)
    rerun = create_report_entry(AnalysisCategory.PCA, DATASET, same_slot)

    assert identity == report_entry_identity(AnalysisCategory.PCA, DATASET.tab_id, same_slot)
    assert identity != report_entry_identity(AnalysisCategory.PCA, DATASET.tab_id, reordered)
    assert identity != report_entry_identity(AnalysisCategory.PCA, DATASET.tab_id, different_features)
    assert identity != report_entry_identity(AnalysisCategory.PCA, DATASET.tab_id, different_standardization)
    assert entry.capture_id == inspected.capture_id == initial.capture_id
    assert rerun.capture_id == same_slot.capture_id != entry.capture_id
    assert rerun.entry_id == entry.entry_id
    assert entry.with_selection(("feature_loadings",), "Keep note").capture_id == entry.capture_id
    with pytest.raises(ValueError, match="PCA report entry requires its applied-result capture identifier"):
        replace(entry, capture_id="different-capture")


def test_time_series_report_omits_unavailable_autocorrelation():
    components = available_report_components(AnalysisCategory.TIME_SERIES, irregular_snapshot())

    assert [component.key for component in components] == ["series", "model_summary", "charts"]


def test_time_series_report_identity_distinguishes_every_applied_setting_and_auto_period_intent():
    frame = daily_frame().dropna(subset=["day"]).copy()
    frame["other_day"] = frame["day"] + pd.Timedelta(days=30)
    frame["other_value"] = frame["sales"] + 2

    def snapshot(
        time_column: str = "day",
        value_column: str = "sales",
        frequency: str | None = None,
        period: int | None = None,
        model: DecompositionModel = DecompositionModel.ADDITIVE,
    ) -> TimeSeriesExportSnapshot:
        result = analyze_time_series(
            frame,
            time_column,
            value_column,
            resample_frequency=frequency,
            seasonal_period=period,
            decomposition_model=model,
        )
        assert result.error is None
        return TimeSeriesExportSnapshot(
            result,
            TIME_SERIES_CHART_LABELS,
            applied_configuration=TimeSeriesAppliedConfiguration(
                time_column,
                value_column,
                frequency,
                period,
                model,
            ),
        )

    automatic = snapshot()
    configurations = (
        automatic,
        snapshot(time_column="other_day"),
        snapshot(value_column="other_value"),
        snapshot(frequency="D"),
        snapshot(period=7),
        snapshot(model=DecompositionModel.MULTIPLICATIVE),
    )
    identities = {
        report_entry_identity(AnalysisCategory.TIME_SERIES, DATASET.tab_id, configured) for configured in configurations
    }

    assert len(identities) == len(configurations)
    assert automatic.result.seasonal_period == 7
    assert automatic.applied_configuration is not None
    assert automatic.applied_configuration.seasonal_period is None
    assert snapshot(period=7).result.seasonal_period == 7
    automatic_summary = build_analysis_presentation(
        AnalysisCategory.TIME_SERIES, automatic, lambda _context, source: source
    )
    assert automatic_summary.title == "Time Series"
    assert automatic_summary.summary_lines[2] == "Resampling: Original frequency"
    assert automatic_summary.summary_lines[3] == "Seasonal period: Automatic (detected: 7)"
    assert (
        build_analysis_presentation(
            AnalysisCategory.TIME_SERIES, configurations[4], lambda _context, source: source
        ).summary_lines[3]
        == "Seasonal period: 7"
    )
    assert (
        build_analysis_presentation(
            AnalysisCategory.TIME_SERIES, configurations[3], lambda _context, source: source
        ).summary_lines[2]
        == "Resampling: Daily"
    )
    assert (
        build_analysis_presentation(
            AnalysisCategory.TIME_SERIES, configurations[5], lambda _context, source: source
        ).summary_lines[-1]
        == "Decomposition model: Multiplicative"
    )


def test_time_series_report_entry_keeps_same_slot_capture_and_validates_provenance():
    snapshot = time_series_snapshot()
    entry = create_report_entry(AnalysisCategory.TIME_SERIES, DATASET, snapshot)
    inspected = create_report_entry(AnalysisCategory.TIME_SERIES, DATASET, snapshot)
    rerun = create_report_entry(AnalysisCategory.TIME_SERIES, DATASET, time_series_snapshot())

    assert entry.entry_id == rerun.entry_id
    assert entry.capture_id == inspected.capture_id == snapshot.capture_id
    assert rerun.capture_id != entry.capture_id
    assert entry.with_selection(("series",), "Keep this note").capture_id == entry.capture_id
    with pytest.raises(ValueError, match="Time Series report entry requires its applied-result capture identifier"):
        replace(entry, capture_id="another-capture")


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


def test_outlier_component_labels_are_shared_and_descriptive():
    univariate = available_report_components(AnalysisCategory.OUTLIERS, univariate_snapshot())
    multivariate = available_report_components(AnalysisCategory.OUTLIERS, multivariate_snapshot())

    assert [component.label for component in univariate] == [
        "Column summary",
        "Model summary",
        "Potential outliers",
        "Column distributions",
    ]
    assert [component.label for component in multivariate] == [
        "Model summary",
        "Potential outliers",
        "Outlier projection",
    ]


def test_univariate_report_slot_uses_screened_columns_not_the_detail_selection():
    initial = univariate_snapshot(column="a")
    another_detail = initial.with_detail(univariate_snapshot(column="b").detail, ())
    changed_method = univariate_snapshot(OutlierMethod.Z_SCORE)
    changed_threshold_summary = replace(initial.summary, threshold=2.0)
    changed_threshold = UnivariateOutlierExportSnapshot(
        changed_threshold_summary,
        initial.data,
        initial.chart_labels,
        detail=None,
    )
    reduced_columns = ("a", "b")
    reduced_summary = replace(
        initial.summary,
        available_columns=reduced_columns,
        columns=tuple(item for item in initial.summary.columns if item.column in reduced_columns),
    )
    reduced_screen = UnivariateOutlierExportSnapshot(
        reduced_summary,
        initial.data.loc[:, list(reduced_columns)].copy(),
        initial.chart_labels,
    )

    identity = report_entry_identity(AnalysisCategory.OUTLIERS, DATASET.tab_id, initial)
    assert report_entry_identity(AnalysisCategory.OUTLIERS, DATASET.tab_id, another_detail) == identity
    assert report_entry_identity(AnalysisCategory.OUTLIERS, DATASET.tab_id, changed_method) != identity
    assert report_entry_identity(AnalysisCategory.OUTLIERS, DATASET.tab_id, changed_threshold) != identity
    assert report_entry_identity(AnalysisCategory.OUTLIERS, DATASET.tab_id, reduced_screen) != identity
    assert outlier_report_configuration(create_report_entry(AnalysisCategory.OUTLIERS, DATASET, initial)) != (
        outlier_report_configuration(create_report_entry(AnalysisCategory.OUTLIERS, DATASET, another_detail))
    )


@pytest.mark.parametrize(
    ("change", "is_same_slot"),
    [
        ({"method": MultivariateOutlierMethod.LOCAL_OUTLIER_FACTOR}, False),
        ({"columns": ("y", "x")}, False),
        ({"standardize": False}, False),
        ({"contamination": 0.1}, False),
        ({"lof_neighbors": 5}, True),
    ],
)
def test_multivariate_report_slot_tracks_applied_settings_and_ignores_inactive_lof_neighbors(change, is_same_slot):
    initial = multivariate_snapshot()
    result = replace(initial.result, **change)
    candidate = MultivariateOutlierExportSnapshot(result, initial.chart_labels, initial.notes)

    assert (
        report_entry_identity(AnalysisCategory.OUTLIERS, DATASET.tab_id, candidate)
        == report_entry_identity(AnalysisCategory.OUTLIERS, DATASET.tab_id, initial)
    ) is is_same_slot


def test_multivariate_lof_neighbor_setting_is_part_of_report_slot_identity():
    initial = multivariate_snapshot(MultivariateOutlierMethod.LOCAL_OUTLIER_FACTOR)
    changed_neighbors = MultivariateOutlierExportSnapshot(
        replace(initial.result, lof_neighbors=3),
        initial.chart_labels,
        initial.notes,
    )

    assert report_entry_identity(AnalysisCategory.OUTLIERS, DATASET.tab_id, changed_neighbors) != report_entry_identity(
        AnalysisCategory.OUTLIERS, DATASET.tab_id, initial
    )


def test_outlier_report_entry_uses_snapshot_capture_id_and_validates_it():
    snapshot = univariate_snapshot()
    entry = create_report_entry(AnalysisCategory.OUTLIERS, DATASET, snapshot)

    assert entry.capture_id == snapshot.capture_id
    assert entry.with_selection(entry.selected_components, "saved note").capture_id == snapshot.capture_id
    with pytest.raises(ValueError, match="applied-result capture identifier"):
        replace(entry, capture_id="different-capture")


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
