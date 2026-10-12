from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from expo_jbm329.services.analysis.categories import AnalysisCategory, HypothesisTest
from expo_jbm329.services.analysis.clustering import ClusteringMethod
from expo_jbm329.services.analysis.correlation_export import CorrelationExportComponent
from expo_jbm329.services.analysis.hypothesis_export import HypothesisExportSnapshot
from expo_jbm329.services.analysis.overview import analyze_dataset_overview
from expo_jbm329.services.analysis.report import (
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
    assert prepared.entries[0].components[0].tables[0].rows
    assert prepared.entries[1].components[1].charts
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
    assert prepared.entries[0].components[1].charts[0].heading == "Pearson correlation"


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
    with pytest.raises(ValueError, match="exactly one"):
        PreparedReportComponent("table", "Table", "table")
    with pytest.raises(ValueError, match="chart images only"):
        PreparedReportComponent("chart", "Chart", "chart", tables=(table,))
    with pytest.raises(ValueError, match="chart images only"):
        PreparedReportComponent("chart", "Chart", "chart")


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
        ("Dataset label", "Rows label", "Columns label", "Date label", "Version label"),
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


def test_report_html_keeps_mixed_dataset_entries_distinct() -> None:
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

    assert "Employees" in html and "Orders" in html
    assert ">12</dd>" in html and ">25</dd>" in html
    assert ">3</dd>" in html and ">5</dd>" in html


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
