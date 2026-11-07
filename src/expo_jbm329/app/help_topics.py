"""Stable destinations in the online user manual.

Use paths relative to USER_MANUAL_URL and explicit documentation anchors.
Browser opening and user-facing error handling belong to the calling UI.
"""

from enum import StrEnum

from expo_jbm329.app.metadata import USER_MANUAL_URL


class HelpTopic(StrEnum):
    """Named manual destinations, checked against documentation by pytest."""

    HOME = ""
    WORKBENCH_LAYOUT = "workbench/#window-layout"
    GENERAL_SETTINGS = "settings/general-settings/"
    LOG_SETTINGS = "settings/log-settings/"
    DATABASE_CONNECTIONS = "settings/database-connections/"
    REST_API_CONNECTIONS = "settings/rest-api-connections/"
    SCB_QUERY_BUILDER = "settings/rest-api-connections/#scb-query-builder"
    JOIN_DATASETS = "transform-data/join/"
    JOIN_PREVIEW = "transform-data/join/#preview"
    CONCATENATE_DATASETS = "transform-data/concatenate/"
    DERIVED_COLUMNS = "transform-data/derived-columns/"
    RESHAPE = "transform-data/reshape/"
    RESHAPE_CONDITION_BUILDER = "transform-data/reshape/#condition-builder"
    ADVANCED_ANALYSIS = "analyze-data/"
    ANALYSIS_OVERVIEW = "analyze-data/overview/"
    ANALYSIS_STATISTICS = "analyze-data/statistics/"
    ANALYSIS_HYPOTHESIS_TESTS = "analyze-data/hypothesis-tests/"
    ANALYSIS_GROUP_COMPARISON = "analyze-data/hypothesis-tests/#group-comparison"
    ANALYSIS_CHI_SQUARE = "analyze-data/hypothesis-tests/#chi-square"
    ANALYSIS_PAIRED_COMPARISON = "analyze-data/hypothesis-tests/#paired-comparison"
    ANALYSIS_CORRELATION = "analyze-data/correlation/"
    ANALYSIS_REGRESSION = "analyze-data/regression/"
    ANALYSIS_OUTLIERS = "analyze-data/outliers/"
    ANALYSIS_CLUSTERING = "analyze-data/clustering/"
    ANALYSIS_PCA = "analyze-data/pca/"
    ANALYSIS_TIME_SERIES = "analyze-data/time-series/"
    ANALYSIS_REPORTS = "export-and-report/analysis-results-and-reports/"
    CONVERT_TO_CATEGORIES = "prepare-data/clean-values/#convert-to-category"
    ORDER_CATEGORIES = "prepare-data/clean-values/#set-category-order"

    @property
    def url(self) -> str:
        """Return the absolute manual URL, including any topic fragment."""
        return f"{USER_MANUAL_URL}{self.value}"
