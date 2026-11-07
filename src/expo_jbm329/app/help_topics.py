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

    @property
    def url(self) -> str:
        """Return the absolute manual URL, including any topic fragment."""
        return f"{USER_MANUAL_URL}{self.value}"
