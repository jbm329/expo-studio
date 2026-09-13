"""Dialog service."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal, Protocol, TypedDict, runtime_checkable

from PyQt6.QtWidgets import QWidget

from expo_jbm329.services.data_operations.category_orders import CategoryOrderKey
from expo_jbm329.services.data_operations.datetime_formats import DateFormatKey
from expo_jbm329.services.data_profile.semantics import SeriesSemantics

DateTimeTarget = Literal["date", "datetime"]


class ProfileChoice(Enum):
    """Enum for profile scope confirmation."""
    ACTIVE = "active"
    ALL = "all"
    CANCEL = "cancel"


class BetweenResult(TypedDict):
    """Result of a numeric or datetime range prompt."""
    low: object
    high: object
    inclusive: str
    ok: bool
    

class CompareResult(TypedDict):
    """Result of a numeric or datetime compare prompt."""
    op: str
    value: object
    ok: bool


class DateTimeConversionResult(TypedDict):
    """Result of a datetime conversion prompt."""
    format_key: DateFormatKey
    target: DateTimeTarget
    ok: bool


class BooleanConversionResult(TypedDict):
    """Result of a boolean conversion prompt."""
    true_values: list[str]
    false_values: list[str]
    ok: bool


class CategoryConversionResult(TypedDict):
    """Result of a category conversion prompt."""
    order: CategoryOrderKey
    ordered: bool
    strict: bool
    ok: bool


class CategoryRenameResult(TypedDict):
    """Result of a category rename prompt."""
    old: str
    new: str
    ok: bool


class CategoryOrderResult(TypedDict):
    """Result of a category order prompt."""
    order_list: list[str]
    ordered: bool
    strict: bool
    append_missing_tail: bool
    ok: bool


class TextReplaceResult(TypedDict):
    """Result of a text replace prompt."""
    old: str
    new: str
    case: bool
    ok: bool


class TextInsertResult(TypedDict):
    """Result of a text insert prompt."""
    insert: str
    position: int
    ok: bool


class ValueReplaceResult(TypedDict):
    """Result of a value replace prompt."""
    new_value: str
    replace_all: bool
    ok: bool


class TextFilterMatchResult(TypedDict):
    """Result of a text contains filter prompt."""
    value: str
    case_sensitive: bool
    ok: bool


class SplitColumnResult(TypedDict):
    """Result of the split column dialog."""
    delimiter: str
    keep_original: bool
    mode: Literal["first", "last"]
    ok: bool
    

class MergeColumnsResult(TypedDict):
    """Result of a merge columns prompt."""
    columns: list[str]
    delimiter: str
    new_name: str
    keep_original: bool
    ok: bool


@runtime_checkable
class DialogService(Protocol):
    """Abstraction for dialogs."""
    # --- Message boxes ---
    def info(self, parent: QWidget, title: str, text: str) -> None:
        """Show an informational message box."""
        ...

    def warn(self, parent: QWidget, title: str, text: str) -> None:
        """Show a warning message box."""
        ...

    def critical(self, parent: QWidget, title: str, text: str) -> None:
        """Show a critical error message box."""
        ...

    # --- Confirms ---
    def confirm_profile_scope(
        self,
        parent: QWidget,
        *,
        title: str,
        text: str,
        active_tab_text: str,
        all_tabs_text: str,
    ) -> ProfileChoice:
        """Show a confirmation dialog for profile scope."""
        ...

    def confirm_delete(
        self,
        parent: QWidget,
        *,
        title: str | None,
        name: str,
        full_path: str,
        size_hint: str | None = None,
    ) -> bool:
        """Show a confirmation dialog for deleting a file or folder."""
        ...

    # --- Prompts (delegated later) ---
    def prompt_between(
        self,
        parent: QWidget,
        *,
        title: str,
        label_low: str,
        label_high: str,
        default_low: object,
        default_high: object,
        inclusive_default: str,
        semantics: SeriesSemantics,
    ) -> BetweenResult:
        """Show a prompt for a range.

        Widget choice is based solely on semantics.
        """
        ...

    def prompt_compare(
        self,
        parent: QWidget,
        *,
        title: str,
        label_op: str,
        label_value: str,
        default_op: str,
        default_value: object,
        semantics: SeriesSemantics,
    ) -> CompareResult:
        """Show a prompt for comparison.

        Widget choice is based solely on semantics.
        """
        ...

    def prompt_filter_match(
        self,
        parent: QWidget,
        *,
        title: str,
        label: str,
        default_value: str,
        default_case_sensitive: bool = True,
    ) -> TextFilterMatchResult:
        """Prompt for text-based match filtering (e.g. contains, equals)."""
        ...

    def prompt_datetime_conversion(
        self,
        parent: QWidget,
        *,
        title: str,
        default_format_key: DateFormatKey,
        default_target: DateTimeTarget,
    ) -> DateTimeConversionResult:
        """Show a dialog for datetime conversion.

        The user selects:
        - how the input data is formatted (format_key)
        - what the column should become (date or datetime)

        Parsing flags (fmt/dayfirst/yearfirst) are derived internally
        from format_key. Presentation is handled elsewhere.
        """
        ...

    def prompt_boolean_conversion(
        self,
        parent: QWidget,
        *,
        title: str,
        default_true_values: list[str],
        default_false_values: list[str],
    ) -> BooleanConversionResult:
        """Show a dialog for boolean conversion.

        The user specifies which values should be interpreted as True or False.
        """
        ...

    def prompt_category_conversion(
        self,
        parent: QWidget,
        *,
        title: str,
        default_order: CategoryOrderKey,
        default_ordered: bool,
        default_strict: bool,
    ) -> CategoryConversionResult:
        """Show a dialog for category conversion."""
        ...

    def prompt_category_rename(
        self,
        parent: QWidget,
        *,
        title: str,
        categories: list[str],
        default_old_value: str,
        default_new_value: str,
    ) -> CategoryRenameResult:
        """Show a prompt for category renaming."""
        ...

    def prompt_category_set_order(
            self,
            parent: QWidget,
            *,
            title: str,
            default_order_list: list[str],
            default_ordered: bool,
            default_strict: bool,
            default_append_missing_tail: bool,
    ) -> CategoryOrderResult:
        """Show a prompt for category ordering."""
        ...

    def prompt_text_replace(self, parent: QWidget, **kwargs) -> TextReplaceResult:
        """Show a prompt for text replacement."""
        ...

    def prompt_text_insert(self, parent: QWidget, **kwargs) -> TextInsertResult:
        """Show a prompt for text insertion."""
        ...

    def prompt_value_replace(self, parent: QWidget, **kwargs) -> ValueReplaceResult:
        """Show a prompt for value replacement."""
        ...

    def prompt_text(self, parent: QWidget, **kwargs) -> tuple[str, bool]:
        """Show a prompt for text input."""
        ...

    def prompt_choice(self, parent: QWidget, **kwargs) -> tuple[str, bool]:
        """Show a prompt for a choice from a list of options."""
        ...

    def prompt_yes_no(self, parent: QWidget, **kwargs) -> bool:
        """Show a yes/no confirmation dialog."""
        ...

    def prompt_number(
        self,
        parent: QWidget,
        *,
        title: str,
        label: str,
        default: float | int | None,
        semantics: SeriesSemantics,
    ) -> tuple[float | int | None, bool]:
        """Show a prompt for numeric input."""
        ...

    def prompt_datetime(
        self,
        parent: QWidget,
        *,
        title: str,
        label: str,
        default: datetime | None,
        semantics: SeriesSemantics,
    ) -> tuple[datetime | None, bool]:
        """Show a prompt for datetime input."""
        ...

    def prompt_split_column(
        self,
        parent: QWidget,
        *,
        title: str,
        column: str,
        default_delimiter: str,
        default_keep_original: bool,
        default_mode: Literal["first", "last"],
    ) -> SplitColumnResult:
        """Show a dialog for splitting a column."""
        ...

    def prompt_merge_columns(
        self,
        parent: QWidget,
        *,
        title: str,
        all_columns: list[str],
        default_columns: list[str],
        default_delimiter: str,
        default_new_name: str,
        default_keep_original: bool,
    ) -> MergeColumnsResult:
        """Show a dialog for selecting and merging multiple columns.

        Notes:
            - default_columns must be pre-selected when the dialog opens
              (e.g. the column that was right-clicked).
            - Dialog must not allow OK unless at least two columns are selected.
            - Returned column order defines merge order.
        """
        ...
