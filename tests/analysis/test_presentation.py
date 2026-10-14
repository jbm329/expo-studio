from __future__ import annotations

from dataclasses import replace

import pytest

from expo_jbm329.services.analysis.categories import AnalysisCategory
from expo_jbm329.services.analysis.correlation import CorrelationMethod
from expo_jbm329.services.analysis.correlation_export import CorrelationExportSnapshot
from expo_jbm329.services.analysis.hypothesis_export import HypothesisExportComponent
from expo_jbm329.services.analysis.presentation import (
    AnalysisPresentation,
    ConfigurationField,
    PresentationLabel,
    build_analysis_presentation,
    build_correlation_presentation,
    hypothesis_component_label,
    presentation_label_source,
)
from tests.analysis.test_correlation_export import _snapshot as correlation_snapshot
from tests.analysis.test_hypothesis_export import chi_snapshot, group_snapshot, paired_snapshot
from tests.analysis.test_pca_export import pca_snapshot


@pytest.mark.parametrize(
    ("method", "name"),
    [
        (CorrelationMethod.PEARSON, "Pearson"),
        (CorrelationMethod.SPEARMAN, "Spearman"),
        (CorrelationMethod.KENDALL, "Kendall's tau-b"),
    ],
)
def test_correlation_presentation_uses_configured_title_and_ordered_columns(method, name):
    base = correlation_snapshot()
    snapshot = CorrelationExportSnapshot(replace(base.matrix, method=method), base.matrix_data.copy(deep=True))
    translations = {
        "Correlation": "Korrelation",
        "{category} — {method}": "{category} — {method}",
        "Columns:": "Kolumner:",
        name: name,
    }
    calls: list[tuple[str, str]] = []

    def translate(context: str, source: str) -> str:
        calls.append((context, source))
        return translations.get(source, source)

    presentation = build_analysis_presentation(AnalysisCategory.CORRELATION, snapshot, translate)

    assert presentation.category == "Korrelation"
    assert presentation.title == f"Korrelation — {name}"
    assert len(presentation.configuration) == 1
    assert presentation.configuration[0].label == "Kolumner:"
    assert presentation.configuration[0].items == snapshot.matrix.columns
    assert presentation.configuration[0].display_value == ", ".join(snapshot.matrix.columns)
    assert presentation.summary_lines == (f"Kolumner: {', '.join(snapshot.matrix.columns)}",)
    assert calls
    assert {context for context, _source in calls} == {"CorrelationView"}


def test_correlation_semantic_labels_have_one_translation_source_context():
    for key in (
        PresentationLabel.CORRELATION,
        PresentationLabel.CONFIGURED_TITLE,
        PresentationLabel.COLUMNS,
        PresentationLabel.STRONGEST_CORRELATIONS,
        PresentationLabel.CORRELATION_PLOTS,
        PresentationLabel.CORRELATION_MATRIX,
        PresentationLabel.SCATTERPLOTS,
        PresentationLabel.PEARSON,
        PresentationLabel.SPEARMAN,
        PresentationLabel.KENDALL,
        PresentationLabel.SCATTERPLOT_TITLE,
    ):
        context, source = presentation_label_source(key)
        assert context == "CorrelationView"
        assert source


@pytest.mark.parametrize(
    ("snapshot_factory", "expected_title", "expected_summary"),
    [
        (
            lambda: group_snapshot(2),
            "Hypothesis Tests — Group comparison",
            (
                "Numeric variable: Value",
                "Grouping variable: Group",
                "Tests computed: Welch's t-test, Student's t-test, Mann-Whitney U",
            ),
        ),
        (
            lambda: group_snapshot(3),
            "Hypothesis Tests — Group comparison",
            (
                "Numeric variable: Value",
                "Grouping variable: Group",
                "Tests computed: One-way ANOVA, Kruskal-Wallis",
            ),
        ),
        (
            chi_snapshot,
            "Hypothesis Tests — Categorical association",
            (
                "Row variable: Row",
                "Column variable: Column",
                "Tests available: Pearson's chi-square test, Fisher's exact test",
            ),
        ),
        (
            lambda: chi_snapshot(3),
            "Hypothesis Tests — Categorical association",
            (
                "Row variable: Row",
                "Column variable: Column",
                "Tests available: Pearson's chi-square test",
            ),
        ),
        (
            paired_snapshot,
            "Hypothesis Tests — Wilcoxon signed-rank",
            ("Measurement variables (selected order): Time 1, Time 0",),
        ),
        (
            lambda: paired_snapshot(3),
            "Hypothesis Tests — Friedman",
            ("Measurement variables (selected order): Time 2, Time 1, Time 0",),
        ),
    ],
)
def test_hypothesis_presentation_uses_applied_roles_and_computed_methods(
    snapshot_factory,
    expected_title,
    expected_summary,
):
    calls: list[tuple[str, str]] = []

    def translate(context: str, source: str) -> str:
        calls.append((context, source))
        return source

    snapshot = snapshot_factory()
    presentation = build_analysis_presentation(AnalysisCategory.HYPOTHESIS_TESTS, snapshot, translate)

    assert presentation.category == "Hypothesis Tests"
    assert presentation.title == expected_title
    assert presentation.summary_lines == expected_summary
    assert {context for context, _source in calls} == {"HypothesisPresentation"}


@pytest.mark.parametrize(
    ("snapshot", "component", "expected"),
    [
        (group_snapshot(), HypothesisExportComponent.SUMMARY, "Group summary"),
        (chi_snapshot(), HypothesisExportComponent.SUMMARY, "Contingency table"),
        (paired_snapshot(), HypothesisExportComponent.SUMMARY, "Measurement summary"),
        (group_snapshot(), HypothesisExportComponent.CHARTS, "Group distributions"),
        (chi_snapshot(), HypothesisExportComponent.CHARTS, "Association plots"),
        (paired_snapshot(), HypothesisExportComponent.CHARTS, "Paired measurement plots"),
        (group_snapshot(), HypothesisExportComponent.TEST_RESULTS, "Test results"),
    ],
)
def test_hypothesis_component_headings_share_semantic_translation(snapshot, component, expected):
    assert hypothesis_component_label(snapshot, component, lambda _context, text: text) == expected


def test_other_category_presentation_deliberately_keeps_category_only_fallback():
    calls: list[tuple[str, str]] = []

    def translate(context: str, source: str) -> str:
        calls.append((context, source))
        return f"translated {source}"

    presentation = build_analysis_presentation(AnalysisCategory.PCA, pca_snapshot(), translate)

    assert presentation.category == "translated PCA"
    assert presentation.title == "translated PCA"
    assert presentation.configuration == ()
    assert calls == [("AnalysisDialog", "PCA")]


def test_correlation_presentation_rejects_mismatched_snapshot():
    with pytest.raises(TypeError, match="Correlation presentation"):
        build_analysis_presentation(AnalysisCategory.CORRELATION, pca_snapshot(), lambda _context, source: source)


@pytest.mark.parametrize(("label", "items"), [("", ("value",)), ("Columns:", ())])
def test_configuration_fields_require_a_label_and_values(label, items):
    with pytest.raises(ValueError, match="requires a label"):
        ConfigurationField(label, items)


@pytest.mark.parametrize(("category", "title"), [("", "Title"), ("Correlation", "")])
def test_analysis_presentation_requires_category_and_title(category, title):
    with pytest.raises(ValueError, match="requires a category"):
        AnalysisPresentation(category, title)


def test_correlation_presentation_requires_applied_columns():
    with pytest.raises(ValueError, match="requires applied columns"):
        build_correlation_presentation(
            CorrelationMethod.PEARSON,
            (),
            lambda _context, source: source,
        )
