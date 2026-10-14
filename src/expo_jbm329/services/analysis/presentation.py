"""Shared presentation descriptors for applied analysis results."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from expo_jbm329.services.analysis.categories import AnalysisCategory, HypothesisTest
from expo_jbm329.services.analysis.chi_square import ChiSquareResult
from expo_jbm329.services.analysis.correlation import CorrelationMethod
from expo_jbm329.services.analysis.correlation_export import CorrelationExportSnapshot
from expo_jbm329.services.analysis.group_comparison import GroupComparisonResult
from expo_jbm329.services.analysis.hypothesis_export import HypothesisExportComponent, HypothesisExportSnapshot
from expo_jbm329.services.analysis.paired_comparison import PairedComparisonMethod, PairedComparisonResult
from expo_jbm329.services.analysis.regression import RegressionResult, TermKind, term_name
from expo_jbm329.services.analysis.regression_export import (
    RegressionExportComponent,
    RegressionExportSnapshot,
    regression_model,
)
from expo_jbm329.services.analysis.regression_glm import (
    GeneralizedRegressionResult,
    RegressionModel,
    generalized_term_name,
)
from expo_jbm329.services.analysis.survival import SurvivalResult, survival_term_name

if TYPE_CHECKING:
    from collections.abc import Callable

    from expo_jbm329.services.analysis.report import ReportSnapshot


class PresentationLabel(StrEnum):
    """Stable semantic labels shared by analysis presentation surfaces."""

    CORRELATION = "correlation"
    CONFIGURED_TITLE = "configured_title"
    COLUMNS = "columns"
    STRONGEST_CORRELATIONS = "strongest_correlations"
    CORRELATION_PLOTS = "correlation_plots"
    CORRELATION_MATRIX = "correlation_matrix"
    SCATTERPLOTS = "scatterplots"
    PEARSON = "pearson"
    SPEARMAN = "spearman"
    KENDALL = "kendall"
    SCATTERPLOT_TITLE = "scatterplot_title"
    HYPOTHESIS_TESTS = "hypothesis_tests"
    GROUP_COMPARISON = "group_comparison"
    CATEGORICAL_ASSOCIATION = "categorical_association"
    WILCOXON_SIGNED_RANK = "wilcoxon_signed_rank"
    FRIEDMAN = "friedman"
    NUMERIC_VARIABLE = "numeric_variable"
    GROUPING_VARIABLE = "grouping_variable"
    ROW_VARIABLE = "row_variable"
    COLUMN_VARIABLE = "column_variable"
    MEASUREMENT_VARIABLES = "measurement_variables"
    TESTS_COMPUTED = "tests_computed"
    TESTS_AVAILABLE = "tests_available"
    WELCH_T_TEST = "welch_t_test"
    STUDENT_T_TEST = "student_t_test"
    MANN_WHITNEY_U = "mann_whitney_u"
    ONE_WAY_ANOVA = "one_way_anova"
    KRUSKAL_WALLIS = "kruskal_wallis"
    PEARSON_CHI_SQUARE = "pearson_chi_square"
    FISHER_EXACT = "fisher_exact"
    GROUP_SUMMARY = "group_summary"
    CONTINGENCY_TABLE = "contingency_table"
    MEASUREMENT_SUMMARY = "measurement_summary"
    TEST_RESULTS = "test_results"
    GROUP_DISTRIBUTIONS = "group_distributions"
    ASSOCIATION_PLOTS = "association_plots"
    PAIRED_MEASUREMENT_PLOTS = "paired_measurement_plots"
    HYPOTHESIS_CONFIGURED_TITLE = "hypothesis_configured_title"
    REGRESSION = "regression"
    REGRESSION_CONFIGURED_TITLE = "regression_configured_title"
    LINEAR_REGRESSION = "linear_regression"
    LOGISTIC_REGRESSION = "logistic_regression"
    POISSON_REGRESSION = "poisson_regression"
    NEGATIVE_BINOMIAL_REGRESSION = "negative_binomial_regression"
    COX_REGRESSION = "cox_regression"
    OUTCOME = "outcome"
    DURATION = "duration"
    EVENT = "event"
    PREDICTORS = "predictors"
    MODEL_TERMS = "model_terms"
    REFERENCE_LEVELS = "reference_levels"
    COEFFICIENTS = "coefficients"
    MODEL_METRICS = "model_metrics"
    LINEAR_DIAGNOSTICS = "linear_diagnostics"
    LOGISTIC_DIAGNOSTICS = "logistic_diagnostics"
    COUNT_DIAGNOSTICS = "count_diagnostics"
    SURVIVAL_CHARTS = "survival_charts"
    INTERCEPT = "intercept"


@dataclass(frozen=True, slots=True)
class PresentationLabelDefinition:
    """Translation source and context for one semantic presentation label."""

    context: str
    source: str


_CORRELATION_CONTEXT = "CorrelationView"
_HYPOTHESIS_CONTEXT = "HypothesisPresentation"
_REGRESSION_CONTEXT = "RegressionPresentation"
_LABEL_DEFINITIONS: dict[PresentationLabel, PresentationLabelDefinition] = {
    PresentationLabel.CORRELATION: PresentationLabelDefinition(_CORRELATION_CONTEXT, "Correlation"),
    PresentationLabel.CONFIGURED_TITLE: PresentationLabelDefinition(_CORRELATION_CONTEXT, "{category} — {method}"),
    PresentationLabel.COLUMNS: PresentationLabelDefinition(_CORRELATION_CONTEXT, "Columns:"),
    PresentationLabel.STRONGEST_CORRELATIONS: PresentationLabelDefinition(
        _CORRELATION_CONTEXT, "Strongest correlations"
    ),
    PresentationLabel.CORRELATION_PLOTS: PresentationLabelDefinition(_CORRELATION_CONTEXT, "Correlation plots"),
    PresentationLabel.CORRELATION_MATRIX: PresentationLabelDefinition(_CORRELATION_CONTEXT, "Correlation matrix"),
    PresentationLabel.SCATTERPLOTS: PresentationLabelDefinition(_CORRELATION_CONTEXT, "Scatterplots"),
    PresentationLabel.PEARSON: PresentationLabelDefinition(_CORRELATION_CONTEXT, "Pearson"),
    PresentationLabel.SPEARMAN: PresentationLabelDefinition(_CORRELATION_CONTEXT, "Spearman"),
    PresentationLabel.KENDALL: PresentationLabelDefinition(_CORRELATION_CONTEXT, "Kendall's tau-b"),
    PresentationLabel.SCATTERPLOT_TITLE: PresentationLabelDefinition(_CORRELATION_CONTEXT, "{x} vs {y}"),
    PresentationLabel.HYPOTHESIS_TESTS: PresentationLabelDefinition(_HYPOTHESIS_CONTEXT, "Hypothesis Tests"),
    PresentationLabel.GROUP_COMPARISON: PresentationLabelDefinition(_HYPOTHESIS_CONTEXT, "Group comparison"),
    PresentationLabel.CATEGORICAL_ASSOCIATION: PresentationLabelDefinition(
        _HYPOTHESIS_CONTEXT, "Categorical association"
    ),
    PresentationLabel.WILCOXON_SIGNED_RANK: PresentationLabelDefinition(_HYPOTHESIS_CONTEXT, "Wilcoxon signed-rank"),
    PresentationLabel.FRIEDMAN: PresentationLabelDefinition(_HYPOTHESIS_CONTEXT, "Friedman"),
    PresentationLabel.NUMERIC_VARIABLE: PresentationLabelDefinition(_HYPOTHESIS_CONTEXT, "Numeric variable:"),
    PresentationLabel.GROUPING_VARIABLE: PresentationLabelDefinition(_HYPOTHESIS_CONTEXT, "Grouping variable:"),
    PresentationLabel.ROW_VARIABLE: PresentationLabelDefinition(_HYPOTHESIS_CONTEXT, "Row variable:"),
    PresentationLabel.COLUMN_VARIABLE: PresentationLabelDefinition(_HYPOTHESIS_CONTEXT, "Column variable:"),
    PresentationLabel.MEASUREMENT_VARIABLES: PresentationLabelDefinition(
        _HYPOTHESIS_CONTEXT, "Measurement variables (selected order):"
    ),
    PresentationLabel.TESTS_COMPUTED: PresentationLabelDefinition(_HYPOTHESIS_CONTEXT, "Tests computed:"),
    PresentationLabel.TESTS_AVAILABLE: PresentationLabelDefinition(_HYPOTHESIS_CONTEXT, "Tests available:"),
    PresentationLabel.WELCH_T_TEST: PresentationLabelDefinition(_HYPOTHESIS_CONTEXT, "Welch's t-test"),
    PresentationLabel.STUDENT_T_TEST: PresentationLabelDefinition(_HYPOTHESIS_CONTEXT, "Student's t-test"),
    PresentationLabel.MANN_WHITNEY_U: PresentationLabelDefinition(_HYPOTHESIS_CONTEXT, "Mann-Whitney U"),
    PresentationLabel.ONE_WAY_ANOVA: PresentationLabelDefinition(_HYPOTHESIS_CONTEXT, "One-way ANOVA"),
    PresentationLabel.KRUSKAL_WALLIS: PresentationLabelDefinition(_HYPOTHESIS_CONTEXT, "Kruskal-Wallis"),
    PresentationLabel.PEARSON_CHI_SQUARE: PresentationLabelDefinition(_HYPOTHESIS_CONTEXT, "Pearson's chi-square test"),
    PresentationLabel.FISHER_EXACT: PresentationLabelDefinition(_HYPOTHESIS_CONTEXT, "Fisher's exact test"),
    PresentationLabel.GROUP_SUMMARY: PresentationLabelDefinition(_HYPOTHESIS_CONTEXT, "Group summary"),
    PresentationLabel.CONTINGENCY_TABLE: PresentationLabelDefinition(_HYPOTHESIS_CONTEXT, "Contingency table"),
    PresentationLabel.MEASUREMENT_SUMMARY: PresentationLabelDefinition(_HYPOTHESIS_CONTEXT, "Measurement summary"),
    PresentationLabel.TEST_RESULTS: PresentationLabelDefinition(_HYPOTHESIS_CONTEXT, "Test results"),
    PresentationLabel.GROUP_DISTRIBUTIONS: PresentationLabelDefinition(_HYPOTHESIS_CONTEXT, "Group distributions"),
    PresentationLabel.ASSOCIATION_PLOTS: PresentationLabelDefinition(_HYPOTHESIS_CONTEXT, "Association plots"),
    PresentationLabel.PAIRED_MEASUREMENT_PLOTS: PresentationLabelDefinition(
        _HYPOTHESIS_CONTEXT, "Paired measurement plots"
    ),
    PresentationLabel.HYPOTHESIS_CONFIGURED_TITLE: PresentationLabelDefinition(
        _HYPOTHESIS_CONTEXT, "{category} — {method}"
    ),
    PresentationLabel.REGRESSION: PresentationLabelDefinition(_REGRESSION_CONTEXT, "Regression"),
    PresentationLabel.REGRESSION_CONFIGURED_TITLE: PresentationLabelDefinition(
        _REGRESSION_CONTEXT, "{category} — {model}"
    ),
    PresentationLabel.LINEAR_REGRESSION: PresentationLabelDefinition(_REGRESSION_CONTEXT, "Linear regression"),
    PresentationLabel.LOGISTIC_REGRESSION: PresentationLabelDefinition(_REGRESSION_CONTEXT, "Logistic regression"),
    PresentationLabel.POISSON_REGRESSION: PresentationLabelDefinition(_REGRESSION_CONTEXT, "Poisson regression"),
    PresentationLabel.NEGATIVE_BINOMIAL_REGRESSION: PresentationLabelDefinition(
        _REGRESSION_CONTEXT, "Negative binomial regression"
    ),
    PresentationLabel.COX_REGRESSION: PresentationLabelDefinition(
        _REGRESSION_CONTEXT, "Cox proportional-hazards regression"
    ),
    PresentationLabel.OUTCOME: PresentationLabelDefinition(_REGRESSION_CONTEXT, "Outcome:"),
    PresentationLabel.DURATION: PresentationLabelDefinition(_REGRESSION_CONTEXT, "Duration:"),
    PresentationLabel.EVENT: PresentationLabelDefinition(_REGRESSION_CONTEXT, "Event:"),
    PresentationLabel.PREDICTORS: PresentationLabelDefinition(_REGRESSION_CONTEXT, "Predictors:"),
    PresentationLabel.MODEL_TERMS: PresentationLabelDefinition(_REGRESSION_CONTEXT, "Modeled terms:"),
    PresentationLabel.REFERENCE_LEVELS: PresentationLabelDefinition(_REGRESSION_CONTEXT, "Reference levels:"),
    PresentationLabel.COEFFICIENTS: PresentationLabelDefinition(_REGRESSION_CONTEXT, "Coefficients"),
    PresentationLabel.MODEL_METRICS: PresentationLabelDefinition(_REGRESSION_CONTEXT, "Model metrics"),
    PresentationLabel.LINEAR_DIAGNOSTICS: PresentationLabelDefinition(_REGRESSION_CONTEXT, "Linear diagnostics"),
    PresentationLabel.LOGISTIC_DIAGNOSTICS: PresentationLabelDefinition(_REGRESSION_CONTEXT, "Logistic diagnostics"),
    PresentationLabel.COUNT_DIAGNOSTICS: PresentationLabelDefinition(_REGRESSION_CONTEXT, "Count-model diagnostics"),
    PresentationLabel.SURVIVAL_CHARTS: PresentationLabelDefinition(_REGRESSION_CONTEXT, "Survival charts"),
    PresentationLabel.INTERCEPT: PresentationLabelDefinition(_REGRESSION_CONTEXT, "(Intercept)"),
}

_CATEGORY_FALLBACKS: dict[AnalysisCategory, str] = {
    AnalysisCategory.OVERVIEW: "Overview",
    AnalysisCategory.STATISTICS: "Statistics",
    AnalysisCategory.HYPOTHESIS_TESTS: "Hypothesis Tests",
    AnalysisCategory.CORRELATION: _LABEL_DEFINITIONS[PresentationLabel.CORRELATION].source,
    AnalysisCategory.REGRESSION: "Regression",
    AnalysisCategory.OUTLIERS: "Outliers",
    AnalysisCategory.CLUSTERING: "Clustering",
    AnalysisCategory.PCA: "PCA",
    AnalysisCategory.TIME_SERIES: "Time Series",
}
_CORRELATION_METHOD_LABELS = {
    CorrelationMethod.PEARSON: PresentationLabel.PEARSON,
    CorrelationMethod.SPEARMAN: PresentationLabel.SPEARMAN,
    CorrelationMethod.KENDALL: PresentationLabel.KENDALL,
}
_HYPOTHESIS_COMPONENT_LABELS = {
    HypothesisTest.GROUP_COMPARISON: {
        HypothesisExportComponent.SUMMARY: PresentationLabel.GROUP_SUMMARY,
        HypothesisExportComponent.TEST_RESULTS: PresentationLabel.TEST_RESULTS,
        HypothesisExportComponent.CHARTS: PresentationLabel.GROUP_DISTRIBUTIONS,
    },
    HypothesisTest.CHI_SQUARE: {
        HypothesisExportComponent.SUMMARY: PresentationLabel.CONTINGENCY_TABLE,
        HypothesisExportComponent.TEST_RESULTS: PresentationLabel.TEST_RESULTS,
        HypothesisExportComponent.CHARTS: PresentationLabel.ASSOCIATION_PLOTS,
    },
    HypothesisTest.PAIRED_COMPARISON: {
        HypothesisExportComponent.SUMMARY: PresentationLabel.MEASUREMENT_SUMMARY,
        HypothesisExportComponent.TEST_RESULTS: PresentationLabel.TEST_RESULTS,
        HypothesisExportComponent.CHARTS: PresentationLabel.PAIRED_MEASUREMENT_PLOTS,
    },
}


@dataclass(frozen=True, slots=True)
class ConfigurationField:
    """One ordered applied setting represented by a label and values."""

    label: str
    items: tuple[str, ...]

    def __post_init__(self) -> None:
        """Require a visible label and at least one applied value."""
        if not self.label or not self.items:
            message = "A configuration field requires a label and at least one value."
            raise ValueError(message)

    @property
    def display_value(self) -> str:
        """Return values in their captured order for a plain-text surface."""
        return ", ".join(self.items)


@dataclass(frozen=True, slots=True)
class AnalysisPresentation:
    """Configured analysis title and structured applied configuration."""

    category: str
    title: str
    configuration: tuple[ConfigurationField, ...] = ()

    def __post_init__(self) -> None:
        """Require visible category and title labels."""
        if not self.category or not self.title:
            message = "An analysis presentation requires a category and title."
            raise ValueError(message)

    @property
    def summary_lines(self) -> tuple[str, ...]:
        """Return configuration fields as plain-text lines."""
        return tuple(f"{field.label} {field.display_value}" for field in self.configuration)


def presentation_label_source(label: PresentationLabel) -> tuple[str, str]:
    """Return the canonical translation context and source for a semantic label."""
    definition = _LABEL_DEFINITIONS[label]
    return definition.context, definition.source


def presentation_label_sources() -> tuple[tuple[str, str], ...]:
    """Return unique translation context/source pairs for worker label capture."""
    return tuple(dict.fromkeys((item.context, item.source) for item in _LABEL_DEFINITIONS.values()))


def translate_presentation_label(
    label: PresentationLabel,
    translate: Callable[[str, str], str],
) -> str:
    """Resolve one shared semantic label using the supplied translation source."""
    context, source = presentation_label_source(label)
    return translate(context, source)


def correlation_method_label(
    method: CorrelationMethod,
    translate: Callable[[str, str], str],
) -> str:
    """Return the localized display name of an applied correlation method."""
    return translate_presentation_label(_CORRELATION_METHOD_LABELS[method], translate)


def analysis_category_source(category: AnalysisCategory) -> str:
    """Return the legacy category source label used by non-Correlation surfaces."""
    return _CATEGORY_FALLBACKS[category]


def build_analysis_presentation(
    category: AnalysisCategory,
    snapshot: ReportSnapshot,
    translate: Callable[[str, str], str],
) -> AnalysisPresentation:
    """Build a presentation descriptor from a captured applied result.

    Correlation, Hypothesis Tests, and Regression receive configured titles and
    ordered settings.
    Other categories deliberately retain their existing category-only title.

    Args:
        category: Category that owns the successful applied result.
        snapshot: Captured result, never live configuration controls.
        translate: Translation callback accepting a context and source label.

    Returns:
        Category title, configured analysis title, and typed settings.

    Raises:
        TypeError: If a Correlation category is paired with another snapshot type.
    """
    if category is AnalysisCategory.CORRELATION:
        if not isinstance(snapshot, CorrelationExportSnapshot):
            message = "Correlation presentation requires a correlation result snapshot."
            raise TypeError(message)
        return build_correlation_presentation(
            snapshot.matrix.method,
            snapshot.matrix.columns,
            translate,
        )
    if category is AnalysisCategory.HYPOTHESIS_TESTS:
        if not isinstance(snapshot, HypothesisExportSnapshot):
            message = "Hypothesis Tests presentation requires a hypothesis result snapshot."
            raise TypeError(message)
        return build_hypothesis_presentation(snapshot, translate)
    if category is AnalysisCategory.REGRESSION:
        if not isinstance(snapshot, RegressionExportSnapshot):
            message = "Regression presentation requires a regression result snapshot."
            raise TypeError(message)
        return build_regression_presentation(snapshot, translate)
    category_source = analysis_category_source(category)
    category_title = translate("AnalysisDialog", category_source)
    return AnalysisPresentation(category_title, category_title)


def regression_model_label(model: RegressionModel, translate: Callable[[str, str], str]) -> str:
    """Return the canonical translated name of a regression model family."""
    labels = {
        RegressionModel.LINEAR: PresentationLabel.LINEAR_REGRESSION,
        RegressionModel.LOGISTIC: PresentationLabel.LOGISTIC_REGRESSION,
        RegressionModel.POISSON: PresentationLabel.POISSON_REGRESSION,
        RegressionModel.NEGATIVE_BINOMIAL: PresentationLabel.NEGATIVE_BINOMIAL_REGRESSION,
        RegressionModel.COX: PresentationLabel.COX_REGRESSION,
    }
    return translate_presentation_label(labels[model], translate)


def regression_component_label(
    model: RegressionModel,
    component: RegressionExportComponent,
    translate: Callable[[str, str], str],
) -> str:
    """Return a truthful shared heading for a regression result component."""
    if component is RegressionExportComponent.COEFFICIENTS:
        label = PresentationLabel.COEFFICIENTS
    elif component is RegressionExportComponent.MODEL_METRICS:
        label = PresentationLabel.MODEL_METRICS
    else:
        labels = {
            RegressionModel.LINEAR: PresentationLabel.LINEAR_DIAGNOSTICS,
            RegressionModel.LOGISTIC: PresentationLabel.LOGISTIC_DIAGNOSTICS,
            RegressionModel.POISSON: PresentationLabel.COUNT_DIAGNOSTICS,
            RegressionModel.NEGATIVE_BINOMIAL: PresentationLabel.COUNT_DIAGNOSTICS,
            RegressionModel.COX: PresentationLabel.SURVIVAL_CHARTS,
        }
        label = labels[model]
    return translate_presentation_label(label, translate)


def regression_intercept_label(translate: Callable[[str, str], str]) -> str:
    """Return the canonical translated name of a regression intercept term."""
    return translate_presentation_label(PresentationLabel.INTERCEPT, translate)


def build_regression_presentation(
    snapshot: RegressionExportSnapshot,
    translate: Callable[[str, str], str],
) -> AnalysisPresentation:
    """Build the configured title and role-ordered settings from a fitted model."""
    return build_regression_result_presentation(snapshot.result, translate)


def build_regression_result_presentation(
    result: RegressionResult | GeneralizedRegressionResult | SurvivalResult,
    translate: Callable[[str, str], str],
) -> AnalysisPresentation:
    """Build the applied configuration directly from a fitted result."""
    model_name = regression_model_label(regression_model(result), translate)
    category = translate_presentation_label(PresentationLabel.REGRESSION, translate)
    title = translate_presentation_label(PresentationLabel.REGRESSION_CONFIGURED_TITLE, translate).format(
        category=category,
        model=model_name,
    )
    outcome_role = (
        (
            (PresentationLabel.DURATION, result.duration),
            (PresentationLabel.EVENT, result.event),
        )
        if isinstance(result, SurvivalResult)
        else ((PresentationLabel.OUTCOME, result.target),)
    )
    configuration = [
        ConfigurationField(translate_presentation_label(role, translate), (value,)) for role, value in outcome_role
    ]
    configuration.append(
        ConfigurationField(
            translate_presentation_label(PresentationLabel.PREDICTORS, translate),
            result.predictors,
        )
    )
    references = result.references
    if references:
        configuration.append(
            ConfigurationField(
                translate_presentation_label(PresentationLabel.REFERENCE_LEVELS, translate),
                tuple(f"{reference.column} = {reference.reference_level}" for reference in references),
            )
        )
    terms = _regression_term_names(result, translate)
    configuration.append(
        ConfigurationField(
            translate_presentation_label(PresentationLabel.MODEL_TERMS, translate),
            terms,
        )
    )
    return AnalysisPresentation(category, title, tuple(configuration))


def _regression_term_names(
    result: RegressionResult | GeneralizedRegressionResult | SurvivalResult,
    translate: Callable[[str, str], str],
) -> tuple[str, ...]:
    """Return fitted terms in model order, including dummy levels and intercept."""
    if isinstance(result, RegressionResult):
        return tuple(
            translate("RegressionPresentation", "(Intercept)") if term.kind is TermKind.INTERCEPT else term_name(term)
            for term in result.terms
        )
    if isinstance(result, GeneralizedRegressionResult):
        return tuple(
            translate("RegressionPresentation", "(Intercept)")
            if term.kind is TermKind.INTERCEPT
            else generalized_term_name(term)
            for term in result.terms
        )
    return tuple(
        translate("RegressionPresentation", "(Intercept)")
        if term.kind is TermKind.INTERCEPT
        else survival_term_name(term)
        for term in result.terms
    )


def build_hypothesis_presentation(
    snapshot: HypothesisExportSnapshot,
    translate: Callable[[str, str], str],
) -> AnalysisPresentation:
    """Build the configured title and role-ordered settings from a fitted result."""
    category_title = translate_presentation_label(PresentationLabel.HYPOTHESIS_TESTS, translate)
    result = snapshot.result
    configuration: tuple[ConfigurationField, ...]
    match result:
        case GroupComparisonResult():
            tests = (
                (PresentationLabel.WELCH_T_TEST, PresentationLabel.STUDENT_T_TEST, PresentationLabel.MANN_WHITNEY_U)
                if result.pairwise is not None
                else (PresentationLabel.ONE_WAY_ANOVA, PresentationLabel.KRUSKAL_WALLIS)
            )
            method = translate_presentation_label(PresentationLabel.GROUP_COMPARISON, translate)
            configuration = (
                ConfigurationField(
                    translate_presentation_label(PresentationLabel.NUMERIC_VARIABLE, translate),
                    (result.numeric_column,),
                ),
                ConfigurationField(
                    translate_presentation_label(PresentationLabel.GROUPING_VARIABLE, translate),
                    (result.grouping_column,),
                ),
                ConfigurationField(
                    translate_presentation_label(PresentationLabel.TESTS_COMPUTED, translate),
                    tuple(translate_presentation_label(test, translate) for test in tests),
                ),
            )
        case ChiSquareResult():
            method = translate_presentation_label(PresentationLabel.CATEGORICAL_ASSOCIATION, translate)
            tests_available = [translate_presentation_label(PresentationLabel.PEARSON_CHI_SQUARE, translate)]
            if result.fisher_p_value is not None and result.fisher_odds_ratio is not None:
                tests_available.append(translate_presentation_label(PresentationLabel.FISHER_EXACT, translate))
            configuration = (
                ConfigurationField(
                    translate_presentation_label(PresentationLabel.ROW_VARIABLE, translate),
                    (result.row_column,),
                ),
                ConfigurationField(
                    translate_presentation_label(PresentationLabel.COLUMN_VARIABLE, translate),
                    (result.column_column,),
                ),
                ConfigurationField(
                    translate_presentation_label(PresentationLabel.TESTS_AVAILABLE, translate),
                    tuple(tests_available),
                ),
            )
        case PairedComparisonResult():
            method_label = (
                PresentationLabel.WILCOXON_SIGNED_RANK
                if result.method is PairedComparisonMethod.WILCOXON
                else PresentationLabel.FRIEDMAN
            )
            method = translate_presentation_label(method_label, translate)
            configuration = (
                ConfigurationField(
                    translate_presentation_label(PresentationLabel.MEASUREMENT_VARIABLES, translate),
                    result.columns,
                ),
            )
        case _:
            message = "Hypothesis Tests presentation requires a supported fitted result."
            raise TypeError(message)
    title_template = translate_presentation_label(PresentationLabel.HYPOTHESIS_CONFIGURED_TITLE, translate)
    return AnalysisPresentation(
        category_title, title_template.format(category=category_title, method=method), configuration
    )


def hypothesis_component_label(
    snapshot: HypothesisExportSnapshot,
    component: HypothesisExportComponent,
    translate: Callable[[str, str], str],
) -> str:
    """Return the shared family-specific heading for an applied report/export component."""
    labels = _HYPOTHESIS_COMPONENT_LABELS.get(snapshot.test)
    if labels is None or component not in labels:
        message = "The hypothesis component does not match its applied test family."
        raise ValueError(message)
    return translate_presentation_label(labels[component], translate)


def build_correlation_presentation(
    method: CorrelationMethod,
    columns: tuple[str, ...],
    translate: Callable[[str, str], str],
) -> AnalysisPresentation:
    """Build the configured title and ordered columns for an applied matrix."""
    if not columns:
        message = "A correlation presentation requires applied columns."
        raise ValueError(message)
    category_title = translate_presentation_label(PresentationLabel.CORRELATION, translate)
    method_name = correlation_method_label(method, translate)
    title_template = translate_presentation_label(PresentationLabel.CONFIGURED_TITLE, translate)
    return AnalysisPresentation(
        category_title,
        title_template.format(category=category_title, method=method_name),
        (
            ConfigurationField(
                translate_presentation_label(PresentationLabel.COLUMNS, translate),
                columns,
            ),
        ),
    )
