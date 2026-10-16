from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from html import escape
from typing import TYPE_CHECKING
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from expo_jbm329.services.analysis.categories import AnalysisCategory, HypothesisTest
from expo_jbm329.services.analysis.clustering import ClusteringMethod
from expo_jbm329.services.analysis.clustering_export import (
    ClusteringExportComponent,
    clustering_export_tables,
)
from expo_jbm329.services.analysis.correlation import CorrelationMethod, analyze_correlation_matrix
from expo_jbm329.services.analysis.correlation_export import CorrelationExportComponent, CorrelationExportSnapshot
from expo_jbm329.services.analysis.group_comparison import analyze_group_comparison
from expo_jbm329.services.analysis.hypothesis_charts import render_hypothesis_charts
from expo_jbm329.services.analysis.hypothesis_export import (
    HypothesisExportComponent,
    HypothesisExportSnapshot,
    hypothesis_export_tables,
)
from expo_jbm329.services.analysis.outliers import (
    OutlierMethod,
    analyze_outlier_column,
    analyze_outlier_summary,
)
from expo_jbm329.services.analysis.outliers_export import (
    UnivariateOutlierExportSnapshot,
    outlier_column_details_table,
    outlier_column_summary_table,
    outlier_model_summary_table,
)
from expo_jbm329.services.analysis.overview import analyze_dataset_overview
from expo_jbm329.services.analysis.pca_export import (
    PCAExportComponent,
    pca_export_tables,
)
from expo_jbm329.services.analysis.presentation import build_analysis_presentation
from expo_jbm329.services.analysis.regression_export import (
    RegressionExportComponent,
    regression_export_tables,
    regression_metrics_table,
)
from expo_jbm329.services.analysis.regression_glm import RegressionModel
from expo_jbm329.services.analysis.report import (
    PreparedOverviewSummary,
    PreparedReportComponent,
    PreparedReportDocument,
    PreparedReportEntry,
    PreparedReportTable,
    ReportComponent,
    ReportDocument,
    _render_entry_charts,
    capture_report_labels,
    create_report_entry,
    localized_report_tables,
    prepare_report_content,
    render_prepared_report_html,
    render_report_html,
)
from expo_jbm329.services.analysis.statistics import analyze_descriptive_statistics
from expo_jbm329.services.analysis.timeseries import DecompositionModel, analyze_time_series
from expo_jbm329.services.analysis.timeseries_export import (
    TimeSeriesAppliedConfiguration,
    TimeSeriesExportComponent,
    TimeSeriesExportSnapshot,
    TimeSeriesMetric,
    time_series_export_tables,
)
from expo_jbm329.services.excel_chart import ExcelChartCancelledError, ExcelChartImage
from expo_jbm329.utils.dataset_ref import DatasetRef
from expo_jbm329.utils.format_utils import fmt_pct
from tests.analysis.test_clustering_export import clustering_snapshot
from tests.analysis.test_correlation_export import _snapshot as correlation_snapshot
from tests.analysis.test_hypothesis_export import chi_snapshot, group_snapshot, paired_snapshot
from tests.analysis.test_outliers_export import (
    HISTOGRAM_LABELS,
    multivariate_snapshot,
    univariate_snapshot,
)
from tests.analysis.test_pca_export import pca_snapshot
from tests.analysis.test_regression_export import (
    cox_snapshot,
    linear_snapshot,
    logistic_snapshot,
    negative_binomial_snapshot,
    poisson_snapshot,
)
from tests.analysis.test_timeseries_export import CHART_LABELS, irregular_snapshot, time_series_snapshot

if TYPE_CHECKING:
    from collections.abc import Callable

DATASET = DatasetRef("report-tab", "Report sample", 40, 4)


def _entry(category: AnalysisCategory, snapshot: object, selection: tuple[str, ...] | None = None):
    entry = create_report_entry(category, DATASET, snapshot)
    if selection is None:
        return entry
    return entry.with_selection(selection, entry.note)


@pytest.mark.parametrize("method", list(ClusteringMethod))
@pytest.mark.parametrize("locale", ["en", "sv"])
def test_clustering_worker_captures_shared_localized_presentation_and_escapes_applied_features(method, locale):
    from pathlib import Path

    from PyQt6.QtCore import QCoreApplication, QTranslator
    from PyQt6.QtWidgets import QApplication

    snapshot = clustering_snapshot(method)
    feature = '<feature & "quoted">' + "very long name " * 30
    snapshot = replace(snapshot, result=replace(snapshot.result, columns=(feature, "second")))
    document = ReportDocument()
    document.upsert(_entry(AnalysisCategory.CLUSTERING, snapshot, ("cluster_sizes", "model_summary")))
    translator = QTranslator()
    catalog = Path(__file__).parents[2] / "src" / "expo_jbm329" / "i18n" / "locales" / f"app_{locale}.qm"
    assert translator.load(str(catalog))
    app = QApplication.instance()
    app.installTranslator(translator)
    try:
        presentation = build_analysis_presentation(AnalysisCategory.CLUSTERING, snapshot, QCoreApplication.translate)
        labels = capture_report_labels(QCoreApplication.translate)
    finally:
        app.removeTranslator(translator)
    prepared = prepare_report_content(document, labels=labels)
    entry = prepared.entries[0]
    assert entry.title == presentation.title
    assert entry.configuration == presentation.configuration
    expected = ("Cluster sizes", "Model summary") if locale == "en" else ("Klusterstorlekar", "Modellsammanfattning")
    assert tuple(component.label for component in entry.components) == expected
    assert tuple(component.tables[0].title for component in entry.components) == expected
    html = render_prepared_report_html(prepared)
    assert escape(feature, quote=True) in html
    assert feature not in html
    assert presentation.title in html
    assert "Clustering —" in html if locale == "en" else "Klustring —" in html


@pytest.mark.parametrize("method", list(ClusteringMethod))
def test_clustering_html_places_ordered_escaped_notes_below_model_summary_without_changing_exports(method):
    notes = ("First <model> & note\ncontinued safely", "Second model note")
    snapshot = replace(clustering_snapshot(method), notes=notes)
    exported_before = clustering_export_tables(
        snapshot,
        (ClusteringExportComponent.MODEL_SUMMARY,),
    )[ClusteringExportComponent.MODEL_SUMMARY]
    localized_export = localized_report_tables(
        AnalysisCategory.CLUSTERING,
        snapshot,
        ("model_summary",),
    )["Model summary"]
    document = ReportDocument()
    document.upsert(_entry(AnalysisCategory.CLUSTERING, snapshot, ("model_summary",)))

    prepared = prepare_report_content(document)
    component = prepared.entries[0].components[0]
    table = component.tables[0]
    html = render_prepared_report_html(prepared)
    exported_after = clustering_export_tables(
        snapshot,
        (ClusteringExportComponent.MODEL_SUMMARY,),
    )[ClusteringExportComponent.MODEL_SUMMARY]
    metric_rows = exported_before.loc[exported_before["metric"].notna()]

    assert table.headers == ("Metric", "Value")
    assert len(table.rows) == len(metric_rows)
    assert tuple(row[0] for row in table.rows) == tuple(localized_export["Metric"].iloc[: len(metric_rows)])
    np.testing.assert_equal(
        tuple(row[1] for row in table.rows),
        tuple(localized_export["Value"].iloc[: len(metric_rows)]),
    )
    assert component.paragraphs == notes
    assert "Notes" not in table.headers
    assert localized_export.columns.tolist() == ["Metric", "Value", "Notes"]
    assert localized_export["Notes"].iloc[: len(notes)].tolist() == list(notes)
    assert localized_export["Notes"].iloc[len(notes) :].isna().all()
    assert exported_before.columns.tolist() == ["metric", "value", "notes"]
    assert exported_before["metric"].dtype == pd.StringDtype()
    assert exported_before["value"].dtype == "float64"
    assert exported_before["notes"].dtype == pd.StringDtype()
    pd.testing.assert_frame_equal(exported_after, exported_before)
    assert html.index("</table></div>") < html.index('<div class="report-paragraphs">')
    assert html.index("First &lt;model&gt; &amp; note") < html.index("Second model note")
    assert "continued safely" in html
    assert "First <model>" not in html
    assert "white-space: pre-wrap" in html


@pytest.mark.parametrize("notes", [(), tuple(f"PCA note {index}" for index in range(8))])
def test_pca_html_separates_notes_from_model_summary_without_changing_exports(notes):
    snapshot = replace(pca_snapshot(), notes=notes)
    raw_before = pca_export_tables(snapshot, (PCAExportComponent.MODEL_SUMMARY,))[PCAExportComponent.MODEL_SUMMARY]
    localized_export = localized_report_tables(
        AnalysisCategory.PCA,
        snapshot,
        ("model_summary",),
    )["Model summary"]
    document = ReportDocument()
    document.upsert(_entry(AnalysisCategory.PCA, snapshot, ("model_summary",)))

    prepared = prepare_report_content(document)
    component = prepared.entries[0].components[0]
    raw_after = pca_export_tables(snapshot, (PCAExportComponent.MODEL_SUMMARY,))[PCAExportComponent.MODEL_SUMMARY]
    metric_rows = raw_before.loc[raw_before["metric"].notna()]

    assert component.tables[0].headers == ("Metric", "Value")
    assert len(component.tables[0].rows) == len(metric_rows)
    assert tuple(row[0] for row in component.tables[0].rows) == tuple(
        localized_export["Metric"].iloc[: len(metric_rows)]
    )
    np.testing.assert_equal(
        tuple(row[1] for row in component.tables[0].rows),
        tuple(localized_export["Value"].iloc[: len(metric_rows)]),
    )
    assert component.paragraphs == notes
    assert localized_export.columns.tolist() == ["Metric", "Value", "Notes"]
    assert localized_export["Notes"].iloc[: len(notes)].tolist() == list(notes)
    assert localized_export["Notes"].iloc[len(notes) :].isna().all()
    assert len(localized_export) == max(len(metric_rows), len(notes))
    assert localized_export["Metric"].iloc[len(metric_rows) :].isna().all()
    assert localized_export["Value"].iloc[len(metric_rows) :].isna().all()
    assert localized_export["Metric"].dtype == object
    assert localized_export["Value"].dtype == "float64"
    assert isinstance(localized_export["Notes"].dtype, pd.StringDtype)
    assert raw_before.columns.tolist() == ["metric", "value", "notes"]
    assert raw_before["metric"].dtype == pd.StringDtype()
    assert raw_before["value"].dtype == "float64"
    assert raw_before["notes"].dtype == pd.StringDtype()
    pd.testing.assert_frame_equal(raw_after, raw_before)


def test_pca_html_places_ordered_escaped_notes_below_model_summary():
    notes = ("First <model> & note\ncontinued safely", "Second model note")
    snapshot = replace(pca_snapshot(), notes=notes)
    document = ReportDocument()
    document.upsert(_entry(AnalysisCategory.PCA, snapshot, ("model_summary",)))

    prepared = prepare_report_content(document)
    component = prepared.entries[0].components[0]
    html = render_prepared_report_html(prepared)

    assert component.paragraphs == notes
    assert "Notes" not in component.tables[0].headers
    assert html.index("</table></div>") < html.index('<div class="report-paragraphs">')
    assert html.index("First &lt;model&gt; &amp; note") < html.index("Second model note")
    assert "continued safely" in html
    assert "First <model>" not in html
    assert "white-space: pre-wrap" in html


def test_pca_html_keeps_real_metric_rows_with_missing_values(monkeypatch):
    from expo_jbm329.services.analysis import report

    snapshot = pca_snapshot(notes=("Captured model note",))
    original_export_tables = report.pca_export_tables

    def export_with_missing_value(snapshot_arg, components):
        tables = original_export_tables(snapshot_arg, components)
        tables[PCAExportComponent.MODEL_SUMMARY].loc[2, "value"] = np.nan
        return tables

    monkeypatch.setattr(report, "pca_export_tables", export_with_missing_value)
    document = ReportDocument()
    document.upsert(_entry(AnalysisCategory.PCA, snapshot, ("model_summary",)))

    component = prepare_report_content(document).entries[0].components[0]
    metric_index = component.tables[0].headers.index("Metric")
    value_index = component.tables[0].headers.index("Value")
    rows_used = next(row for row in component.tables[0].rows if row[metric_index] == "Rows used")

    assert pd.isna(rows_used[value_index])
    assert len(component.tables[0].rows) == 4
    assert component.paragraphs == snapshot.notes


def test_pca_notes_follow_component_selection_without_capturing_entry_notes_or_chart_captions():
    snapshot = replace(pca_snapshot(), notes=("Model-only note",))
    entry = _entry(AnalysisCategory.PCA, snapshot).with_selection(("model_summary", "charts"), "Entry note")
    document = ReportDocument()
    document.upsert(entry)

    components = prepare_report_content(document).entries[0].components

    assert components[0].paragraphs == snapshot.notes
    assert components[1].paragraphs == ()
    assert components[1].charts[1].captions == snapshot.chart_labels.scatter_captions
    assert entry.note == "Entry note"


@pytest.mark.parametrize("method", list(ClusteringMethod))
@pytest.mark.parametrize("notes", [(), tuple(f"Model note {index}" for index in range(20))])
def test_clustering_html_omits_note_only_rows_and_preserves_export_notes(method, notes):
    snapshot = replace(clustering_snapshot(method), notes=notes)
    raw_table = clustering_export_tables(
        snapshot,
        (ClusteringExportComponent.MODEL_SUMMARY,),
    )[ClusteringExportComponent.MODEL_SUMMARY]
    document = ReportDocument()
    document.upsert(_entry(AnalysisCategory.CLUSTERING, snapshot, ("model_summary",)))

    component = prepare_report_content(document).entries[0].components[0]
    localized_export = localized_report_tables(
        AnalysisCategory.CLUSTERING,
        snapshot,
        ("model_summary",),
    )["Model summary"]
    metric_count = raw_table["metric"].notna().sum()

    assert len(component.tables[0].rows) == metric_count
    assert component.paragraphs == notes
    assert "Notes" not in component.tables[0].headers
    assert "Notes" in localized_export.columns
    assert localized_export["Notes"].iloc[: len(notes)].tolist() == list(notes)
    assert len(localized_export) == max(metric_count, len(notes))
    assert localized_export["Metric"].iloc[metric_count:].isna().all()
    assert localized_export["Value"].iloc[metric_count:].isna().all()


def test_clustering_html_keeps_a_real_metric_with_a_missing_value():
    snapshot = clustering_snapshot(
        ClusteringMethod.DBSCAN,
        dbscan_epsilon=100.0,
        dbscan_min_samples=2,
        notes=("Silhouette is undefined for this fit.",),
    )
    document = ReportDocument()
    document.upsert(_entry(AnalysisCategory.CLUSTERING, snapshot, ("model_summary",)))

    component = prepare_report_content(document).entries[0].components[0]
    metric_index = component.tables[0].headers.index("Metric")
    value_index = component.tables[0].headers.index("Value")
    silhouette = next(row for row in component.tables[0].rows if row[metric_index] == "Silhouette score")

    assert pd.isna(silhouette[value_index])
    assert component.paragraphs == snapshot.notes


def test_clustering_notes_are_excluded_when_model_summary_is_not_selected():
    snapshot = replace(clustering_snapshot(), notes=("Model-only note",))
    document = ReportDocument()
    document.upsert(_entry(AnalysisCategory.CLUSTERING, snapshot, ("cluster_sizes",)))

    prepared = prepare_report_content(document)
    component = prepared.entries[0].components[0]
    html = render_prepared_report_html(prepared)

    assert component.key == "cluster_sizes"
    assert component.paragraphs == ()
    assert "Model-only note" not in html


def _renderable_snapshots():
    overview = analyze_dataset_overview(pd.DataFrame({"value": [1, None, 3], "group": ["a", "b", "a"]}))
    statistics = analyze_descriptive_statistics(
        pd.DataFrame({"measure": [1.0, 2.0, 4.0, 8.0], "group": ["a", "b", "a", "b"]})
    )
    return [
        (AnalysisCategory.OVERVIEW, overview),
        (AnalysisCategory.STATISTICS, statistics),
        (AnalysisCategory.HYPOTHESIS_TESTS, group_snapshot()),
        (AnalysisCategory.HYPOTHESIS_TESTS, chi_snapshot()),
        (AnalysisCategory.HYPOTHESIS_TESTS, paired_snapshot()),
        (AnalysisCategory.CORRELATION, correlation_snapshot()),
        (AnalysisCategory.REGRESSION, linear_snapshot()),
        (AnalysisCategory.REGRESSION, logistic_snapshot()),
        (AnalysisCategory.REGRESSION, poisson_snapshot()),
        (AnalysisCategory.REGRESSION, negative_binomial_snapshot()),
        (AnalysisCategory.REGRESSION, cox_snapshot()),
        (AnalysisCategory.OUTLIERS, univariate_snapshot()),
        (AnalysisCategory.OUTLIERS, multivariate_snapshot()),
        (AnalysisCategory.CLUSTERING, clustering_snapshot()),
        (AnalysisCategory.CLUSTERING, clustering_snapshot(ClusteringMethod.DBSCAN)),
        (AnalysisCategory.PCA, pca_snapshot()),
        (AnalysisCategory.TIME_SERIES, time_series_snapshot()),
        (AnalysisCategory.TIME_SERIES, irregular_snapshot()),
    ]


def test_localized_report_tables_reuse_export_builders_and_cover_categories() -> None:
    def translate(_context: str, text: str) -> str:
        return f"localized {text}"

    cases = _renderable_snapshots()

    for category, snapshot in cases:
        entry = create_report_entry(category, DATASET, snapshot)
        keys = entry.selected_components
        table_keys = tuple(component.key for component in entry.components if component.kind == "table")
        tables = localized_report_tables(category, snapshot, keys, translate=translate)

        assert len(tables) == len(table_keys)
        assert all(title.startswith("localized ") for title in tables)
        assert all(frame.shape[1] > 0 for frame in tables.values())
        assert len({id(frame) for frame in tables.values()}) == len(tables)


def test_hypothesis_html_uses_shared_configured_title_components_and_escaped_role_values():
    numeric_column = "<numeric>" + "_measurement" * 20
    grouping_column = "group & <label>" + "_category" * 20
    frame = pd.DataFrame({
        numeric_column: [1.0, 2.0, 3.0, 4.0],
        grouping_column: ["A", "A", "B", "B"],
    })
    result = analyze_group_comparison(frame, numeric_column, grouping_column)
    snapshot = HypothesisExportSnapshot(
        HypothesisTest.GROUP_COMPARISON,
        result,
        (result.numeric_column, result.grouping_column),
    )
    entry = _entry(
        AnalysisCategory.HYPOTHESIS_TESTS,
        snapshot,
        ("summary", "test_results"),
    )
    document = ReportDocument()
    document.upsert(entry)

    prepared = prepare_report_content(document)
    prepared_entry = prepared.entries[0]
    component_labels = tuple(component.label for component in prepared_entry.components)
    table_titles = tuple(table.title for component in prepared_entry.components for table in component.tables)
    html = render_prepared_report_html(prepared)

    assert prepared_entry.title == "Hypothesis Tests — Group comparison"
    assert prepared_entry.configuration[0].display_value == numeric_column
    assert prepared_entry.configuration[1].display_value == grouping_column
    assert component_labels == ("Group summary", "Test results")
    assert table_titles == component_labels
    assert f"<dt>Numeric variable:</dt><dd>{escape(numeric_column)}</dd>" in html
    assert f"<dt>Grouping variable:</dt><dd>{escape(grouping_column)}</dd>" in html
    assert "Hypothesis Tests — Group comparison" in html
    assert "&lt;numeric&gt;" in html
    assert numeric_column not in html
    assert grouping_column not in html


def test_hypothesis_report_labels_are_captured_before_worker_preparation():
    snapshot = paired_snapshot(3)
    entry = _entry(AnalysisCategory.HYPOTHESIS_TESTS, snapshot, ("summary",))
    document = ReportDocument()
    document.upsert(entry)

    def translate(context: str, text: str) -> str:
        if context == "HypothesisPresentation" and text != "{category} — {method}":
            return f"sv:{text}"
        return text

    labels = capture_report_labels(translate=translate)

    prepared = prepare_report_content(document, labels=labels)

    assert prepared.entries[0].title == "sv:Hypothesis Tests — sv:Paired comparison"
    assert prepared.entries[0].configuration[0].label == "sv:Measurement variables (selected order):"
    assert prepared.entries[0].configuration[1].label == "sv:Tests computed:"
    assert prepared.entries[0].configuration[1].items == ("sv:Friedman test",)
    assert prepared.entries[0].components[0].label == "sv:Measurement summary"
    assert prepared.entries[0].components[0].tables[0].title == "sv:Measurement summary"


def test_pca_html_and_export_share_localized_title_roles_components_and_escaped_features():
    feature = '<feature & "quoted">' + "very long name " * 30
    base_snapshot = pca_snapshot()
    snapshot = replace(base_snapshot, result=replace(base_snapshot.result, columns=(feature, "second", "third")))
    selection = ("feature_loadings", "explained_variance", "model_summary")
    entry = _entry(AnalysisCategory.PCA, snapshot, selection)
    document = ReportDocument()
    document.upsert(entry)

    def translate(context: str, text: str) -> str:
        return f"sv:{text}" if context == "PCAPresentation" else text

    labels = capture_report_labels(translate=translate)
    prepared = prepare_report_content(document, labels=labels)
    prepared_entry = prepared.entries[0]
    html = render_prepared_report_html(prepared)
    localized_tables = localized_report_tables(AnalysisCategory.PCA, snapshot, selection, labels=labels)
    raw_tables = pca_export_tables(
        snapshot,
        (
            PCAExportComponent.FEATURE_LOADINGS,
            PCAExportComponent.EXPLAINED_VARIANCE,
            PCAExportComponent.MODEL_SUMMARY,
        ),
    )

    assert prepared_entry.title == "sv:PCA"
    assert tuple((field.label, field.items) for field in prepared_entry.configuration) == (
        ("sv:Features:", (feature, "second", "third")),
        ("sv:Standardization:", ("sv:Standardized",)),
    )
    expected_components = ("sv:Feature loadings", "sv:Explained variance", "sv:Model summary")
    assert tuple(component.label for component in prepared_entry.components) == expected_components
    assert (
        tuple(table.title for component in prepared_entry.components for table in component.tables)
        == expected_components
    )
    assert tuple(localized_tables) == expected_components
    for (localized_title, localized_frame), (_, raw_frame), expected_title in zip(
        localized_tables.items(), raw_tables.items(), expected_components, strict=True
    ):
        assert localized_title == expected_title
        for column_index, raw_column in enumerate(raw_frame.columns):
            if pd.api.types.is_numeric_dtype(raw_frame[raw_column].dtype):
                assert localized_frame.dtypes.iloc[column_index] == raw_frame.dtypes.iloc[column_index]
                pd.testing.assert_series_equal(
                    localized_frame.iloc[:, column_index],
                    raw_frame.iloc[:, column_index],
                    check_names=False,
                )
    escaped_features = escape(f"{feature}, second, third")
    assert f"<dt>sv:Features:</dt><dd>{escaped_features}</dd>" in html
    assert "sv:Standardization:</dt><dd>sv:Standardized</dd>" in html
    assert escape(feature, quote=True) in html
    assert feature not in html
    assert "sv:PCA" in html


def test_time_series_report_and_html_share_applied_descriptor_and_export_labels():
    time_column = '<time & "quoted">' + "timestamp " * 12
    value_column = "<value & metric>"
    frame = pd.DataFrame({
        time_column: pd.date_range("2025-01-01", periods=28, freq="D"),
        value_column: [float(index + 1) for index in range(28)],
    })
    result = analyze_time_series(
        frame,
        time_column,
        value_column,
        resample_frequency="D",
        seasonal_period=None,
        decomposition_model=DecompositionModel.MULTIPLICATIVE,
    )
    assert result.error is None
    snapshot = TimeSeriesExportSnapshot(
        result,
        CHART_LABELS,
        applied_configuration=TimeSeriesAppliedConfiguration(
            time_column,
            value_column,
            "D",
            None,
            DecompositionModel.MULTIPLICATIVE,
        ),
    )
    selection = ("series", "model_summary")
    document = ReportDocument()
    document.upsert(_entry(AnalysisCategory.TIME_SERIES, snapshot, selection))

    def translate(context: str, source: str) -> str:
        return f"sv:{source}" if context == "TimeSeriesPresentation" else source

    labels = capture_report_labels(translate=translate)
    presentation = build_analysis_presentation(AnalysisCategory.TIME_SERIES, snapshot, translate)
    prepared = prepare_report_content(document, labels=labels)
    entry = prepared.entries[0]
    html = render_prepared_report_html(prepared)
    export_tables = localized_report_tables(
        AnalysisCategory.TIME_SERIES,
        snapshot,
        selection,
        labels=labels,
    )

    assert presentation.title == "Time Series"
    assert entry.title == presentation.title
    assert tuple(field.display_value for field in entry.configuration) == (
        time_column,
        value_column,
        "sv:Daily",
        "sv:Automatic (detected: 7)",
        "sv:Multiplicative",
    )
    assert tuple(field.label for field in entry.configuration) == (
        "sv:Time column:",
        "sv:Value column:",
        "sv:Resampling:",
        "sv:Seasonal period:",
        "sv:Decomposition model:",
    )
    expected_titles = ("sv:Series", "sv:Model summary")
    assert tuple(component.label for component in entry.components) == expected_titles
    assert tuple(table.title for component in entry.components for table in component.tables) == expected_titles
    assert tuple(export_tables) == expected_titles
    assert "Time Series — Time Series" not in html
    assert "Time Series</h2>" in html
    assert f"<dt>sv:Time column:</dt><dd>{escape(time_column)}</dd>" in html
    assert f"<dt>sv:Value column:</dt><dd>{escape(value_column)}</dd>" in html
    assert "&lt;time &amp; &quot;quoted&quot;&gt;" in html
    assert time_column not in html
    assert value_column not in html

    from expo_jbm329.services.analysis.timeseries_export import (
        TimeSeriesExportComponent,
        time_series_export_tables,
    )

    raw = time_series_export_tables(
        snapshot,
        (TimeSeriesExportComponent.SERIES, TimeSeriesExportComponent.MODEL_SUMMARY),
    )
    localized_series = export_tables["sv:Series"]
    raw_series = raw[TimeSeriesExportComponent.SERIES]
    assert localized_series.columns.tolist() == [
        "sv:Timestamp",
        "sv:Value",
        "sv:Trend",
        "sv:Seasonal",
        "sv:Residual",
    ]
    assert localized_series.dtypes.tolist() == raw_series.dtypes.tolist()
    for index in range(1, localized_series.shape[1]):
        pd.testing.assert_series_equal(
            localized_series.iloc[:, index],
            raw_series.iloc[:, index],
            check_dtype=True,
            check_names=False,
        )


def test_time_series_html_reports_applied_model_without_claiming_partial_decomposition():
    snapshot = irregular_snapshot()
    snapshot = replace(
        snapshot,
        notes=(
            "Decomposition model: Additive",
            "The autocorrelation requires a regular time frequency.",
            "Seasonal decomposition requires a regular time frequency.",
        ),
    )
    entry = _entry(AnalysisCategory.TIME_SERIES, snapshot, ("model_summary", "charts"))
    document = ReportDocument()
    document.upsert(entry)

    prepared = prepare_report_content(document)
    prepared_entry = prepared.entries[0]
    chart_component = next(component for component in prepared_entry.components if component.kind == "chart")
    html = render_prepared_report_html(prepared)

    assert prepared_entry.title == "Time Series"
    assert prepared_entry.configuration[-1].display_value == "Additive"
    assert len(chart_component.charts) == 1
    assert chart_component.charts[0].heading == "Series"
    assert "The autocorrelation requires a regular time frequency." in html
    assert "Seasonal decomposition requires a regular time frequency." in html
    assert "Seasonal decomposition (calculated)" not in html


def _resampled_time_series_snapshot(notes: tuple[str, ...]) -> TimeSeriesExportSnapshot:
    frame = pd.DataFrame({
        "time": pd.date_range("2024-01-01", periods=28, freq="D"),
        "value": [float(index + 1) for index in range(28)],
    })
    result = analyze_time_series(frame, "time", "value", resample_frequency="D", seasonal_period=7)
    assert result.error is None
    return TimeSeriesExportSnapshot(result, CHART_LABELS, notes)


@pytest.mark.parametrize("variant", ["regular", "resampled", "partial"])
@pytest.mark.parametrize(
    "notes",
    [
        (),
        (
            "First <model> & note\ncontinued safely",
            "Second model note",
            "Third note",
            "Fourth note",
            "Fifth note",
            "Sixth note",
            "Seventh note",
        ),
    ],
)
def test_time_series_html_separates_model_notes_without_changing_exports(variant, notes):
    if variant == "regular":
        snapshot = time_series_snapshot(notes=notes)
    elif variant == "resampled":
        snapshot = _resampled_time_series_snapshot(notes)
    else:
        snapshot = replace(irregular_snapshot(), notes=notes)

    component_key = TimeSeriesExportComponent.MODEL_SUMMARY
    raw_before = time_series_export_tables(snapshot, (component_key,))[component_key]
    localized_export = localized_report_tables(
        AnalysisCategory.TIME_SERIES,
        snapshot,
        ("model_summary",),
    )["Model summary"]
    document = ReportDocument()
    document.upsert(_entry(AnalysisCategory.TIME_SERIES, snapshot, ("model_summary",)))

    prepared = prepare_report_content(document)
    component = prepared.entries[0].components[0]
    html = render_prepared_report_html(prepared)
    raw_after = time_series_export_tables(snapshot, (component_key,))[component_key]

    expected_metrics = [
        "Source rows",
        "Invalid rows dropped",
        "Duplicate rows averaged",
        "Time points",
        "Seasonal period",
    ]
    metric_index = component.tables[0].headers.index("Metric")
    assert component.tables[0].headers == ("Metric", "Value")
    assert len(component.tables[0].rows) == len(expected_metrics)
    assert tuple(row[metric_index] for row in component.tables[0].rows) == tuple(expected_metrics)
    assert component.paragraphs == notes
    assert localized_export.columns.tolist() == ["Metric", "Value", "Notes"]
    assert len(localized_export) == max(len(expected_metrics), len(notes))
    assert localized_export["Notes"].iloc[: len(notes)].tolist() == list(notes)
    assert localized_export["Notes"].iloc[len(notes) :].isna().all()
    assert isinstance(localized_export["Notes"].dtype, pd.StringDtype)
    assert raw_before.columns.tolist() == ["metric", "value", "notes"]
    assert raw_before["metric"].dtype == pd.StringDtype()
    assert raw_before["value"].dtype == "float64"
    assert raw_before["notes"].dtype == pd.StringDtype()
    pd.testing.assert_frame_equal(raw_after, raw_before)
    if notes:
        assert "Notes" not in component.tables[0].headers
        assert html.index("</table></div>") < html.index('<div class="report-paragraphs">')
        assert html.index("First &lt;model&gt; &amp; note") < html.index("Second model note")
        assert "continued safely" in html
        assert "First <model>" not in html
        assert "white-space: pre-wrap" in html
    else:
        assert '<div class="report-paragraphs">' not in html


def test_time_series_html_keeps_real_metric_rows_with_missing_values(monkeypatch):
    from expo_jbm329.services.analysis import report

    snapshot = time_series_snapshot(notes=("Captured model note",))
    original_export_tables = report.time_series_export_tables

    def export_with_missing_value(snapshot_arg, components):
        tables = original_export_tables(snapshot_arg, components)
        tables[TimeSeriesExportComponent.MODEL_SUMMARY].loc[0, "value"] = np.nan
        return tables

    monkeypatch.setattr(report, "time_series_export_tables", export_with_missing_value)
    document = ReportDocument()
    document.upsert(_entry(AnalysisCategory.TIME_SERIES, snapshot, ("model_summary",)))

    component = prepare_report_content(document).entries[0].components[0]
    metric_index = component.tables[0].headers.index("Metric")
    value_index = component.tables[0].headers.index("Value")
    source_rows = next(row for row in component.tables[0].rows if row[metric_index] == "Source rows")

    assert pd.isna(source_rows[value_index])
    assert len(component.tables[0].rows) == len(TimeSeriesMetric)
    assert component.paragraphs == snapshot.notes


def test_time_series_notes_are_excluded_when_model_summary_is_not_selected():
    snapshot = replace(time_series_snapshot(), notes=("Model-only note",))
    document = ReportDocument()
    document.upsert(_entry(AnalysisCategory.TIME_SERIES, snapshot, ("series",)))

    prepared = prepare_report_content(document)
    component = prepared.entries[0].components[0]
    html = render_prepared_report_html(prepared)

    assert component.key == "series"
    assert component.paragraphs == ()
    assert "Model-only note" not in html


def test_time_series_descriptor_and_html_use_compiled_swedish_labels():
    from pathlib import Path

    from PyQt6.QtCore import QCoreApplication, QTranslator
    from PyQt6.QtWidgets import QApplication

    snapshot = time_series_snapshot()
    assert snapshot.applied_configuration is not None
    snapshot = replace(
        snapshot,
        applied_configuration=TimeSeriesAppliedConfiguration(
            snapshot.result.datetime_column,
            snapshot.result.value_column,
            None,
            None,
            snapshot.result.decomposition_model,
        ),
    )
    document = ReportDocument()
    document.upsert(_entry(AnalysisCategory.TIME_SERIES, snapshot, ("series", "model_summary")))
    translator = QTranslator()
    catalog = Path(__file__).parents[2] / "src" / "expo_jbm329" / "i18n" / "locales" / "app_sv.qm"
    assert translator.load(str(catalog))
    app = QApplication.instance()
    app.installTranslator(translator)
    try:
        presentation = build_analysis_presentation(AnalysisCategory.TIME_SERIES, snapshot, QCoreApplication.translate)
        labels = capture_report_labels(QCoreApplication.translate)
    finally:
        app.removeTranslator(translator)

    prepared = prepare_report_content(document, labels=labels)
    entry = prepared.entries[0]
    html = render_prepared_report_html(prepared)

    assert presentation.title == "Tidsserie"
    assert entry.title == "Tidsserie"
    assert tuple(field.label for field in entry.configuration) == (
        "Tidskolumn:",
        "Värdekolumn:",
        "Omsampling:",
        "Säsongsperiod:",
        "Dekomponeringsmodell:",
    )
    assert entry.configuration[2].display_value == "Ursprunglig frekvens"
    assert entry.configuration[3].display_value == "Automatiskt (identifierad: 7)"
    assert entry.configuration[4].display_value == "Additiv"
    assert tuple(component.label for component in entry.components) == ("Serie", "Modellsammanfattning")
    assert "Tidsserie" in html
    assert "Tidskolumn:" in html
    assert "Automatiskt (identifierad: 7)" in html


@pytest.mark.parametrize(
    ("factory", "model", "model_name", "chart_label"),
    [
        (linear_snapshot, RegressionModel.LINEAR, "Linear regression", "Linear diagnostics"),
        (logistic_snapshot, RegressionModel.LOGISTIC, "Logistic regression", "Logistic diagnostics"),
        (poisson_snapshot, RegressionModel.POISSON, "Poisson regression", "Count-model diagnostics"),
        (
            negative_binomial_snapshot,
            RegressionModel.NEGATIVE_BINOMIAL,
            "Negative binomial regression",
            "Count-model diagnostics",
        ),
        (
            cox_snapshot,
            RegressionModel.COX,
            "Cox proportional-hazards regression",
            "Survival charts",
        ),
    ],
)
def test_regression_html_and_export_tables_share_applied_labels(factory, model, model_name, chart_label):
    snapshot = factory()
    selection = ("coefficients", "model_metrics")
    entry = _entry(AnalysisCategory.REGRESSION, snapshot, selection)
    document = ReportDocument()
    document.upsert(entry)

    def translate(context: str, source: str) -> str:
        return f"sv:{source}" if context == "RegressionPresentation" else source

    labels = capture_report_labels(translate=translate)
    prepared = prepare_report_content(document, labels=labels)
    html = render_prepared_report_html(prepared)
    export_tables = localized_report_tables(
        AnalysisCategory.REGRESSION,
        snapshot,
        selection,
        labels=labels,
    )
    prepared_entry = prepared.entries[0]
    table_titles = tuple(table.title for component in prepared_entry.components for table in component.tables)

    assert prepared_entry.title == f"sv:sv:Regression — sv:{model_name}"
    assert tuple(field.label for field in prepared_entry.configuration[:1]) == (
        "sv:Outcome:" if model is not RegressionModel.COX else "sv:Duration:",
    )
    if model is RegressionModel.COX:
        assert prepared_entry.configuration[1].label == "sv:Event:"
    assert any(field.label == "sv:Predictors:" for field in prepared_entry.configuration)
    assert tuple(component.label for component in prepared_entry.components) == ("sv:Coefficients", "sv:Model summary")
    assert table_titles == tuple(export_tables)
    assert all(name.startswith("sv:") for name in export_tables)
    assert "sv:Predictors:" in html
    assert any(component.label == chart_label for component in entry.components)
    assert snapshot.model is model


@pytest.mark.parametrize(
    "factory",
    [linear_snapshot, logistic_snapshot, poisson_snapshot, negative_binomial_snapshot, cox_snapshot],
)
def test_regression_html_separates_notes_without_changing_exports(factory):
    snapshot = replace(factory(), notes=tuple(f"Model note {index}" for index in range(30)))
    export_before = regression_export_tables(snapshot, (RegressionExportComponent.MODEL_METRICS,))[
        RegressionExportComponent.MODEL_METRICS
    ]
    raw_metrics = regression_metrics_table(snapshot)
    localized_before = localized_report_tables(AnalysisCategory.REGRESSION, snapshot, ("model_metrics",))[
        "Model summary"
    ]
    document = ReportDocument()
    document.upsert(_entry(AnalysisCategory.REGRESSION, snapshot, ("model_metrics",)))

    prepared = prepare_report_content(document)
    prepared_component = prepared.entries[0].components[0]
    report_table = prepared_component.tables[0]
    html = render_prepared_report_html(prepared)
    localized_export = localized_report_tables(
        AnalysisCategory.REGRESSION,
        snapshot,
        ("model_metrics",),
    )["Model summary"]
    export_after = regression_export_tables(snapshot, (RegressionExportComponent.MODEL_METRICS,))[
        RegressionExportComponent.MODEL_METRICS
    ]
    expected_metrics = raw_metrics.loc[raw_metrics["metric"].notna()]

    assert report_table.headers == ("Metric", "Value")
    assert tuple(row[0] for row in report_table.rows) == tuple(localized_export["Metric"].iloc[: len(expected_metrics)])
    assert tuple(row[1] for row in report_table.rows) == tuple(localized_export["Value"].iloc[: len(expected_metrics)])
    assert len(report_table.rows) == len(expected_metrics)
    assert prepared_component.paragraphs == snapshot.notes
    assert "Notes" not in report_table.headers
    assert localized_export.columns.tolist() == ["Metric", "Value", "Notes"]
    assert len(localized_export) == len(snapshot.notes)
    assert localized_export["Notes"].tolist() == list(snapshot.notes)
    assert html.index("Model note 0") > html.index("<h3>Model summary</h3>")
    assert list(export_before.columns) == ["metric", "value", "notes"]
    assert export_before["metric"].dtype == pd.StringDtype()
    assert export_before["value"].dtype == raw_metrics["value"].dtype
    assert export_before["notes"].dtype == pd.StringDtype()
    pd.testing.assert_frame_equal(export_after, export_before)
    pd.testing.assert_frame_equal(localized_export, localized_before)
    assert html.index("</table></div>") < html.index('<div class="report-paragraphs">')
    assert html.index("Model note 0") < html.index("Model note 1") < html.index("Model note 29")
    assert html.count("Model note 0") == 1


@pytest.mark.parametrize(
    "factory",
    [linear_snapshot, logistic_snapshot, poisson_snapshot, negative_binomial_snapshot, cox_snapshot],
)
def test_regression_html_without_notes_has_only_metric_rows(factory):
    snapshot = replace(factory(), notes=())
    raw_metrics = regression_metrics_table(snapshot)
    document = ReportDocument()
    document.upsert(_entry(AnalysisCategory.REGRESSION, snapshot, ("model_metrics",)))

    prepared = prepare_report_content(document)
    prepared_component = prepared.entries[0].components[0]
    html = render_prepared_report_html(prepared)

    assert prepared_component.tables[0].headers == ("Metric", "Value")
    assert len(prepared_component.tables[0].rows) == raw_metrics["metric"].notna().sum()
    assert prepared_component.paragraphs == ()
    assert '<div class="report-paragraphs">' not in html


@pytest.mark.parametrize("factory", [linear_snapshot, logistic_snapshot])
def test_regression_html_localizes_metrics_and_escapes_ordered_notes(factory):
    notes = ("First <calibration> & observed\ncontinued safely", "Second note")
    snapshot = replace(factory(), notes=notes)
    document = ReportDocument()
    document.upsert(_entry(AnalysisCategory.REGRESSION, snapshot, ("model_metrics",)))

    labels = capture_report_labels(
        translate=lambda context, text: f"sv:{text}" if context == "AnalysisExportDialog" else text
    )
    prepared = prepare_report_content(document, labels=labels)
    prepared_component = prepared.entries[0].components[0]
    html = render_prepared_report_html(prepared)

    assert prepared_component.tables[0].headers == ("sv:Metric", "sv:Value")
    assert prepared_component.tables[0].rows[0][0] == "sv:Rows used"
    assert prepared_component.paragraphs == notes
    assert html.index("</table></div>") < html.index('<div class="report-paragraphs">')
    assert html.index("First &lt;calibration&gt; &amp; observed") < html.index("Second note")
    assert "continued safely" in html
    assert "First <calibration>" not in html
    assert "white-space: pre-wrap" in html


@pytest.mark.parametrize("factory", [linear_snapshot, logistic_snapshot])
def test_regression_html_keeps_real_metric_with_missing_value(monkeypatch, factory):
    snapshot = factory()
    export_tables = regression_export_tables

    def with_missing_metric_value(snapshot, components, *, intercept_label="(Intercept)"):
        tables = export_tables(snapshot, components, intercept_label=intercept_label)
        metrics = tables.get(RegressionExportComponent.MODEL_METRICS)
        if metrics is not None:
            metrics.loc[0, "value"] = float("nan")
        return tables

    monkeypatch.setattr(
        "expo_jbm329.services.analysis.report.regression_export_tables",
        with_missing_metric_value,
    )
    document = ReportDocument()
    document.upsert(_entry(AnalysisCategory.REGRESSION, snapshot, ("model_metrics",)))

    prepared_component = prepare_report_content(document).entries[0].components[0]
    first_metric, first_value = prepared_component.tables[0].rows[0]

    assert first_metric == "Rows used"
    assert pd.isna(first_value)
    assert len(prepared_component.tables[0].rows) == len(regression_metrics_table(snapshot)["metric"].dropna())


@pytest.mark.parametrize("factory", [linear_snapshot, logistic_snapshot])
@pytest.mark.parametrize("selection", [("charts",), ("coefficients",), ("coefficients", "charts")])
def test_regression_notes_are_omitted_when_model_metrics_are_not_selected(monkeypatch, factory, selection):
    snapshot = replace(factory(), notes=("Hidden model note",))
    document = ReportDocument()
    document.upsert(_entry(AnalysisCategory.REGRESSION, snapshot, selection))
    monkeypatch.setattr(
        "expo_jbm329.services.analysis.report.render_regression_charts",
        lambda *_args, **_kwargs: (ExcelChartImage("ROC", b"image", 10, 10),),
    )

    prepared = prepare_report_content(document)
    html = render_prepared_report_html(prepared)

    assert tuple(component.key for component in prepared.entries[0].components) == selection
    assert all(component.paragraphs == () for component in prepared.entries[0].components)
    assert "Hidden model note" not in html
    assert '<div class="report-paragraphs">' not in html


def test_linear_regression_html_places_model_notes_only_below_metrics(monkeypatch):
    snapshot = replace(linear_snapshot(), notes=("Linear note",))
    entry = _entry(AnalysisCategory.REGRESSION, snapshot, ("coefficients", "model_metrics", "charts"))
    entry = entry.with_selection(entry.selected_components, "User entry note")
    document = ReportDocument()
    document.upsert(entry)
    monkeypatch.setattr(
        "expo_jbm329.services.analysis.report.render_regression_charts",
        lambda *_args, **_kwargs: (ExcelChartImage("Diagnostics", b"image", 10, 10),),
    )

    prepared = prepare_report_content(document)
    coefficients, metrics, charts = prepared.entries[0].components
    html = render_prepared_report_html(prepared)

    assert metrics.tables[0].headers == ("Metric", "Value")
    assert metrics.paragraphs == ("Linear note",)
    assert coefficients.paragraphs == charts.paragraphs == ()
    assert html.count("Linear note") == 1
    assert html.count("User entry note") == 1
    assert html.index("Linear note") > html.index("Model summary</h3>")


def test_regression_html_escapes_long_applied_roles_reference_levels_and_terms():
    original = linear_snapshot()
    result = original.result
    long_outcome = "<outcome & analysis>" + " name" * 20
    long_predictor = "predictor <&>" + " column" * 20
    long_reference = "<control & reference>" + " level" * 12
    terms = (
        result.terms[0],
        replace(result.terms[1], column=long_predictor),
        *result.terms[2:],
    )
    references = (replace(result.references[0], column=long_predictor, reference_level=long_reference),)
    modified = replace(
        result,
        target=long_outcome,
        predictors=(long_predictor,),
        terms=terms,
        references=references,
    )
    snapshot = replace(original, result=modified)
    document = ReportDocument()
    document.upsert(_entry(AnalysisCategory.REGRESSION, snapshot, ("coefficients",)))

    html = render_report_html(document)

    assert f"<dd>{escape(long_outcome)}</dd>" in html
    assert f"<dd>{escape(long_predictor)}</dd>" in html
    assert escape(long_reference) in html
    assert long_outcome not in html
    assert long_predictor not in html
    assert long_reference not in html


@pytest.mark.parametrize(
    ("family", "variant"),
    [
        ("groups", 2),
        ("groups", 3),
        ("chi_square", 2),
        ("chi_square", 3),
        ("paired", 2),
        ("paired", 3),
    ],
)
def test_hypothesis_report_table_values_do_not_wrap(family: str, variant: int) -> None:
    snapshot_factories: dict[str, Callable[[int], HypothesisExportSnapshot]] = {
        "groups": group_snapshot,
        "chi_square": chi_snapshot,
        "paired": paired_snapshot,
    }
    document = ReportDocument()
    document.upsert(
        _entry(AnalysisCategory.HYPOTHESIS_TESTS, snapshot_factories[family](variant), ("summary", "test_results"))
    )

    prepared = prepare_report_content(document)
    tables = [table for component in prepared.entries[0].components for table in component.tables]
    html = render_prepared_report_html(prepared)

    assert len(tables) == 2
    assert all(table.nowrap_values for table in tables)
    assert html.count('<table class="nowrap-values">') == len(tables)
    assert ".nowrap-values td { white-space: nowrap; }" in html
    assert ".nowrap-values th" not in html


@pytest.mark.parametrize(
    ("family", "variant"),
    [
        ("groups", 2),
        ("groups", 3),
        ("chi_square", 2),
        ("chi_square", 3),
        ("paired", 2),
        ("paired", 3),
    ],
)
def test_hypothesis_report_separates_notes_without_changing_export_tables(family: str, variant: int) -> None:
    snapshot_factories: dict[str, Callable[[int], HypothesisExportSnapshot]] = {
        "groups": group_snapshot,
        "chi_square": chi_snapshot,
        "paired": paired_snapshot,
    }
    snapshot = snapshot_factories[family](variant)
    raw_results = hypothesis_export_tables(snapshot, (HypothesisExportComponent.TEST_RESULTS,))[
        HypothesisExportComponent.TEST_RESULTS
    ]
    expected_test_names = raw_results.loc[raw_results["test"].notna(), "test"].tolist()
    exported_before = raw_results.copy(deep=True)
    document = ReportDocument()
    document.upsert(
        _entry(
            AnalysisCategory.HYPOTHESIS_TESTS,
            snapshot,
            ("test_results",),
        )
    )

    prepared_component = prepare_report_content(document).entries[0].components[0]
    report_table = prepared_component.tables[0]
    report_rows = dict(zip(report_table.headers, zip(*report_table.rows, strict=True), strict=True))
    localized_export = localized_report_tables(
        AnalysisCategory.HYPOTHESIS_TESTS,
        snapshot,
        ("test_results",),
    )["Test results"]
    exported_after = hypothesis_export_tables(snapshot, (HypothesisExportComponent.TEST_RESULTS,))[
        HypothesisExportComponent.TEST_RESULTS
    ]

    assert prepared_component.paragraphs == snapshot.notes
    assert "Notes" not in report_table.headers
    assert report_rows["Test"] == tuple(expected_test_names)
    assert len(report_table.rows) == len(expected_test_names)
    report_frame = pd.DataFrame.from_records(report_table.rows, columns=report_table.headers)
    if family in {"groups", "chi_square"} and variant == 2:
        assert report_frame.isna().any().any()
    if family == "chi_square" and variant == 2:
        assert "Fisher's exact test" in report_rows["Test"]
    else:
        assert "Fisher's exact test" not in report_rows["Test"]
    assert "Notes" in localized_export.columns
    assert localized_export.shape == raw_results.shape
    assert localized_export["Notes"].tolist() == list(snapshot.notes)
    pd.testing.assert_frame_equal(exported_after, exported_before)


def test_hypothesis_report_handles_no_notes_and_more_notes_than_tests():
    snapshot_with_notes = replace(paired_snapshot(2), notes=("one", "two", "three"))
    snapshot_without_notes = replace(snapshot_with_notes, notes=())

    def prepare(snapshot: HypothesisExportSnapshot):
        document = ReportDocument()
        document.upsert(_entry(AnalysisCategory.HYPOTHESIS_TESTS, snapshot, ("test_results",)))
        return prepare_report_content(document).entries[0].components[0]

    with_notes = prepare(snapshot_with_notes)
    without_notes = prepare(snapshot_without_notes)

    assert len(with_notes.tables[0].rows) == 1
    assert with_notes.paragraphs == ("one", "two", "three")
    assert without_notes.tables[0].rows == with_notes.tables[0].rows
    assert without_notes.paragraphs == ()


def test_hypothesis_notes_render_escaped_in_order_below_test_results_only():
    snapshot = replace(
        group_snapshot(),
        notes=("First <script>alert('x')</script>\ncontinued & safe", "Second note"),
    )
    entry = _entry(AnalysisCategory.HYPOTHESIS_TESTS, snapshot, ("test_results",)).with_selection(
        ("test_results",),
        "Independent entry note",
    )
    document = ReportDocument()
    document.upsert(entry)

    prepared = prepare_report_content(document)
    html = render_prepared_report_html(prepared)
    results_position = html.index("</table></div>")
    paragraphs_position = html.index('<div class="report-paragraphs">')

    assert prepared.entries[0].components[0].paragraphs == snapshot.notes
    assert results_position < paragraphs_position
    assert html.index("First &lt;script&gt;", paragraphs_position) < html.index("Second note", paragraphs_position)
    assert "First <script>" not in html
    assert "continued &amp; safe" in html
    assert "white-space: pre-wrap" in html
    assert '<p class="report-note">Independent entry note</p>' in html
    assert html.index("Independent entry note") < paragraphs_position

    summary_entry = _entry(AnalysisCategory.HYPOTHESIS_TESTS, snapshot, ("summary",))
    summary_document = ReportDocument()
    summary_document.upsert(summary_entry)
    summary_html = render_report_html(summary_document)
    assert snapshot.notes[0] not in summary_html
    assert '<div class="report-paragraphs">' not in summary_html


@pytest.mark.parametrize("factory", [group_snapshot, chi_snapshot, paired_snapshot])
def test_hypothesis_report_charts_hide_captions_and_preserve_accessible_names(
    factory: Callable[[], HypothesisExportSnapshot],
) -> None:
    snapshot = factory()
    document = ReportDocument()
    document.upsert(_entry(AnalysisCategory.HYPOTHESIS_TESTS, snapshot, ("charts",)))
    with patch(
        "expo_jbm329.services.analysis.report.render_hypothesis_charts",
        wraps=render_hypothesis_charts,
    ) as render:
        prepared = prepare_report_content(document)

    labels = render.call_args.args[1]
    expected_axes = (
        (snapshot.columns[1], snapshot.columns[0]) if snapshot.test is HypothesisTest.GROUP_COMPARISON else None
    )
    assert labels.group_axis_labels == expected_axes
    assert not prepared.entries[0].components[0].show_chart_captions
    html = render_prepared_report_html(prepared)
    assert "<figcaption>" not in html
    assert f'alt="{escape(" / ".join(snapshot.columns))}"' in html


def test_preparation_renders_selected_categories_and_variants(monkeypatch) -> None:
    calls: dict[str, int] = {}

    def fake_images(name: str, count: int = 1):
        def render(*args, **kwargs):
            calls[name] = calls.get(name, 0) + 1
            progress = kwargs.get("progress_cb")
            if progress is not None:
                progress(45)
                progress(100)
            return tuple(
                ExcelChartImage(f"{name} chart {index + 1}", b"png-bytes", 80, 40, ("caption",))
                for index in range(count)
            )

        return render

    monkeypatch.setattr("expo_jbm329.services.analysis.report.render_statistics_charts", fake_images("statistics", 2))
    monkeypatch.setattr("expo_jbm329.services.analysis.report.render_hypothesis_charts", fake_images("hypothesis"))
    monkeypatch.setattr("expo_jbm329.services.analysis.report.render_regression_charts", fake_images("regression"))
    monkeypatch.setattr(
        "expo_jbm329.services.analysis.report.render_univariate_outlier_charts", fake_images("univariate")
    )
    monkeypatch.setattr(
        "expo_jbm329.services.analysis.report.render_multivariate_outlier_charts", fake_images("multivariate")
    )
    monkeypatch.setattr("expo_jbm329.services.analysis.report.render_clustering_charts", fake_images("clustering"))
    monkeypatch.setattr("expo_jbm329.services.analysis.report.render_pca_charts", fake_images("pca", 2))
    monkeypatch.setattr("expo_jbm329.services.analysis.report.render_time_series_charts", fake_images("time_series", 2))

    def fake_correlation(_snapshot, components, labels, **kwargs):
        calls["correlation"] = calls.get("correlation", 0) + 1
        progress = kwargs.get("progress_cb")
        if progress is not None:
            progress(100)
        images = []
        if CorrelationExportComponent.MATRIX_PLOT in components:
            images.append(ExcelChartImage(labels.matrix_title, b"matrix", 80, 40))
        if CorrelationExportComponent.SCATTERPLOTS in components:
            images.append(ExcelChartImage("pair scatter", b"scatter", 80, 40))
        return tuple(images)

    monkeypatch.setattr("expo_jbm329.services.analysis.report.render_correlation_charts", fake_correlation)
    document = ReportDocument(title="Complete report", description="All reportable analyses")
    for category, snapshot in _renderable_snapshots():
        document.upsert(_entry(category, snapshot))

    progress_values: list[int] = []
    prepared = prepare_report_content(
        document,
        translate=lambda context, text: f"{context}: {text}",
        progress_cb=progress_values.append,
    )

    assert len(prepared.entries) == len(document.entries)
    assert all(entry.components for entry in prepared.entries)
    assert prepared.entries[0].category == "AnalysisDialog: Overview"
    assert prepared.entries[0].components[0].overview_summary.facts
    statistics_chart = next(component for component in prepared.entries[1].components if component.key == "Charts")
    assert statistics_chart.charts
    hypothesis_chart = next(component for component in prepared.entries[2].components if component.key == "charts")
    assert hypothesis_chart.paragraphs == ()
    assert hypothesis_chart.charts[0].captions == ("caption",)
    assert [component.key for component in prepared.entries[5].components] == [
        "strongest_correlations",
        "matrix_plot",
        "scatterplots",
    ]
    assert len(prepared.entries[5].components[1].charts) == 1
    assert len(prepared.entries[5].components[2].charts) == 1
    assert all(value == sorted(progress_values)[index] for index, value in enumerate(progress_values))
    assert progress_values[-1] == 100
    assert calls == {
        "statistics": 1,
        "hypothesis": 3,
        "correlation": 1,
        "regression": 5,
        "univariate": 1,
        "multivariate": 1,
        "clustering": 2,
        "pca": 1,
        "time_series": 2,
    }


def test_prepare_builds_only_selected_components(monkeypatch) -> None:
    snapshot = pca_snapshot()
    entry = _entry(AnalysisCategory.PCA, snapshot, ("explained_variance",))
    document = ReportDocument()
    document.upsert(entry)

    def unexpected_chart(*_args, **_kwargs):
        pytest.fail("An unselected chart must not be rendered")

    monkeypatch.setattr("expo_jbm329.services.analysis.report.render_pca_charts", unexpected_chart)
    prepared = prepare_report_content(document)

    assert [component.key for component in prepared.entries[0].components] == ["explained_variance"]
    assert len(prepared.entries[0].components[0].tables) == 1
    assert prepared.entries[0].components[0].tables[0].title == "Explained variance"


def test_preparation_captures_document_metadata_before_callbacks() -> None:
    document = ReportDocument(title="Title at request", description="Description at request")
    document.upsert(_entry(AnalysisCategory.PCA, pca_snapshot(), ("explained_variance",)))

    def change_document(_progress: int) -> None:
        document.title = "Changed while preparing"
        document.description = "Changed description"

    prepared = prepare_report_content(document, progress_cb=change_document)

    assert prepared.title == "Title at request"
    assert prepared.description == "Description at request"


@pytest.mark.parametrize("other_dataset", [DATASET, DatasetRef("other", "Other <dataset>", 5, 2)])
def test_report_metadata_appears_once_in_header_without_dataset_dimensions(other_dataset) -> None:
    document = ReportDocument(title="Report")
    first = _entry(AnalysisCategory.PCA, pca_snapshot(), ("explained_variance",))
    second = create_report_entry(
        AnalysisCategory.STATISTICS,
        other_dataset,
        analyze_descriptive_statistics(pd.DataFrame({"value": [1, 2, 3]})),
    )
    second = second.with_selection(("Continuous",), "")
    document.upsert(replace(first, analysis_date="2001-01-01"))
    document.upsert(replace(second, analysis_date="2002-02-02"))
    prepared = prepare_report_content(document, translate=lambda _context, source: f"translated:{source}")
    prepared = replace(prepared, report_date="2026-10-14")

    html = render_prepared_report_html(prepared)
    header, entries = html.split("</header>", 1)

    assert html.count('<dl class="metadata">') == 1
    assert "<dt>translated:Dataset</dt>" in header
    assert "<dt>translated:Report date</dt><dd>2026-10-14</dd>" in header
    assert "<dt>translated:Expo version</dt>" in header
    assert header.count(DATASET.title) == 1
    if other_dataset is not DATASET:
        assert "Other &lt;dataset&gt;" in header
    assert "<dt>translated:Rows</dt>" not in html
    assert "<dt>translated:Columns</dt>" not in html
    assert "Analysis date" not in html
    assert "2001-01-01" not in html
    assert "2002-02-02" not in html
    assert '<dl class="metadata">' not in entries
    assert entries.count('<article class="analysis-entry">') == 2


def test_report_date_is_captured_at_preparation_not_from_entry_or_serialization() -> None:
    document = ReportDocument()
    entry = _entry(AnalysisCategory.PCA, pca_snapshot(), ("explained_variance",))
    document.upsert(replace(entry, analysis_date="2001-01-01"))
    generated_at = datetime(2026, 10, 14, 12, 30, tzinfo=UTC).astimezone()

    with patch("expo_jbm329.services.analysis.report.datetime", wraps=datetime) as clock:
        clock.now.return_value = generated_at
        prepared = prepare_report_content(document)

    html = render_prepared_report_html(prepared)
    assert prepared.report_date == generated_at.date().isoformat()
    assert f"<dt>Report date</dt><dd>{prepared.report_date}</dd>" in html
    assert "2001-01-01" not in html
    assert "2027-10-14" not in html


def test_correlation_charts_follow_selection_order_and_only_selected_keys(monkeypatch) -> None:
    snapshot = correlation_snapshot()
    entry = _entry(
        AnalysisCategory.CORRELATION,
        snapshot,
        ("scatterplots", "matrix_plot"),
    )
    document = ReportDocument()
    document.upsert(entry)
    captured: list[tuple[CorrelationExportComponent, ...]] = []

    def render(_snapshot, components, labels, **_kwargs):
        captured.append(tuple(components))
        return tuple(
            ExcelChartImage(
                labels.matrix_title if item is CorrelationExportComponent.MATRIX_PLOT else "scatter",
                b"chart",
                10,
                10,
            )
            for item in components
        )

    monkeypatch.setattr("expo_jbm329.services.analysis.report.render_correlation_charts", render)
    prepared = prepare_report_content(document)

    assert captured == [(CorrelationExportComponent.SCATTERPLOTS, CorrelationExportComponent.MATRIX_PLOT)]
    assert [component.key for component in prepared.entries[0].components] == [
        "scatterplots",
        "matrix_plot",
    ]
    assert prepared.entries[0].components[0].charts[0].heading == "scatter"
    assert prepared.entries[0].components[1].charts[0].heading == "Correlation matrix"


def test_correlation_renderer_cannot_return_an_unselected_chart(monkeypatch) -> None:
    document = ReportDocument()
    document.upsert(_entry(AnalysisCategory.CORRELATION, correlation_snapshot(), ("matrix_plot",)))
    monkeypatch.setattr(
        "expo_jbm329.services.analysis.report.render_correlation_charts",
        lambda *_args, **_kwargs: (ExcelChartImage("unexpected", b"chart", 10, 10),),
    )

    with pytest.raises(ValueError, match="unselected chart"):
        prepare_report_content(document)


def test_cancelled_report_preparation_raises_compatible_exception(monkeypatch) -> None:
    document = ReportDocument()
    document.upsert(_entry(AnalysisCategory.PCA, pca_snapshot(), ("charts",)))
    monkeypatch.setattr(
        "expo_jbm329.services.analysis.report.render_pca_charts",
        lambda *_args, **_kwargs: pytest.fail("Cancellation should be checked before rendering"),
    )

    with pytest.raises(ExcelChartCancelledError):
        prepare_report_content(document, cancel_cb=lambda: True)


def test_empty_report_completes_progress_without_creating_entries() -> None:
    progress_values: list[int] = []

    prepared = prepare_report_content(ReportDocument(), progress_cb=progress_values.append)

    assert prepared.entries == ()
    assert progress_values == [100]


def test_prepared_report_content_rejects_malformed_table_and_components() -> None:
    with pytest.raises(ValueError, match="key, title, and headers"):
        PreparedReportTable("", "Table", ("Column",), ())
    with pytest.raises(ValueError, match="match the header count"):
        PreparedReportTable("table", "Table", ("Column", "Value"), (("only one",),))
    table = PreparedReportTable("table", "Table", ("Column",), ())
    with pytest.raises(ValueError, match="supported kind"):
        PreparedReportComponent("", "Table", "table", (table,))
    with pytest.raises(ValueError, match="one or more"):
        PreparedReportComponent("table", "Table", "table")
    PreparedReportComponent("table", "Table", "table", (table, table))
    with pytest.raises(ValueError, match="one or more"):
        PreparedReportComponent("table", "Table", "table", (table,), (ExcelChartImage("chart", b"png", 1, 1),))
    with pytest.raises(ValueError, match="chart images only"):
        PreparedReportComponent("chart", "Chart", "chart", tables=(table,))
    with pytest.raises(ValueError, match="chart images only"):
        PreparedReportComponent("chart", "Chart", "chart")
    with pytest.raises(ValueError, match="non-empty plain-text strings"):
        PreparedReportComponent("table", "Table", "table", (table,), paragraphs=("",))
    PreparedReportComponent("table", "Table", "table", (table,), paragraphs=("Explanation",))
    with pytest.raises(ValueError, match="chart images only"):
        PreparedReportComponent(
            "chart",
            "Chart",
            "chart",
            charts=(ExcelChartImage("chart", b"png", 1, 1),),
            paragraphs=("Explanation",),
        )
    with pytest.raises(ValueError, match="text content only"):
        PreparedReportComponent(
            "summary",
            "Summary",
            "table",
            overview_summary=PreparedOverviewSummary((), "Types", (), "Issues", ()),
            paragraphs=("Explanation",),
        )


def test_localized_report_tables_reject_duplicate_translated_table_titles() -> None:
    overview = analyze_dataset_overview(pd.DataFrame({"value": [1, 2]}))

    with pytest.raises(ValueError, match="titles must be unique"):
        localized_report_tables(
            AnalysisCategory.OVERVIEW,
            overview,
            ("Summary", "Columns"),
            translate=lambda _context, _text: "same title",
        )


def test_captured_report_options_fall_back_to_source_for_unknown_labels() -> None:
    options = capture_report_labels()

    assert options.translate("UnknownContext", "Unknown label") == "Unknown label"


def test_localized_report_tables_reject_category_snapshot_mismatch(monkeypatch) -> None:
    monkeypatch.setattr(
        "expo_jbm329.services.analysis.report.available_report_components",
        lambda *_args: (ReportComponent("feature_loadings", "Feature loadings", "table"),),
    )

    with pytest.raises(TypeError, match="category and applied report snapshot"):
        localized_report_tables(AnalysisCategory.PCA, linear_snapshot(), ("feature_loadings",))


def test_hypothesis_report_rejects_chi_square_snapshot_with_wrong_result() -> None:
    chi_square = chi_snapshot()
    malformed = object.__new__(HypothesisExportSnapshot)
    object.__setattr__(malformed, "test", HypothesisTest.CHI_SQUARE)
    object.__setattr__(malformed, "result", group_snapshot().result)
    object.__setattr__(malformed, "columns", chi_square.columns)
    object.__setattr__(malformed, "notes", ())

    with pytest.raises(TypeError, match="must contain a chi-square result"):
        localized_report_tables(AnalysisCategory.HYPOTHESIS_TESTS, malformed, ("summary",))


def test_chart_preparation_returns_empty_for_no_chart_components() -> None:
    assert (
        _render_entry_charts(
            AnalysisCategory.PCA,
            linear_snapshot(),
            (),
            translate=lambda _context, text: text,
            number_format=lambda value: str(value),
            count_format=str,
            progress_cb=None,
            cancel_cb=None,
        )
        == {}
    )


def test_chart_preparation_rejects_category_snapshot_mismatch() -> None:
    with pytest.raises(TypeError, match="category and applied report snapshot"):
        _render_entry_charts(
            AnalysisCategory.PCA,
            linear_snapshot(),
            ("charts",),
            translate=lambda _context, text: text,
            number_format=lambda value: str(value),
            count_format=str,
            progress_cb=None,
            cancel_cb=None,
        )


def test_empty_prepared_html_reports_completion_progress() -> None:
    progress: list[int] = []

    render_prepared_report_html(
        PreparedReportDocument("Empty", "", (), "N/A"),
        progress_cb=progress.append,
    )

    assert progress == [100]


def test_selected_chart_without_renderer_images_fails_explicitly(monkeypatch) -> None:
    document = ReportDocument()
    document.upsert(_entry(AnalysisCategory.PCA, pca_snapshot(), ("charts",)))
    monkeypatch.setattr(
        "expo_jbm329.services.analysis.report.render_pca_charts",
        lambda *_args, **_kwargs: (),
    )

    with pytest.raises(ValueError, match="produced no images"):
        prepare_report_content(document)


def test_chart_cancellation_from_existing_renderer_propagates(monkeypatch) -> None:
    document = ReportDocument()
    document.upsert(_entry(AnalysisCategory.PCA, pca_snapshot(), ("charts",)))

    def cancelled(*_args, **_kwargs):
        raise ExcelChartCancelledError

    monkeypatch.setattr("expo_jbm329.services.analysis.report.render_pca_charts", cancelled)

    with pytest.raises(ExcelChartCancelledError):
        prepare_report_content(document)


@pytest.mark.parametrize("with_warnings", [False, True])
def test_overview_summary_is_readable_text_with_view_facts_and_issues(with_warnings) -> None:
    frame = pd.DataFrame({
        "<measure>": [None, None, 3] if with_warnings else [1, 1, 3],
        "group": ["a", "a", "b"],
        "flag": [True, True, False],
        "date": pd.to_datetime(["2026-01-01", "2026-01-01", "2026-01-02"]),
    })
    result = analyze_dataset_overview(frame)
    document = ReportDocument(title="Overview")
    document.upsert(_entry(AnalysisCategory.OVERVIEW, result, ("Summary",)))

    prepared = prepare_report_content(document)
    component = prepared.entries[0].components[0]
    summary = component.overview_summary
    assert summary is not None
    assert dict(summary.facts)["Rows"] == "3"
    assert dict(summary.facts)["Columns"] == "4"
    assert (
        dict(summary.facts)["Missing values"]
        == f"{result.missing_cell_count} ({fmt_pct(result.missing_cell_fraction)})"
    )
    assert (
        dict(summary.facts)["Duplicate rows"]
        == f"{result.duplicate_row_count} ({fmt_pct(result.duplicate_row_fraction)})"
    )
    assert dict(summary.column_types) == {
        "Numeric columns": "1",
        "Categorical columns": "1",
        "Datetime columns": "1",
        "Boolean columns": "1",
        "Other columns": "0",
    }
    assert not component.tables
    html = render_prepared_report_html(prepared)
    assert "<table>" not in html
    assert '<dl class="overview-facts">' in html
    assert ".overview-facts { margin: .5rem 0; display: grid; gap: .4rem; }" in html
    assert "<h3>Summary</h3>" in html
    assert '<h3>Summary</h3>\n<div class="overview-summary">' in html
    assert ".overview-summary { border: 1px solid #ccd5df; padding: .75rem 1rem; }" in html
    assert "<h4>Dataset statistics</h4>" in html
    assert "<h4>Column types</h4>" in html
    assert "<h4>Potential issues</h4>" in html
    groups = html.split('<div class="overview-summary-groups">', 1)[1]
    assert groups.count('<div class="overview-summary-group">') == 2
    assert "</dl></div>\n</div>\n<h4>Potential issues</h4>" in groups
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in html
    assert ".overview-summary-groups { grid-template-columns: 1fr; gap: 0; }" in html
    if with_warnings:
        assert "&lt;measure&gt;" in html
        assert "missing values." in html
    else:
        assert "No issues detected." in html
    assert "Missing values" in html and "Duplicate rows" in html


def test_overview_empty_summary_localizes_text_and_preserves_export_table() -> None:
    result = analyze_dataset_overview(pd.DataFrame())
    document = ReportDocument()
    document.upsert(_entry(AnalysisCategory.OVERVIEW, result))
    options = capture_report_labels(lambda _context, text: f"Translated {text}")

    prepared = prepare_report_content(document, labels=options)
    html = render_prepared_report_html(prepared)

    assert "Translated Column types" in html
    assert "Translated Dataset statistics" in html
    assert "Translated No issues detected." in html
    assert "<strong>0</strong>" in html
    assert "<table>" not in html
    tables = localized_report_tables(AnalysisCategory.OVERVIEW, result, ("Summary",))
    assert tables["Summary"].shape[0] > 0


def test_overview_unselected_summary_keeps_columns_and_sample_as_tables() -> None:
    result = analyze_dataset_overview(pd.DataFrame({"value": [1, 2]}))
    document = ReportDocument()
    document.upsert(_entry(AnalysisCategory.OVERVIEW, result, ("Columns", "Sample")))
    html = render_report_html(document)

    assert html.count("<table>") == 3
    assert '<div class="overview-summary">' not in html


@pytest.mark.parametrize("localized", [False, True])
def test_overview_columns_metadata_has_one_visible_heading(localized: bool) -> None:
    result = analyze_dataset_overview(pd.DataFrame({"value": [1, 2]}))
    document = ReportDocument()
    entry = _entry(AnalysisCategory.OVERVIEW, result, ("Columns",))
    document.upsert(entry)
    label = "Localized metadata" if localized else "Columns metadata"
    calls: list[tuple[str, str]] = []

    def translate(context: str, text: str) -> str:
        calls.append((context, text))
        return label if (context, text) == ("OverviewView", "Columns metadata") else text

    options = capture_report_labels(translate)
    prepared = prepare_report_content(document, labels=options)
    component = prepared.entries[0].components[0]
    html = render_prepared_report_html(prepared)

    assert ("OverviewView", "Columns metadata") in calls
    assert entry.components[1].label == "Columns metadata"
    assert component.key == "Columns"
    assert component.label == component.tables[0].title == label
    assert html.count(f"<h3>{label}</h3>") == 1
    assert f'<caption class="visually-hidden">{label}</caption>' in html
    assert "<caption>Columns</caption>" not in html
    assert "<h3>Columns</h3>" not in html
    assert '<th scope="col">Column</th>' in html


def test_overview_sample_report_has_accessible_first_and_last_tables() -> None:
    frame = pd.DataFrame({"<literal name>": range(120), "label": [f"row-{i}" for i in range(120)]})
    result = analyze_dataset_overview(frame)
    document = ReportDocument(title="Overview sample")
    document.upsert(_entry(AnalysisCategory.OVERVIEW, result, ("Sample",)))

    prepared = prepare_report_content(document)
    component = prepared.entries[0].components[0]
    html = render_prepared_report_html(prepared)

    assert component.label == "Sample"
    assert [table.title for table in component.tables] == ["First (10)", "Last (10)"]
    assert component.tables[0].rows[0] == (0, "row-0")
    assert component.tables[1].rows[-1] == (119, "row-119")
    assert html.count("<h3>Sample</h3>") == 1
    assert html.count("<table>") == 2
    assert "<caption>First (10)</caption>" in html
    assert "<caption>Last (10)</caption>" in html
    assert '<th scope="col">&lt;literal name&gt;</th>' in html
    assert html.index("<caption>First (10)</caption>") < html.index("<caption>Last (10)</caption>")
    assert "<script" not in html
    exported = localized_report_tables(AnalysisCategory.OVERVIEW, result, ("Sample",))["Sample"]
    assert exported.shape == (20, 3)
    assert exported.iloc[-1, 1] == 119
    assert exported.iloc[-1, 0] == "Last (10)"


@pytest.mark.parametrize("split_samples", [False, True])
def test_localized_overview_sample_retains_literal_headers_and_safe_localized_group(split_samples):
    frame = pd.DataFrame({
        "Sample group": pd.Series(range(5), dtype="Int64"),
        "Urvalsgrupp": pd.Series(range(5), dtype="Int64"),
        "Urvalsgrupp (2)": pd.Series(range(5), dtype="Int64"),
        "column": pd.Series(["Column"] * 5, dtype="string"),
        "First (5)": pd.Series(range(5), dtype="Int64"),
    })
    translations = {
        "Sample": "Urval",
        "Sample group": "Urvalsgrupp",
        "First ({count})": "Första ({count})",
        "Last ({count})": "Sista ({count})",
        "Column": "Kolumn",
    }
    tables = localized_report_tables(
        AnalysisCategory.OVERVIEW,
        analyze_dataset_overview(frame),
        ("Sample",),
        translate=lambda _context, source: translations.get(source, source),
        split_overview_samples=split_samples,
    )
    if split_samples:
        assert list(tables) == ["Första (5)", "Sista (5)"]
        for table in tables.values():
            pd.testing.assert_frame_equal(table, frame)
    else:
        assert list(tables) == ["Urval"]
        combined = tables["Urval"]
        assert list(combined.columns) == ["Urvalsgrupp (3)", *frame.columns]
        assert combined.iloc[:, 0].tolist() == ["Första (5)"] * 5 + ["Sista (5)"] * 5
        assert combined.iloc[:, 0].dtype == pd.StringDtype()
        pd.testing.assert_frame_equal(combined.iloc[:5, 1:], frame)
        pd.testing.assert_frame_equal(combined.iloc[5:, 1:].reset_index(drop=True), frame)


def test_overview_sample_report_does_not_invent_tail_for_legacy_partial_snapshot() -> None:
    result = analyze_dataset_overview(pd.DataFrame({"value": range(120)}))
    legacy_result = replace(result, sample_last_rows=(), sample_last_frame=None)
    document = ReportDocument()
    document.upsert(_entry(AnalysisCategory.OVERVIEW, legacy_result, ("Sample",)))

    prepared = prepare_report_content(document)
    component = prepared.entries[0].components[0]
    html = render_prepared_report_html(prepared)

    assert len(component.tables) == 1
    assert component.tables[0].title == "First (10)"
    assert component.notice == "Last sample is unavailable in this captured result."
    assert "Last (10)" not in html
    assert "Last sample is unavailable in this captured result." in html


def test_report_sample_labels_are_captured_and_formatted_for_both_tables() -> None:
    options = capture_report_labels(lambda _context, text: f"Captured {text}", count_format=lambda n: f"count:{n}")
    document = ReportDocument()
    document.upsert(
        _entry(
            AnalysisCategory.OVERVIEW,
            analyze_dataset_overview(pd.DataFrame({"value": [1, 2]})),
            ("Sample",),
        )
    )

    prepared = prepare_report_content(document, labels=options)

    assert [table.title for table in prepared.entries[0].components[0].tables] == [
        "Captured First (count:2)",
        "Captured Last (count:2)",
    ]


def test_overview_report_columns_combine_missing_count_and_two_decimal_percentage() -> None:
    result = analyze_dataset_overview(pd.DataFrame({"value": [1, None, None], "complete": [1, 2, 3]}))
    document = ReportDocument()
    document.upsert(_entry(AnalysisCategory.OVERVIEW, result, ("Columns",)))

    prepared = prepare_report_content(
        document,
        translate=lambda _context, text: f"Localized {text}",
        count_format=lambda count: f"count:{count}",
    )
    table = prepared.entries[0].components[0].tables[0]

    assert table.headers == (
        "Localized Column",
        "Localized Type",
        "Localized Storage type",
        "Localized Missing",
        "Localized Unique",
    )
    assert table.rows[0][3] == f"count:2 ({fmt_pct(2 / 3, decimals=2)})"
    assert table.rows[1][3] == f"count:0 ({fmt_pct(0, decimals=2)})"
    exported = localized_report_tables(AnalysisCategory.OVERVIEW, result, ("Columns",))["Columns metadata"]
    assert exported["Missing"].tolist() == [2, 0]
    assert exported["Missing fraction"].tolist() == [2 / 3, 0]


def test_prepared_overview_summary_rejects_mixed_content() -> None:
    summary = PreparedOverviewSummary((), "Types", (), "Issues", ())
    with pytest.raises(ValueError, match="text content only"):
        PreparedReportComponent("summary", "Summary", "chart", overview_summary=summary)


def test_html_report_is_accessible_self_contained_and_escapes_plain_text() -> None:
    table = PreparedReportTable(
        "sample",
        "Values <table>",
        ("Name <script>", "Count", "Value", "Date", "Flag"),
        (
            (
                "<script>alert(1)</script>",
                1234,
                2.5,
                datetime(2024, 1, 2, 3, 4, tzinfo=UTC),
                True,
            ),
            ("line one\nline two", pd.NA, float("nan"), np.datetime64("NaT"), False),
        ),
    )
    image = ExcelChartImage("Chart <title>", b"\x89PNG", 200, 100, ("First line\nSecond line",))
    prepared = PreparedReportDocument(
        "<unsafe report>",
        "Description <em>not markup</em>",
        (
            PreparedReportEntry(
                "id",
                "Dataset <unsafe>",
                1234,
                3,
                "Statistics",
                "2025-03-04",
                "1.2.3",
                "Note <unsafe>\nsecond note",
                (
                    PreparedReportComponent(
                        "table",
                        "Table section",
                        "table",
                        tables=(table,),
                    ),
                    PreparedReportComponent(
                        "chart",
                        "Chart section",
                        "chart",
                        charts=(image,),
                    ),
                ),
            ),
        ),
        "N/A",
        ("Dataset label", "Date label", "Version label"),
    )

    html = render_prepared_report_html(
        prepared,
        number_format=lambda value: f"num:{value:g}",
        count_format=lambda value: f"count:{value}",
    )

    assert html.startswith("<!doctype html>")
    assert "<main" in html and "<article" in html and "<section" in html
    assert "<table><caption>Values &lt;table&gt;</caption>" in html
    assert '<th scope="col">Name &lt;script&gt;</th>' in html
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "count:1234" in html and "num:2.5" in html
    assert "<td>True</td>" in html
    assert "N/A" in html
    assert "line one\nline two" in html
    assert "Note &lt;unsafe&gt;\nsecond note" in html
    assert "Description &lt;em&gt;not markup&lt;/em&gt;" in html
    assert "Dataset &lt;unsafe&gt;" in html
    assert '<img src="data:image/png;base64,' in html
    assert 'alt="Chart &lt;title&gt;"' in html
    assert "First line\nSecond line" in html
    assert "Chart <title>" not in html
    assert "@media print" in html and "@media (max-width: 650px)" in html
    assert "td { white-space: pre-wrap; }" in html


@pytest.mark.parametrize(
    ("component_label", "content_title", "redundant"),
    [
        ("Summary", "Summary", True),
        ("Summary", " \nSUMMARY\t ", True),
        ("Sammanfattning", "sammanfattning", True),
        ("Summary", "Model summary", False),
        ("Summary", "Summary details", False),
        ("<Summary>", "<Summary>", True),
    ],
)
def test_report_hides_only_redundant_content_titles(component_label, content_title, redundant) -> None:
    from html import escape

    table = PreparedReportTable("summary", content_title, ("Value",), ((1,),))
    other_table = PreparedReportTable("details", "Distinct table", ("Value",), ((2,),))
    chart = ExcelChartImage(content_title, b"png", 80, 40, ("Keep this explanation.",))
    other_chart = ExcelChartImage("Distinct chart", b"other-png", 80, 40)
    document = PreparedReportDocument(
        "Report",
        "",
        (
            PreparedReportEntry(
                "id",
                "Dataset",
                2,
                1,
                "Overview",
                "2026-10-13",
                "1.0",
                "",
                (
                    PreparedReportComponent("summary", component_label, "table", tables=(table,)),
                    PreparedReportComponent("details", "Other table section", "table", tables=(other_table,)),
                    PreparedReportComponent("charts", component_label, "chart", charts=(chart, other_chart)),
                ),
            ),
        ),
        "N/A",
        ("Dataset", "Report date", "Version"),
    )

    html = render_prepared_report_html(document)

    hidden_class = ' class="visually-hidden"' if redundant else ""
    assert f"<h3>{escape(component_label)}</h3>" in html
    assert f"<caption{hidden_class}>{escape(content_title)}</caption>" in html
    assert f"<strong{hidden_class}>{escape(content_title)}</strong>" in html
    assert f'alt="{escape(content_title)}"' in html
    assert "<caption>Distinct table</caption>" in html
    assert "<strong>Distinct chart</strong>" in html
    assert "<p>Keep this explanation.</p>" in html
    assert ".visually-hidden {" in html
    assert "display: none" not in html


def test_render_report_html_renders_real_worker_chart_and_inline_png() -> None:
    snapshot = analyze_descriptive_statistics(pd.DataFrame({"value": [1.0, 2.0, 3.0, 4.0]}))
    document = ReportDocument(title="Statistics report", description="Real chart render")
    document.upsert(_entry(AnalysisCategory.STATISTICS, snapshot, ("Charts",)))
    progress_values: list[int] = []

    html = render_report_html(document, progress_cb=progress_values.append)

    assert '<img src="data:image/png;base64,' in html
    assert 'alt="value"' in html
    assert "Histogram and boxplot" not in html
    assert "<figcaption>" not in html
    assert "<strong>value</strong>" not in html
    assert "<h3>Distribution</h3>" in html
    assert "<h3>Charts</h3>" not in html
    assert progress_values == sorted(progress_values)
    assert progress_values[-1] == 100


def test_statistics_report_components_follow_table_then_distribution_order() -> None:
    snapshot = analyze_descriptive_statistics(pd.DataFrame({"value": [1.0, 2.0, 3.0], "group": ["a", "a", "b"]}))
    document = ReportDocument()
    document.upsert(create_report_entry(AnalysisCategory.STATISTICS, DATASET, snapshot))

    prepared = prepare_report_content(document)
    html = render_prepared_report_html(prepared)

    assert [component.label for component in prepared.entries[0].components] == [
        "Continuous",
        "Categorical",
        "Distribution",
    ]
    assert html.index("<h3>Continuous</h3>") < html.index("<h3>Categorical</h3>") < html.index("<h3>Distribution</h3>")


def test_statistics_continuous_cells_do_not_wrap_but_headers_and_other_tables_can() -> None:
    snapshot = analyze_descriptive_statistics(
        pd.DataFrame({"long variable name": [1.0, 2.0, 3.0], "group": ["long category name", "a", "b"]})
    )
    document = ReportDocument()
    document.upsert(_entry(AnalysisCategory.STATISTICS, snapshot, ("Continuous", "Categorical")))

    html = render_report_html(document)

    assert html.count('<table class="continuous-statistics">') == 1
    assert '<table><caption class="visually-hidden">Categorical</caption>' in html
    assert ".continuous-statistics td { white-space: nowrap; }" in html
    assert ".continuous-statistics th" not in html
    assert "td { white-space: pre-wrap; }" in html
    assert "<td>long variable name</td>" in html
    assert "<td>long category name</td>" in html


def test_statistics_html_combines_counts_and_percentages_without_changing_exports() -> None:
    snapshot = analyze_descriptive_statistics(
        pd.DataFrame({"value": [1.0, None, 3.0, 4.0], "group": ["a", "a", "b", None]})
    )
    document = ReportDocument()
    document.upsert(_entry(AnalysisCategory.STATISTICS, snapshot, ("Continuous", "Categorical")))
    options = capture_report_labels(
        lambda _context, text: f"Localized {text}",
        count_format=lambda count: f"count:{count}",
    )

    prepared = prepare_report_content(document, labels=options)
    continuous, categorical = (component.tables[0] for component in prepared.entries[0].components)
    continuous_row = dict(zip(continuous.headers, continuous.rows[0], strict=True))
    category_row = next(row for row in categorical.rows if row[:2] == ("group", "a"))
    categorical_row = dict(zip(categorical.headers, category_row, strict=True))

    assert "Localized Missing fraction" not in continuous.headers
    assert "Localized Missing fraction" not in categorical.headers
    assert "Localized Fraction (non-missing)" not in categorical.headers
    assert continuous_row["Localized Missing count"] == f"count:1 ({fmt_pct(1 / 4, decimals=2)})"
    assert categorical_row["Localized Missing count"] == f"count:1 ({fmt_pct(1 / 4, decimals=2)})"
    assert categorical_row["Localized Count (% non-missing)"] == f"count:2 ({fmt_pct(2 / 3, decimals=2)})"
    assert continuous_row["Localized Count"] == 3
    assert categorical_row["Localized Valid count"] == 3
    exports = localized_report_tables(AnalysisCategory.STATISTICS, snapshot, ("Continuous", "Categorical"))
    assert exports["Continuous"].iloc[0]["Missing count"] == 1
    assert exports["Continuous"].iloc[0]["Missing fraction"] == 1 / 4
    exported_category = (
        exports["Categorical"]
        .loc[(exports["Categorical"]["Column"] == "group") & (exports["Categorical"]["Category"] == "a")]
        .iloc[0]
    )
    assert exported_category["Count"] == 2
    assert exported_category["Fraction (non-missing)"] == 2 / 3


def test_statistics_html_omits_undefined_percentage_for_all_missing_category() -> None:
    snapshot = analyze_descriptive_statistics(pd.DataFrame({"group": pd.Series([None, None], dtype="string")}))
    document = ReportDocument()
    document.upsert(_entry(AnalysisCategory.STATISTICS, snapshot, ("Categorical",)))

    prepared = prepare_report_content(document)
    table = prepared.entries[0].components[0].tables[0]
    row = dict(zip(table.headers, table.rows[0], strict=True))

    assert row["Count (% non-missing)"] == "0"
    assert row["Missing count"] == f"2 ({fmt_pct(1.0, decimals=2)})"
    assert "nan%" not in render_prepared_report_html(prepared)


def test_statistics_distribution_label_is_shared_and_captured() -> None:
    snapshot = analyze_descriptive_statistics(pd.DataFrame({"value": [1.0, 2.0, 3.0, 4.0]}))
    document = ReportDocument()
    entry = _entry(AnalysisCategory.STATISTICS, snapshot, ("Charts",))
    document.upsert(entry)
    calls: list[tuple[str, str]] = []

    def translate(context: str, text: str) -> str:
        calls.append((context, text))
        return "Localized distribution" if (context, text) == ("StatisticsView", "Distribution") else text

    options = capture_report_labels(translate)
    prepared = prepare_report_content(document, labels=options)
    component = prepared.entries[0].components[0]
    html = render_prepared_report_html(prepared)

    assert ("StatisticsView", "Distribution") in calls
    assert next(item.label for item in entry.components if item.key == "Charts") == "Distribution"
    assert component.key == "Charts"
    assert component.label == "Localized distribution"
    assert component.charts
    assert "<h3>Localized distribution</h3>" in html
    assert "<h3>Charts</h3>" not in html


def test_correlation_report_uses_shared_configured_title_summary_and_semantic_heading():
    frame = pd.DataFrame({
        "<Age & income>": [1.0, 2.0, 3.0, 4.0],
        "Score": [4.0, 3.0, 2.0, 1.0],
    })
    matrix = analyze_correlation_matrix(frame, tuple(frame.columns), CorrelationMethod.SPEARMAN)
    assert matrix is not None
    snapshot = CorrelationExportSnapshot(matrix, frame.copy(deep=True))
    entry = create_report_entry(AnalysisCategory.CORRELATION, DATASET, snapshot).with_selection(
        ("strongest_correlations",),
        "",
    )
    document = ReportDocument()
    document.upsert(entry)

    prepared = prepare_report_content(document)
    html = render_prepared_report_html(prepared)

    assert prepared.entries[0].title == "Correlation — Spearman"
    assert prepared.entries[0].configuration[0].items == ("<Age & income>", "Score")
    assert "<h2>Correlation — Spearman</h2>" in html
    assert "<dt>Columns:</dt><dd>&lt;Age &amp; income&gt;, Score</dd>" in html
    assert "<h3>Strongest correlations</h3>" in html


def test_univariate_outlier_html_uses_shared_title_roles_and_escaped_long_column_names():
    column = "<sensor & reading>" + "_measurement" * 20
    frame = pd.DataFrame({column: [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 100.0]})
    summary = analyze_outlier_summary(frame)
    detail = analyze_outlier_column(frame, column, summary.method, summary.threshold)
    snapshot = UnivariateOutlierExportSnapshot(
        summary,
        frame.loc[:, list(summary.available_columns)].copy(deep=True),
        HISTOGRAM_LABELS,
        detail=detail,
    )
    document = ReportDocument()
    document.upsert(_entry(AnalysisCategory.OUTLIERS, snapshot, ("column_summary",)))
    labels = capture_report_labels(
        lambda context, source: (
            source
            if source == "{category} — {method}"
            else f"sv:{source}"
            if context == "OutliersPresentation"
            else source
        )
    )

    prepared = prepare_report_content(document, labels=labels)
    prepared_entry = prepared.entries[0]
    html = render_prepared_report_html(prepared)
    localized_tables = localized_report_tables(
        AnalysisCategory.OUTLIERS,
        snapshot,
        ("column_summary",),
        labels=labels,
    )

    assert prepared_entry.title == "sv:Outliers — sv:IQR (Tukey's fences)"
    assert prepared_entry.configuration[0].label == "sv:IQR multiplier:"
    assert prepared_entry.configuration[1].items == (column,)
    assert prepared_entry.configuration[2].display_value == column
    assert prepared_entry.components[0].label == "sv:Column summary"
    assert prepared_entry.components[0].tables[0].title == "sv:Column summary"
    assert tuple(localized_tables) == (prepared_entry.components[0].tables[0].title,)
    assert f"<dd>{escape(column)}</dd>" in html
    assert f"<dd>{column}</dd>" not in html


def test_outlier_report_hides_empty_status_and_notes_rows_but_preserves_export_schema():
    frame = pd.DataFrame({"screened": np.arange(10, dtype=float)})
    summary = analyze_outlier_summary(frame)
    notes = tuple(f"Summary note {index}" for index in range(30))
    snapshot = UnivariateOutlierExportSnapshot(
        summary,
        frame.copy(deep=True),
        HISTOGRAM_LABELS,
        summary_notes=notes,
    )
    document = ReportDocument()
    document.upsert(_entry(AnalysisCategory.OUTLIERS, snapshot, ("column_summary",)))

    prepared_component = prepare_report_content(document).entries[0].components[0]
    html = render_prepared_report_html(prepare_report_content(document))
    public_table = outlier_column_summary_table(snapshot)
    localized_export = localized_report_tables(
        AnalysisCategory.OUTLIERS,
        snapshot,
        ("column_summary",),
    )["Column summary"]

    assert prepared_component.tables[0].headers == (
        "Column",
        "Values",
        "Missing",
        "Outliers",
        "Share",
        "Low",
        "High",
        "Lower fence",
        "Upper fence",
    )
    assert len(prepared_component.tables[0].rows) == 1
    assert prepared_component.paragraphs == notes
    assert "notes" in public_table.columns
    assert "status" in public_table.columns
    assert public_table["values"].dtype == pd.Int64Dtype()
    assert public_table["missing"].dtype == pd.Int64Dtype()
    assert public_table["share"].dtype == "float64"
    assert public_table["status"].dtype == pd.StringDtype()
    assert public_table["notes"].dtype == pd.StringDtype()
    assert "Notes" in localized_export.columns
    assert "Status" in localized_export.columns
    assert len(localized_export) == len(notes)
    assert html.index("</table></div>") < html.index("Summary note 0")


def test_outlier_report_keeps_both_unscreened_statuses_and_actual_columns():
    frame = pd.DataFrame({
        "screened": np.arange(10, dtype=float),
        "few": [1.0, 2.0, *([None] * 8)],
        "flat": [5.0] * 10,
    })
    summary = analyze_outlier_summary(frame, OutlierMethod.Z_SCORE)
    snapshot = UnivariateOutlierExportSnapshot(
        summary,
        frame.copy(deep=True),
        HISTOGRAM_LABELS,
        summary_notes=tuple(f"Screening note {index}" for index in range(10)),
    )
    document = ReportDocument()
    document.upsert(_entry(AnalysisCategory.OUTLIERS, snapshot, ("column_summary",)))

    labels = capture_report_labels(
        lambda context, source: {
            ("OutliersView", "Too few values"): "Too few (localized)",
            ("OutliersView", "No spread"): "No spread (localized)",
        }.get((context, source), source)
    )
    table = prepare_report_content(document, labels=labels).entries[0].components[0].tables[0]
    status_index = table.headers.index("Status")
    column_index = table.headers.index("Column")
    rows = {row[column_index]: row for row in table.rows}

    assert len(table.rows) == 3
    assert pd.isna(rows["screened"][status_index])
    assert rows["few"][status_index] == "Too few (localized)"
    assert rows["flat"][status_index] == "No spread (localized)"
    assert "Notes" not in table.headers


def test_outlier_report_omits_notes_without_notes_and_preserves_detail_nan_metrics():
    base = univariate_snapshot(summary_notes=(), detail_notes=())
    assert base.detail is not None
    detail = replace(base.detail, q1=float("nan"))
    notes = tuple(f"Detail note {index}" for index in range(30))
    snapshot = replace(base, detail=detail, detail_notes=notes)
    document = ReportDocument()
    document.upsert(_entry(AnalysisCategory.OUTLIERS, snapshot, ("column_details",)))

    prepared_component = prepare_report_content(document).entries[0].components[0]
    localized_export = localized_report_tables(
        AnalysisCategory.OUTLIERS,
        snapshot,
        ("column_details",),
    )["Model summary"]
    public_table = outlier_column_details_table(snapshot)
    metric_index = prepared_component.tables[0].headers.index("Metric")
    value_index = prepared_component.tables[0].headers.index("Value")
    q1 = next(row for row in prepared_component.tables[0].rows if row[metric_index] == "Q1")

    assert len(prepared_component.tables[0].rows) == public_table["metric"].notna().sum()
    assert len(prepared_component.paragraphs) == len(notes)
    assert pd.isna(q1[value_index])
    assert "Notes" not in prepared_component.tables[0].headers
    assert "Notes" in localized_export.columns
    assert "notes" in public_table.columns

    no_notes = replace(base, detail_notes=())
    no_notes_document = ReportDocument()
    no_notes_document.upsert(_entry(AnalysisCategory.OUTLIERS, no_notes, ("column_details",)))
    no_notes_component = prepare_report_content(no_notes_document).entries[0].components[0]
    assert no_notes_component.paragraphs == ()
    assert len(no_notes_component.tables[0].rows) == outlier_column_details_table(no_notes)["metric"].notna().sum()


def test_outlier_summary_and_detail_notes_are_escaped_and_follow_their_tables():
    snapshot = univariate_snapshot(
        summary_notes=("<summary & note>\ncontinued", "Second summary note"),
        detail_notes=("<detail & note>\ncontinued", "Second detail note"),
    )
    document = ReportDocument()
    document.upsert(_entry(AnalysisCategory.OUTLIERS, snapshot, ("column_summary", "column_details")))

    labels = capture_report_labels(
        lambda context, source: f"sv:{source}" if context == "OutliersPresentation" else source
    )
    prepared = prepare_report_content(document, labels=labels)
    components = prepared.entries[0].components
    html = render_prepared_report_html(prepared)

    assert components[0].paragraphs == snapshot.summary_notes
    assert components[1].label == "sv:Model summary"
    assert components[1].paragraphs == snapshot.detail_notes
    assert html.index("<h3>sv:Column summary</h3>") < html.index("&lt;summary &amp; note&gt;")
    assert html.index("</table></div>", html.index("<h3>sv:Column summary</h3>")) < html.index(
        "&lt;summary &amp; note&gt;"
    )
    assert html.index("<h3>sv:Model summary</h3>") < html.index("&lt;detail &amp; note&gt;")
    assert html.index("</table></div>", html.index("<h3>sv:Model summary</h3>")) < html.index(
        "&lt;detail &amp; note&gt;"
    )
    assert "Notes" not in components[0].tables[0].headers
    assert "Notes" not in components[1].tables[0].headers


def test_multivariate_outlier_notes_follow_model_summary_without_notes_only_rows():
    base = multivariate_snapshot()
    notes = tuple(f"Model note {index}" for index in range(30))
    snapshot = replace(base, notes=notes)
    document = ReportDocument()
    document.upsert(_entry(AnalysisCategory.OUTLIERS, snapshot, ("model_summary",)))

    prepared_component = prepare_report_content(document).entries[0].components[0]
    html = render_prepared_report_html(prepare_report_content(document))
    public_table = outlier_model_summary_table(snapshot)

    assert prepared_component.label == "Model summary"
    assert prepared_component.paragraphs == notes
    assert len(prepared_component.tables[0].rows) == public_table["metric"].notna().sum()
    assert "Notes" not in prepared_component.tables[0].headers
    assert "notes" in public_table.columns
    assert html.index("</table></div>") < html.index("Model note 0")


def test_outlier_notes_follow_component_selection_and_do_not_attach_to_other_content():
    snapshot = univariate_snapshot(
        summary_notes=("Summary component note",),
        detail_notes=("Detail component note",),
    )
    entry = _entry(AnalysisCategory.OUTLIERS, snapshot).with_selection(
        ("potential_outliers", "charts"),
        "Entry note",
    )
    document = ReportDocument()
    document.upsert(entry)

    prepared = prepare_report_content(document)
    components = prepared.entries[0].components
    html = render_prepared_report_html(prepared)

    assert [component.label for component in components] == ["Potential outliers", "Column distributions"]
    assert all(component.paragraphs == () for component in components)
    assert "Summary component note" not in html
    assert "Detail component note" not in html
    assert html.count("Entry note") == 1


def test_multivariate_outlier_chart_heading_is_shared_by_report_and_export():
    snapshot = multivariate_snapshot()
    document = ReportDocument()
    document.upsert(_entry(AnalysisCategory.OUTLIERS, snapshot, ("charts",)))
    options = capture_report_labels(
        lambda context, source: f"sv:{source}" if context == "OutliersPresentation" else source
    )

    prepared = prepare_report_content(document, labels=options)

    component = prepared.entries[0].components[0]
    html = render_prepared_report_html(prepared)
    assert component.label == "sv:Outlier projection"
    assert component.charts[0].heading == "Outlier projection"
    assert "<h3>sv:Outlier projection</h3>" in html


def test_correlation_ranking_explanation_is_below_table_and_exports_are_unchanged():
    snapshot = correlation_snapshot()
    document = ReportDocument()
    document.upsert(_entry(AnalysisCategory.CORRELATION, snapshot, ("strongest_correlations",)))
    source = (
        "Pairs are ranked by absolute coefficient. Significance is based on "
        "p < {alpha} after Holm adjustment for {count} tests."
    )

    def translate(_context: str, text: str) -> str:
        return f"<Explanation>\n{text}" if text == source else text

    options = capture_report_labels(
        translate,
        number_format=lambda value: f"number:{value}",
        count_format=lambda value: f"count:{value}",
    )
    exported = localized_report_tables(
        AnalysisCategory.CORRELATION, snapshot, ("strongest_correlations",), labels=options
    )
    export_frame = next(iter(exported.values()))
    explanation = export_frame["Ranking and Holm explanation"].iloc[0]

    prepared = prepare_report_content(document, labels=options)
    component = prepared.entries[0].components[0]
    table = component.tables[0]
    html = render_prepared_report_html(prepared)

    assert "Ranking and Holm explanation" not in table.headers
    assert len(table.rows) == len(snapshot.matrix.pairs)
    assert component.paragraphs == (explanation,)
    assert f"count:{len(snapshot.matrix.pairs)} tests" in explanation
    assert export_frame["Ranking and Holm explanation"].tolist() == [explanation] * len(snapshot.matrix.pairs)
    assert html.count("&lt;Explanation&gt;") == 1
    assert html.index("</table>") < html.index('<div class="report-paragraphs">')
    assert "p &lt; number:" in html

    document = ReportDocument()
    document.upsert(_entry(AnalysisCategory.CORRELATION, snapshot, ("matrix_plot",)))
    chart_only = prepare_report_content(document)
    assert chart_only.entries[0].components[0].paragraphs == ()


def test_correlation_presentation_labels_are_captured_before_report_preparation():
    entry = _entry(
        AnalysisCategory.CORRELATION,
        correlation_snapshot(),
        ("strongest_correlations",),
    )
    document = ReportDocument()
    document.upsert(entry)
    translations = {
        "Correlation": "Korrelation",
        "Columns:": "Kolumner:",
        "Strongest correlations": "Starkaste korrelationer",
    }
    options = capture_report_labels(
        lambda context, source: translations.get(source, source) if context == "CorrelationView" else source
    )

    prepared = prepare_report_content(document, labels=options)

    assert prepared.entries[0].title == "Korrelation — Pearson"
    assert prepared.entries[0].configuration[0].label == "Kolumner:"
    assert prepared.entries[0].components[0].label == "Starkaste korrelationer"


def test_report_html_lists_all_captured_datasets_in_header() -> None:
    first_dataset = DatasetRef("first-tab", "Employees", 12, 3)
    second_dataset = DatasetRef("second-tab", "Orders", 25, 5)
    document = ReportDocument(title="Mixed datasets")
    overview = analyze_dataset_overview(pd.DataFrame({"employee": ["A", "B"]}))
    document.upsert(
        create_report_entry(AnalysisCategory.OVERVIEW, first_dataset, overview).with_selection(("Summary",), "")
    )
    document.upsert(
        create_report_entry(AnalysisCategory.PCA, second_dataset, pca_snapshot()).with_selection(
            ("explained_variance",), ""
        )
    )

    html = render_report_html(document)

    assert "<dt>Dataset</dt><dd>Employees, Orders</dd>" in html.split("</header>", 1)[0]
    assert html.count('<article class="analysis-entry">') == 2
    assert ">12</dd>" not in html and ">25</dd>" not in html
    assert ">3</dd>" not in html and ">5</dd>" not in html


def test_captured_report_labels_freeze_translation_before_worker_render() -> None:
    language = {"prefix": "Captured"}
    translation_calls: list[tuple[str, str]] = []

    def translate(context: str, text: str) -> str:
        translation_calls.append((context, text))
        return f"{language['prefix']} {text}"

    options = capture_report_labels(
        translate,
        number_format=lambda value: f"n{value:g}",
        count_format=lambda value: f"i{value}",
    )
    captured_call_count = len(translation_calls)
    language["prefix"] = "Changed"
    document = ReportDocument(title="Frozen labels")
    document.upsert(
        _entry(
            AnalysisCategory.OVERVIEW,
            analyze_dataset_overview(pd.DataFrame({"measure": [1, 2]})),
            ("Summary",),
        )
    )

    html = render_report_html(document, labels=options)

    assert "Captured Summary" in html
    assert "Changed Summary" not in html
    assert len(translation_calls) == captured_call_count
    assert options.count_format(1200) == "i1200"
    assert options.number_format(1.25) == "n1.25"


def test_captured_options_can_localize_export_tables_with_report_keys() -> None:
    snapshot = correlation_snapshot()
    language = {"prefix": "Captured"}
    options = capture_report_labels(
        lambda _context, text: f"{language['prefix']} {text}",
        number_format=lambda value: f"number:{value:g}",
        count_format=lambda value: f"count:{value}",
    )
    language["prefix"] = "Changed"

    tables = localized_report_tables(
        AnalysisCategory.CORRELATION,
        snapshot,
        ("strongest_correlations",),
        labels=options,
    )

    assert "Captured Strongest correlations" in tables
    frame = next(iter(tables.values()))
    assert "Captured Variable 1" in frame.columns
    assert frame.iloc[0]["Captured Ranking and Holm explanation"].startswith("Captured Pairs are ranked")


def test_prepared_report_html_supports_cooperative_cancellation() -> None:
    prepared = PreparedReportDocument(
        "Report",
        "",
        (
            PreparedReportEntry(
                "entry",
                "Dataset",
                1,
                1,
                "Overview",
                "2025-01-01",
                "1.0",
                "",
                (),
            ),
        ),
        "N/A",
    )

    with pytest.raises(ExcelChartCancelledError):
        render_prepared_report_html(prepared, cancel_cb=lambda: True)


def test_localized_tables_reject_unavailable_or_duplicate_component_keys() -> None:
    snapshot = irregular_snapshot()

    with pytest.raises(ValueError, match="distinct available"):
        localized_report_tables(
            AnalysisCategory.TIME_SERIES,
            snapshot,
            ("autocorrelation",),
        )
    with pytest.raises(ValueError, match="distinct available"):
        localized_report_tables(
            AnalysisCategory.TIME_SERIES,
            snapshot,
            ("series", "series"),
        )
