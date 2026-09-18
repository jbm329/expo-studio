"""UI builder for column header context menus.

This module contains the UI-only logic for constructing context menus
(QMenu) for table column headers based on a precomputed ResultTabHeaderContext.

Purpose
-------
The purpose of this module is to translate an immutable ResultTabHeaderContext
into a concrete, user-facing QMenu with correctly enabled/disabled
actions.

By isolating menu construction here, we achieve:
  • A declarative and readable menu definition
  • Clear separation from controllers and data mutation logic
  • A single place for menu structure, labels, and grouping
  • Improved maintainability and i18n readiness

Design principles
-----------------
• UI-only responsibility:
    This module creates QMenu and QAction objects, but does NOT:
      - Modify DataFrames
      - Call services
      - Trigger dialogs
      - Dispatch or execute actions

• Context-driven:
    All enable/disable decisions are derived exclusively from
    ResultTabHeaderContext. No additional state is queried.

• Stateless:
    The menu is built on demand and discarded after use.
    No internal state is preserved between invocations.

• i18n-friendly:
    All user-visible strings are routed through an optional
    translation function (tr), allowing seamless later integration
    with Qt translation infrastructure.

Typical usage
-------------
1. A controller builds a ResultTabHeaderContext for the clicked column
2. ResultTabColumnHeaderContextMenu.build(ctx) is called
3. The returned QMenu is shown to the user
4. The chosen QAction is mapped to an action identifier
5. The controller dispatches the action

Location in architecture
------------------------
gui/menus/result_tab_column_header_context_menu.py

This module belongs to the GUI layer and sits below controllers
(e.g. ResultTabManager) but above the service layer. It is a pure
presentation component.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QT_TR_NOOP
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMenu, QWidget

from expo_jbm329.utils.i18n_utils import tr

if TYPE_CHECKING:
    from expo_jbm329.gui.menus.result_tab_header_context import ResultTabHeaderContext


class ResultTabColumnHeaderContextMenu:
    """Builds the column header context menu.

    This class is UI-only:
    - no DataFrame mutation
    - no controller logic
    - returns action identifiers only
    """

    # --- i18n markers (pylupdate6-visible) -----------------------------
    TR_SORT_ASCENDING = QT_TR_NOOP("Sort ascending")
    TR_SORT_DESCENDING = QT_TR_NOOP("Sort descending")

    TR_RENAME = QT_TR_NOOP("Rename…")
    TR_REMOVE = QT_TR_NOOP("Remove…")
    TR_PROPERTIES = QT_TR_NOOP("Properties")

    # Cleanse
    TR_CLEANSE = QT_TR_NOOP("Cleanse data…")
    TR_TRIM = QT_TR_NOOP("Trim (remove whitespace)")
    TR_NORMALIZE_WHITESPACE = QT_TR_NOOP("Normalize whitespace")
    TR_LOWER_CASE = QT_TR_NOOP("Convert to lowercase")
    TR_UPPER_CASE = QT_TR_NOOP("Convert to uppercase")
    TR_TITLE_CASE = QT_TR_NOOP("Convert to title case")
    TR_CAPITALIZE_FIRST = QT_TR_NOOP("Capitalize first letter")
    TR_REPLACE = QT_TR_NOOP("Replace text…")
    TR_INSERT = QT_TR_NOOP("Insert text…")
    TR_REMOVE_SIMPLE = QT_TR_NOOP("Remove text (simple)…")
    TR_REMOVE_REGEX = QT_TR_NOOP("Remove text (regex)…")
    TR_KEEP_DIGITS = QT_TR_NOOP("Keep digits only")
    TR_KEEP_LETTERS = QT_TR_NOOP("Keep letters only")

    # Fill missing values
    TR_FILL_MISSING = QT_TR_NOOP("Fill missing values…")
    TR_MEAN = QT_TR_NOOP("Mean")
    TR_MEDIAN = QT_TR_NOOP("Median")
    TR_MODE = QT_TR_NOOP("Mode")
    TR_CUSTOM_VALUE = QT_TR_NOOP("Custom value…")

    # Convert dtypes
    TR_DATATYPE = QT_TR_NOOP("Datatype…")
    TR_TO_CATEGORY = QT_TR_NOOP("Convert to category…")
    TR_TO_STRING = QT_TR_NOOP("Convert to text (string)")
    TR_TO_INT = QT_TR_NOOP("Convert to integer (Int64)")
    TR_TO_FLOAT = QT_TR_NOOP("Convert to float (Float64)")
    TR_TO_DATETIME = QT_TR_NOOP("Convert to datetime…")
    TR_TO_DATE = QT_TR_NOOP("Convert to date…")
    TR_TO_BOOLEAN = QT_TR_NOOP("Convert to boolean…")
    TR_RENAME_CATEGORY = QT_TR_NOOP("Rename category…")
    TR_ORDER_CATEGORY = QT_TR_NOOP("Set category order…")
    TR_REMOVE_UNUSED_CATEGORIES = QT_TR_NOOP("Remove unused categories")

    # Filter rows
    TR_FILTER_ROWS = QT_TR_NOOP("Filter rows…")
    TR_EQUALS = QT_TR_NOOP("Equals…")
    TR_CONTAINS = QT_TR_NOOP("Contains…")
    TR_IS_EMPTY = QT_TR_NOOP("Is empty")
    TR_NOT_EMPTY = QT_TR_NOOP("Is not empty")
    TR_COMPARE = QT_TR_NOOP("Compare…")
    TR_BETWEEN = QT_TR_NOOP("Between…")

    # Split / merge
    TR_SPLIT = QT_TR_NOOP("Split column…")
    TR_MERGE = QT_TR_NOOP("Merge columns…")

    @staticmethod
    def _tr(text: str) -> str:
        """Translate a string for the context menu."""
        return tr("ResultTabColumnHeaderContextMenu", text)

    def __init__(self, parent: QWidget) -> None:
        """Initialize the ResultTabColumnHeaderContextMenu."""
        self._parent = parent

    def build(self, ctx: ResultTabHeaderContext) -> tuple[QMenu, dict[QAction, str]]:
        """Build a column header context menu for the given context.

        This method creates a QMenu instance whose structure and
        enabled/disabled state are fully determined by the supplied
        ResultTabHeaderContext.

        Each QAction added to the menu is associated with a stable
        action identifier, returned via a mapping to allow the caller
        to dispatch the selected action.

        Args:
            ctx: Immutable context describing the current column,
                 selection state, and semantic/dtype properties.

        Returns:
            A tuple of:
              • QMenu instance ready to be shown
              • Mapping of QAction → action_id

        Notes:
            • The returned menu has no side effects until executed.
            • The menu does not retain references to the context
              after this call.
            • The caller is responsible for executing and disposing
              of the menu.
        """
        caps = ctx.capabilities
        one = ctx.only_one_selected

        menu = QMenu(self._parent)
        action_map: dict[QAction, str] = {}

        # ---- Title -------------------------------------------------
        title = QAction(ctx.column_name, menu)
        title.setEnabled(False)
        menu.addAction(title)
        menu.addSeparator()

        # ---- Sorting ----------------------------------------------
        self._add_menu_action(
            menu,
            action_map,
            self._tr(self.TR_SORT_ASCENDING),
            "sort.asc",
        )

        self._add_menu_action(
            menu,
            action_map,
            self._tr(self.TR_SORT_DESCENDING),
            "sort.desc",
        )

        menu.addSeparator()

        # ---- Column ops -------------------------------------------
        self._add_menu_action(
            menu,
            action_map,
            self._tr(self.TR_RENAME),
            "column.rename",
            enabled=one,
        )

        self._add_menu_action(
            menu,
            action_map,
            self._tr(self.TR_REMOVE),
            "column.drop",
            enabled=one,
        )

        self._add_menu_action(
            menu,
            action_map,
            self._tr(self.TR_PROPERTIES),
            "column.properties",
            enabled=one,
        )

        menu.addSeparator()

        # ---- Clean submenu ----------------------------------------
        clean_menu = self._add_submenu(menu, self._tr(self.TR_CLEANSE))
        clean_menu.setEnabled(one)

        self._add_menu_action(
            clean_menu,
            action_map,
            self._tr(self.TR_TRIM),
            "clean.strip",
            enabled=one and caps.can_clean_text,
        )

        self._add_menu_action(
            clean_menu,
            action_map,
            self._tr(self.TR_NORMALIZE_WHITESPACE),
            "clean.whitespace",
            enabled=one and caps.can_clean_text,
        )

        self._add_menu_action(
            clean_menu,
            action_map,
            self._tr(self.TR_LOWER_CASE),
            "clean.lower",
            enabled=one and caps.can_clean_text,
        )

        self._add_menu_action(
            clean_menu,
            action_map,
            self._tr(self.TR_UPPER_CASE),
            "clean.upper",
            enabled=one and caps.can_clean_text,
        )

        self._add_menu_action(
            clean_menu,
            action_map,
            self._tr(self.TR_TITLE_CASE),
            "clean.title",
            enabled=one and caps.can_clean_text,
        )

        self._add_menu_action(
            clean_menu,
            action_map,
            self._tr(self.TR_CAPITALIZE_FIRST),
            "clean.first_upper",
            enabled=one and caps.can_clean_text,
        )

        clean_menu.addSeparator()

        self._add_menu_action(
            clean_menu,
            action_map,
            self._tr(self.TR_REPLACE),
            "clean.replace",
            enabled=one and caps.can_clean_text,
        )

        self._add_menu_action(
            clean_menu,
            action_map,
            self._tr(self.TR_INSERT),
            "clean.insert",
            enabled=one and caps.can_clean_text,
        )

        clean_menu.addSeparator()

        self._add_menu_action(
            clean_menu,
            action_map,
            self._tr(self.TR_REMOVE_SIMPLE),
            "clean.remove",
            enabled=one and caps.can_clean_text,
        )

        self._add_menu_action(
            clean_menu,
            action_map,
            self._tr(self.TR_REMOVE_REGEX),
            "clean.regex",
            enabled=one and caps.can_regex_text,
        )

        clean_menu.addSeparator()

        self._add_menu_action(
            clean_menu,
            action_map,
            self._tr(self.TR_KEEP_DIGITS),
            "clean.digits",
            enabled=one and caps.can_clean_text,
        )

        self._add_menu_action(
            clean_menu,
            action_map,
            self._tr(self.TR_KEEP_LETTERS),
            "clean.letters",
            enabled=one and caps.can_clean_text,
        )

        # ---- Fill missing values -----------------------------------
        fill_menu = self._add_submenu(menu, self._tr(self.TR_FILL_MISSING))
        fill_menu.setEnabled(one)

        self._add_menu_action(
            fill_menu,
            action_map,
            self._tr(self.TR_MEAN),
            "fill.mean",
            enabled=one and caps.can_fill_numeric,
        )
        self._add_menu_action(
            fill_menu,
            action_map,
            self._tr(self.TR_MEDIAN),
            "fill.median",
            enabled=one and caps.can_fill_numeric,
        )
        self._add_menu_action(
            fill_menu,
            action_map,
            self._tr(self.TR_MODE),
            "fill.mode",
            enabled=one and caps.can_fill_numeric,
        )
        self._add_menu_action(
            fill_menu,
            action_map,
            self._tr(self.TR_CUSTOM_VALUE),
            "fill.custom",
            enabled=one,
        )

        # ---- Datatype ----------------------------------------------
        dtype_menu = self._add_submenu(menu, self._tr(self.TR_DATATYPE))
        dtype_menu.setEnabled(one)

        self._add_menu_action(
            dtype_menu,
            action_map,
            self._tr(self.TR_TO_CATEGORY),
            "dtype.to_category",
            enabled=one and caps.can_convert_to_category,
        )
        self._add_menu_action(
            dtype_menu,
            action_map,
            self._tr(self.TR_TO_STRING),
            "dtype.to_string",
            enabled=one and caps.can_convert_to_string,
        )
        self._add_menu_action(
            dtype_menu,
            action_map,
            self._tr(self.TR_TO_INT),
            "dtype.to_int",
            enabled=one and caps.can_convert_to_int,
        )
        self._add_menu_action(
            dtype_menu,
            action_map,
            self._tr(self.TR_TO_FLOAT),
            "dtype.to_float",
            enabled=one and caps.can_convert_to_float,
        )
        self._add_menu_action(
            dtype_menu,
            action_map,
            self._tr(self.TR_TO_DATETIME),
            "dtype.to_datetime",
            enabled=one and caps.can_convert_to_datetime,
        )
        self._add_menu_action(
            dtype_menu,
            action_map,
            self._tr(self.TR_TO_DATE),
            "dtype.to_date_only",
            enabled=one and caps.can_convert_to_date_only,
        )
        self._add_menu_action(
            dtype_menu,
            action_map,
            self._tr(self.TR_TO_BOOLEAN),
            "dtype.to_bool",
            enabled=one and caps.can_convert_to_bool,
        )

        # ---- Category operations -----------------------------------
        dtype_menu.addSeparator()

        self._add_menu_action(
            dtype_menu,
            action_map,
            self._tr(self.TR_RENAME_CATEGORY),
            "category.rename",
            enabled=one and caps.can_edit_categories,
        )
        self._add_menu_action(
            dtype_menu,
            action_map,
            self._tr(self.TR_ORDER_CATEGORY),
            "category.set_order",
            enabled=one and caps.can_edit_categories,
        )
        self._add_menu_action(
            dtype_menu,
            action_map,
            self._tr(self.TR_REMOVE_UNUSED_CATEGORIES),
            "category.remove_unused",
            enabled=one and caps.can_edit_categories,
        )

        # ---- Filter rows -------------------------------------------
        filter_menu = self._add_submenu(menu, self._tr(self.TR_FILTER_ROWS))
        filter_menu.setEnabled(one)

        self._add_menu_action(
            filter_menu,
            action_map,
            self._tr(self.TR_EQUALS),
            "filter.equals",
            enabled=one,
        )
        self._add_menu_action(
            filter_menu,
            action_map,
            self._tr(self.TR_CONTAINS),
            "filter.contains",
            enabled=one and caps.can_clean_text,
        )

        filter_menu.addSeparator()

        self._add_menu_action(
            filter_menu,
            action_map,
            self._tr(self.TR_IS_EMPTY),
            "filter.isna",
            enabled=one,
        )
        self._add_menu_action(
            filter_menu,
            action_map,
            self._tr(self.TR_NOT_EMPTY),
            "filter.notna",
            enabled=one,
        )

        filter_menu.addSeparator()

        self._add_menu_action(
            filter_menu,
            action_map,
            self._tr(self.TR_COMPARE),
            "filter.compare",
            enabled=one and (caps.can_filter_numeric or caps.can_filter_datetime),
        )
        self._add_menu_action(
            filter_menu,
            action_map,
            self._tr(self.TR_BETWEEN),
            "filter.between",
            enabled=one and (caps.can_filter_numeric or caps.can_filter_datetime),
        )

        menu.addSeparator()

        # ---- split / merge -----------------------------------------
        self._add_menu_action(
            menu,
            action_map,
            self._tr(self.TR_SPLIT),
            "column.split",
            enabled=one,
        )
        self._add_menu_action(
            menu,
            action_map,
            self._tr(self.TR_MERGE),
            "column.merge",
            enabled=True,
        )

        return menu, action_map

    def _add_submenu(self, menu: QMenu, title: str) -> QMenu:
        """Helper method for adding a submenu to a menu."""
        sub = QMenu(title, menu)
        menu.addMenu(sub)
        return sub

    def _add_menu_action(
        self,
        menu: QMenu,
        action_map: dict[QAction, str],
        text: str,
        action_id: str,
        *,
        enabled: bool = True,
    ) -> None:
        """Helper method for adding a single action to a menu."""
        act = QAction(text, menu)
        menu.addAction(act)
        act.setEnabled(enabled)
        action_map[act] = action_id
