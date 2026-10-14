from __future__ import annotations

from dataclasses import replace

import pytest

from expo_jbm329.services.analysis.categories import AnalysisCategory
from expo_jbm329.services.analysis.correlation import CorrelationMethod
from expo_jbm329.services.analysis.correlation_export import CorrelationExportSnapshot
from expo_jbm329.services.analysis.presentation import (
    AnalysisPresentation,
    ConfigurationField,
    PresentationLabel,
    build_analysis_presentation,
    build_correlation_presentation,
    presentation_label_source,
)
from tests.analysis.test_correlation_export import _snapshot as correlation_snapshot
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
    for key in PresentationLabel:
        context, source = presentation_label_source(key)
        assert context == "CorrelationView"
        assert source


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
