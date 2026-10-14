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
from expo_jbm329.services.analysis.correlation import CorrelationMethod, analyze_correlation_matrix
from expo_jbm329.services.analysis.correlation_export import CorrelationExportComponent, CorrelationExportSnapshot
from expo_jbm329.services.analysis.group_comparison import analyze_group_comparison
from expo_jbm329.services.analysis.hypothesis_export import (
    HypothesisExportComponent,
    HypothesisExportSnapshot,
    hypothesis_export_tables,
)
from expo_jbm329.services.analysis.overview import analyze_dataset_overview
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
from expo_jbm329.services.excel_chart import ExcelChartCancelledError, ExcelChartImage
from expo_jbm329.utils.dataset_ref import DatasetRef
from expo_jbm329.utils.format_utils import fmt_pct
from tests.analysis.test_clustering_export import clustering_snapshot
from tests.analysis.test_correlation_export import _snapshot as correlation_snapshot
from tests.analysis.test_hypothesis_export import chi_snapshot, group_snapshot, paired_snapshot
from tests.analysis.test_outliers_export import multivariate_snapshot, univariate_snapshot
from tests.analysis.test_pca_export import pca_snapshot
from tests.analysis.test_regression_export import (
    cox_snapshot,
    linear_snapshot,
    logistic_snapshot,
    negative_binomial_snapshot,
    poisson_snapshot,
)
from tests.analysis.test_timeseries_export import irregular_snapshot, time_series_snapshot

if TYPE_CHECKING:
    from collections.abc import Callable

DATASET = DatasetRef("report-tab", "Report sample", 40, 4)


def _entry(category: AnalysisCategory, snapshot: object, selection: tuple[str, ...] | None = None):
    entry = create_report_entry(category, DATASET, snapshot)
    if selection is None:
        return entry
    return entry.with_selection(selection, entry.note)


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

    assert prepared.entries[0].title == "sv:Hypothesis Tests — sv:Friedman"
    assert prepared.entries[0].configuration[0].label == "sv:Measurement variables (selected order):"
    assert prepared.entries[0].components[0].label == "sv:Measurement summary"
    assert prepared.entries[0].components[0].tables[0].title == "sv:Measurement summary"


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
    assert tuple(component.label for component in prepared_entry.components) == ("sv:Coefficients", "sv:Model metrics")
    assert table_titles == tuple(export_tables)
    assert all(name.startswith("sv:") for name in export_tables)
    assert "sv:Predictors:" in html
    assert any(component.label == chart_label for component in entry.components)
    assert snapshot.model is model


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
    assert prepared.entries[1].components[1].charts
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
    exported = localized_report_tables(AnalysisCategory.OVERVIEW, result, ("Columns",))["Columns"]
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
    assert "Histogram and boxplot" in html
    assert progress_values == sorted(progress_values)
    assert progress_values[-1] == 100


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
    assert "<script>" not in html


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
