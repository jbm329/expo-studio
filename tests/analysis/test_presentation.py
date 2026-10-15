from __future__ import annotations

from dataclasses import replace

import pytest

from expo_jbm329.services.analysis.categories import AnalysisCategory
from expo_jbm329.services.analysis.correlation import CorrelationMethod
from expo_jbm329.services.analysis.correlation_export import CorrelationExportSnapshot
from expo_jbm329.services.analysis.hypothesis_export import HypothesisExportComponent
from expo_jbm329.services.analysis.multivariate_outliers import MultivariateOutlierMethod
from expo_jbm329.services.analysis.outliers import OutlierMethod
from expo_jbm329.services.analysis.outliers_export import OutlierExportComponent
from expo_jbm329.services.analysis.presentation import (
    AnalysisPresentation,
    ConfigurationField,
    PresentationLabel,
    build_analysis_presentation,
    build_correlation_presentation,
    hypothesis_component_label,
    outlier_component_label,
    presentation_label_source,
    regression_component_label,
)
from expo_jbm329.services.analysis.regression_export import RegressionExportComponent
from expo_jbm329.services.analysis.regression_glm import RegressionModel
from expo_jbm329.utils.format_utils import fmt_num, fmt_pct
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


@pytest.mark.parametrize(
    ("factory", "model", "model_name", "outcome_fields", "predictors"),
    [
        (linear_snapshot, RegressionModel.LINEAR, "Linear regression", ("Outcome: y",), "Predictors: x, g"),
        (logistic_snapshot, RegressionModel.LOGISTIC, "Logistic regression", ("Outcome: binary",), "Predictors: x"),
        (poisson_snapshot, RegressionModel.POISSON, "Poisson regression", ("Outcome: count",), "Predictors: x"),
        (
            negative_binomial_snapshot,
            RegressionModel.NEGATIVE_BINOMIAL,
            "Negative binomial regression",
            ("Outcome: count",),
            "Predictors: x",
        ),
        (
            cox_snapshot,
            RegressionModel.COX,
            "Cox proportional-hazards regression",
            ("Duration: duration", "Event: event"),
            "Predictors: x, group",
        ),
    ],
)
def test_regression_presentation_exposes_model_roles_predictors_terms_and_references(
    factory,
    model,
    model_name,
    outcome_fields,
    predictors,
):
    calls: list[tuple[str, str]] = []

    def translate(context: str, source: str) -> str:
        calls.append((context, source))
        return source

    snapshot = factory()
    presentation = build_analysis_presentation(AnalysisCategory.REGRESSION, snapshot, translate)

    assert presentation.category == "Regression"
    assert presentation.title == f"Regression — {model_name}"
    assert presentation.summary_lines[: len(outcome_fields)] == outcome_fields
    assert presentation.summary_lines[len(outcome_fields)] == predictors
    modeled_terms = next(line for line in presentation.summary_lines if line.startswith("Modeled terms:"))
    if model is RegressionModel.COX:
        assert modeled_terms.startswith("Modeled terms: x")
    else:
        assert modeled_terms.startswith("Modeled terms: (Intercept)")
    assert any(line.startswith("Reference levels:") for line in presentation.summary_lines) is bool(
        snapshot.result.references
    )
    assert {context for context, _source in calls} == {"RegressionPresentation"}


@pytest.mark.parametrize(
    ("model", "chart_heading"),
    [
        (RegressionModel.LINEAR, "Linear diagnostics"),
        (RegressionModel.LOGISTIC, "Logistic diagnostics"),
        (RegressionModel.POISSON, "Count-model diagnostics"),
        (RegressionModel.NEGATIVE_BINOMIAL, "Count-model diagnostics"),
        (RegressionModel.COX, "Survival charts"),
    ],
)
def test_regression_component_headings_are_model_specific_and_shared(model, chart_heading):
    def translate(_context: str, source: str) -> str:
        return source

    assert regression_component_label(model, RegressionExportComponent.COEFFICIENTS, translate) == "Coefficients"
    assert regression_component_label(model, RegressionExportComponent.MODEL_METRICS, translate) == "Model metrics"
    assert regression_component_label(model, RegressionExportComponent.CHARTS, translate) == chart_heading


def test_regression_semantic_labels_have_one_translation_source_context():
    labels = (
        PresentationLabel.REGRESSION,
        PresentationLabel.REGRESSION_CONFIGURED_TITLE,
        PresentationLabel.LINEAR_REGRESSION,
        PresentationLabel.LOGISTIC_REGRESSION,
        PresentationLabel.POISSON_REGRESSION,
        PresentationLabel.NEGATIVE_BINOMIAL_REGRESSION,
        PresentationLabel.COX_REGRESSION,
        PresentationLabel.OUTCOME,
        PresentationLabel.DURATION,
        PresentationLabel.EVENT,
        PresentationLabel.PREDICTORS,
        PresentationLabel.MODEL_TERMS,
        PresentationLabel.REFERENCE_LEVELS,
        PresentationLabel.COEFFICIENTS,
        PresentationLabel.MODEL_METRICS,
        PresentationLabel.LINEAR_DIAGNOSTICS,
        PresentationLabel.LOGISTIC_DIAGNOSTICS,
        PresentationLabel.COUNT_DIAGNOSTICS,
        PresentationLabel.SURVIVAL_CHARTS,
        PresentationLabel.INTERCEPT,
    )

    for label in labels:
        context, source = presentation_label_source(label)
        assert context == "RegressionPresentation"
        assert source


@pytest.mark.parametrize(
    ("method", "name", "threshold_role", "threshold"),
    [
        (OutlierMethod.IQR, "IQR (Tukey's fences)", "IQR multiplier:", 1.5),
        (OutlierMethod.Z_SCORE, "Z-score", "Score threshold:", 3.0),
        (OutlierMethod.MODIFIED_Z_SCORE, "Modified Z-score", "Score threshold:", 3.5),
    ],
)
def test_univariate_outlier_presentation_uses_shared_title_and_all_screening_roles(
    method, name, threshold_role, threshold
):
    snapshot = univariate_snapshot(method)
    calls: list[tuple[str, str]] = []

    def translate(context: str, source: str) -> str:
        calls.append((context, source))
        return source

    presentation = build_analysis_presentation(AnalysisCategory.OUTLIERS, snapshot, translate)

    assert presentation.title == f"Outliers — {name}"
    assert presentation.summary_lines == (
        f"{threshold_role} {fmt_num(threshold)}",
        "Screened columns: a, b, few, Row",
        "Selected detail column: a",
    )
    assert {context for context, _source in calls} == {"OutliersPresentation"}
    other_detail = snapshot.with_detail(univariate_snapshot(method, "b").detail, ())
    changed = build_analysis_presentation(AnalysisCategory.OUTLIERS, other_detail, lambda _context, source: source)
    assert changed.title == presentation.title
    assert changed.summary_lines[-1] == "Selected detail column: b"


def test_univariate_outlier_presentation_explicitly_labels_missing_detail_selection():
    presentation = build_analysis_presentation(
        AnalysisCategory.OUTLIERS,
        univariate_snapshot(column=None),
        lambda _context, source: source,
    )

    assert presentation.summary_lines[-1] == "Selected detail column: None"


@pytest.mark.parametrize(
    ("method", "expected_title", "expected_lines"),
    [
        (
            MultivariateOutlierMethod.ISOLATION_FOREST,
            "Outliers — Isolation Forest",
            (
                "Features: x, y",
                "Standardization: Standardized",
                f"Expected outlier fraction: {fmt_pct(0.2, decimals=1)}",
            ),
        ),
        (
            MultivariateOutlierMethod.LOCAL_OUTLIER_FACTOR,
            "Outliers — Local Outlier Factor",
            (
                "Features: x, y",
                "Standardization: Standardized",
                f"Expected outlier fraction: {fmt_pct(0.2, decimals=1)}",
                "LOF neighbors: 2",
            ),
        ),
    ],
)
def test_multivariate_outlier_presentation_includes_only_applicable_settings(method, expected_title, expected_lines):
    calls: list[tuple[str, str]] = []

    def translate(context: str, source: str) -> str:
        calls.append((context, source))
        return source

    presentation = build_analysis_presentation(AnalysisCategory.OUTLIERS, multivariate_snapshot(method), translate)

    assert presentation.title == expected_title
    assert presentation.summary_lines == expected_lines
    assert {context for context, _source in calls} == {"OutliersPresentation"}
    assert presentation_label_source(PresentationLabel.OUTLIERS_CONFIGURED_TITLE) == (
        "OutliersPresentation",
        "{category} — {method}",
    )


@pytest.mark.parametrize(
    ("snapshot", "component", "multivariate", "expected"),
    [
        (univariate_snapshot(), OutlierExportComponent.COLUMN_SUMMARY, False, "Column summary"),
        (univariate_snapshot(), OutlierExportComponent.COLUMN_DETAILS, False, "Model summary"),
        (univariate_snapshot(), OutlierExportComponent.POTENTIAL_OUTLIERS, False, "Potential outliers"),
        (univariate_snapshot(), OutlierExportComponent.CHARTS, False, "Column distributions"),
        (multivariate_snapshot(), OutlierExportComponent.MODEL_SUMMARY, True, "Model summary"),
        (multivariate_snapshot(), OutlierExportComponent.CHARTS, True, "Outlier projection"),
    ],
)
def test_outlier_component_labels_match_the_displayed_content(snapshot, component, multivariate, expected):
    calls: list[tuple[str, str]] = []

    def translate(context: str, source: str) -> str:
        calls.append((context, source))
        return source

    assert (
        outlier_component_label(
            component,
            translate,
            multivariate=multivariate,
        )
        == expected
    )
    assert calls == [("OutliersPresentation", expected)]


def test_univariate_column_details_use_the_shared_model_summary_label_source():
    calls: list[tuple[str, str]] = []

    def translate(context: str, source: str) -> str:
        calls.append((context, source))
        return f"translated {source}"

    label = outlier_component_label(
        OutlierExportComponent.COLUMN_DETAILS,
        translate,
        multivariate=False,
    )

    assert label == "translated Model summary"
    assert calls == [presentation_label_source(PresentationLabel.MODEL_SUMMARY)]
