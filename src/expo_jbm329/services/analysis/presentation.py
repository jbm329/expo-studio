"""Shared presentation descriptors for applied analysis results."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from expo_jbm329.services.analysis.categories import AnalysisCategory
from expo_jbm329.services.analysis.correlation import CorrelationMethod
from expo_jbm329.services.analysis.correlation_export import CorrelationExportSnapshot

if TYPE_CHECKING:
    from collections.abc import Callable

    from expo_jbm329.services.analysis.report import ReportSnapshot


class PresentationLabel(StrEnum):
    """Stable semantic labels shared by Correlation presentation surfaces."""

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


@dataclass(frozen=True, slots=True)
class PresentationLabelDefinition:
    """Translation source and context for one semantic presentation label."""

    context: str
    source: str


_CORRELATION_CONTEXT = "CorrelationView"
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

    Correlation receives its configured title and ordered applied columns.
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
    category_source = analysis_category_source(category)
    category_title = translate("AnalysisDialog", category_source)
    return AnalysisPresentation(category_title, category_title)


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
