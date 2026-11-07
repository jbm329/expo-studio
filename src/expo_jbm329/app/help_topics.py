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

    @property
    def url(self) -> str:
        """Return the absolute manual URL, including any topic fragment."""
        return f"{USER_MANUAL_URL}{self.value}"
