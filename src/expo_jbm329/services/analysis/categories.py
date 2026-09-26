"""Analysis category taxonomy.

This module answers the question:
    "What analysis categories does the Advanced Analysis workspace offer?"

It MUST NOT contain UI text or Qt imports - display labels are owned by the
GUI layer (see gui/dialogs/analysis/analysis_dialog.py), which translates
each category via Qt's i18n system.
"""

from __future__ import annotations

from enum import StrEnum


class AnalysisCategory(StrEnum):
    """Analysis categories available in the Advanced Analysis workspace.

    Ordered as they should appear in the workspace sidebar. Every category
    is a placeholder until its dedicated implementation step lands.
    """

    OVERVIEW = "overview"
    STATISTICS = "statistics"
    HYPOTHESIS_TESTS = "hypothesis_tests"
    CORRELATION = "correlation"
    REGRESSION = "regression"
    OUTLIERS = "outliers"
    CLUSTERING = "clustering"
    PCA = "pca"
    TIME_SERIES = "time_series"
