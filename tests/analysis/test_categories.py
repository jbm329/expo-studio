from __future__ import annotations

from expo_jbm329.services.analysis.categories import AnalysisCategory


def test_analysis_category_values_are_stable_identifiers():
    """Category values are used as Qt item data and must stay stable strings."""
    assert AnalysisCategory.OVERVIEW == "overview"
    assert AnalysisCategory.STATISTICS == "statistics"
    assert AnalysisCategory.CORRELATION == "correlation"
    assert AnalysisCategory.REGRESSION == "regression"
    assert AnalysisCategory.OUTLIERS == "outliers"
    assert AnalysisCategory.CLUSTERING == "clustering"
    assert AnalysisCategory.PCA == "pca"
    assert AnalysisCategory.TIME_SERIES == "time_series"


def test_analysis_category_has_no_duplicate_values():
    values = [category.value for category in AnalysisCategory]
    assert len(values) == len(set(values))


def test_analysis_category_round_trips_through_its_value():
    for category in AnalysisCategory:
        assert AnalysisCategory(category.value) is category
