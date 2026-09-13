"""Cell context menu builder for result tab tables.

This module is responsible ONLY for building the cell context menu UI
(right-click on a table cell). It does not perform any actions itself.

Design principles:
------------------
• UI construction only (no data mutation)
• No dependency on ResultTabManager internals
• i18n-safe (QT_TR_NOOP + tr / tr_fmt)
• Defensive programming
• Matches header context menu pattern
"""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QT_TR_NOOP
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMenu, QWidget

from expo_jbm329.utils.i18n_utils import tr


class ResultTabCellContextMenu:
    """Builder for cell context menus."""

    # ------------------------------------------------------------------
    # i18n markers (pylupdate6-visible)
    # ------------------------------------------------------------------

    TR_FILTER = QT_TR_NOOP("Filter…")
    TR_KEEP_ROWS = QT_TR_NOOP("Keep rows")
    TR_REMOVE_ROWS = QT_TR_NOOP("Remove rows")

    TR_VALUE = QT_TR_NOOP("Value…")
    TR_REPLACE_VALUE_MENU = QT_TR_NOOP("Replace value…")

    # ------------------------------------------------------------------
    @staticmethod
    def _tr(text: str) -> str:
        return tr("ResultTabCellContextMenu", text)

    # ------------------------------------------------------------------
    def __init__(self, *, parent: QWidget):
        """Initialize the cell context menu builder.

        Args:
            parent: Parent widget for menus.
        """
        self._parent = parent

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def build(
        self,
        *,
        column_name: str,
        raw_value: Any,
    ) -> tuple[QMenu, dict[QAction, str]]:
        """Build the cell context menu.

        Args:
            column_name: Name of the column.
            raw_value: Raw cell value.

        Returns:
            tuple:
              • QMenu instance
              • Mapping QAction -> action_id (str)
        """
        menu = QMenu(self._parent)
        actions: dict[QAction, str] = {}

        # --------------------------------------------------------------
        # Header (preview)
        # --------------------------------------------------------------
        preview = str(raw_value)
        if len(preview) > 80:
            preview = preview[:77] + "…"

        header_action = QAction(f"{column_name} = {preview}", menu)
        header_action.setEnabled(False)
        menu.addAction(header_action)
        menu.addSeparator()

        # --------------------------------------------------------------
        # Filter submenu
        # --------------------------------------------------------------
        sub_filter = QMenu(self._tr(self.TR_FILTER), menu)
        menu.addMenu(sub_filter)

        act_keep = QAction(self._tr(self.TR_KEEP_ROWS), sub_filter)
        sub_filter.addAction(act_keep)
        actions[act_keep] = "filter_keep"

        act_remove = QAction(self._tr(self.TR_REMOVE_ROWS), sub_filter)
        sub_filter.addAction(act_remove)
        actions[act_remove] = "filter_remove"

        # --------------------------------------------------------------
        # Value submenu
        # --------------------------------------------------------------
        menu.addSeparator()

        sub_value = QMenu(self._tr(self.TR_VALUE), menu)
        menu.addMenu(sub_value)

        act_replace = QAction(self._tr(self.TR_REPLACE_VALUE_MENU), sub_value)
        sub_value.addAction(act_replace)
        actions[act_replace] = "value_replace"

        return menu, actions
