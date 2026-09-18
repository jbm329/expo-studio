"""Test implementation of DialogService."""
from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from expo_jbm329.gui.dialogs.service.dialog_service import (
    BetweenResult,
    BooleanConversionResult,
    CategoryConversionResult,
    CategoryOrderResult,
    CategoryRenameResult,
    CompareResult,
    DateTimeConversionResult,
    DateTimeTarget,
    DialogService,
    MergeColumnsResult,
    ProfileChoice,
    SplitColumnResult,
    TextFilterMatchResult,
    TextInsertResult,
    TextReplaceResult,
    ValueReplaceResult,
)

if TYPE_CHECKING:
    from datetime import datetime

    from PyQt6.QtWidgets import QWidget

    from expo_jbm329.services.data_operations.category_orders import CategoryOrderKey
    from expo_jbm329.services.data_operations.datetime_formats import DateFormatKey
    from expo_jbm329.services.data_profile.semantics import SeriesSemantics


class NullDialogService(DialogService):
    """Test implementation of DialogService.

    Never opens any UI. All calls are recorded and return
    configurable or deterministic default values.

    Intended for unit and integration testing.
    """

    def __init__(
        self,
        *,
        default_profile_choice: ProfileChoice = ProfileChoice.ACTIVE,
        default_confirm_delete: bool = False,
    ) -> None:
        """Initialize the NullDialogService."""
        self.calls: list[tuple[str, tuple, dict]] = []

        self.default_profile_choice = default_profile_choice
        self.default_confirm_delete = default_confirm_delete

        # Next-return overrides (one-shot)
        self._next_prompt_text: tuple[str, bool] | None = None
        self._next_prompt_choice: tuple[str, bool] | None = None
        self._next_prompt_yes_no: bool | None = None
        self._next_prompt_number: tuple[float | int | None, bool] | None = None
        self._next_prompt_datetime: tuple[datetime | None, bool] | None = None

        self._next_prompt_between: BetweenResult | None = None
        self._next_prompt_compare: CompareResult | None = None
        self._next_prompt_datetime_conversion: DateTimeConversionResult | None = None
        self._next_prompt_boolean_conversion: BooleanConversionResult | None = None
        self._next_prompt_category_conversion: CategoryConversionResult | None = None
        self._next_prompt_category_rename: CategoryRenameResult | None = None
        self._next_prompt_category_set_order: CategoryOrderResult | None = None
        self._next_prompt_text_replace: TextReplaceResult | None = None
        self._next_prompt_text_insert: TextInsertResult | None = None
        self._next_prompt_value_replace: ValueReplaceResult | None = None
        self._next_prompt_filter_match: TextFilterMatchResult | None = None

        self._next_prompt_split_column: SplitColumnResult | None = None
        self._next_prompt_merge_columns: MergeColumnsResult | None = None

    # ------------------------------------------------------------------
    # Helpers for tests
    # ------------------------------------------------------------------

    def set_next_prompt_text(self, value: str, ok: bool) -> None:
        """Set the next value returned by prompt_text."""
        self._next_prompt_text = (value, ok)

    def set_next_prompt_choice(self, value: str, ok: bool) -> None:
        """Set the next value returned by prompt_choice."""
        self._next_prompt_choice = (value, ok)

    def set_next_prompt_yes_no(self, value: bool) -> None:
        """Set the next value returned by prompt_yes_no."""
        self._next_prompt_yes_no = value

    def set_next_prompt_number(self, value: float | None, ok: bool) -> None:
        """Set the next value returned by prompt_number."""
        self._next_prompt_number = (value, ok)

    def set_next_prompt_datetime(self, value: datetime | None, ok: bool) -> None:
        """Set the next value returned by prompt_datetime."""
        self._next_prompt_datetime = (value, ok)

    def set_next_prompt_between(self, result: BetweenResult) -> None:
        """Set the next value returned by prompt_between."""
        self._next_prompt_between = result

    def set_next_prompt_compare(self, result: CompareResult) -> None:
        """Set the next value returned by prompt_compare."""
        self._next_prompt_compare = result

    def set_next_prompt_datetime_conversion(self, result: DateTimeConversionResult) -> None:
        """Set the next value returned by prompt_datetime_conversion."""
        self._next_prompt_datetime_conversion = result

    def set_next_prompt_boolean_conversion(self, result: BooleanConversionResult) -> None:
        """Set the next value returned by prompt_boolean_conversion."""
        self._next_prompt_boolean_conversion = result

    def set_next_prompt_category_conversion(self, result: CategoryConversionResult) -> None:
        """Set the next value returned by prompt_category_conversion."""
        self._next_prompt_category_conversion = result

    def set_next_prompt_category_rename(self, result: CategoryRenameResult) -> None:
        """Set the next value returned by prompt_category_rename."""
        self._next_prompt_category_rename = result

    def set_next_prompt_category_set_order(self, result: CategoryOrderResult) -> None:
        """Set the next value returned by prompt_category_set_order."""
        self._next_prompt_category_set_order = result

    def set_next_prompt_text_replace(self, result: TextReplaceResult) -> None:
        """Set the next value returned by prompt_text_replace."""
        self._next_prompt_text_replace = result

    def set_next_prompt_text_insert(self, result: TextInsertResult) -> None:
        """Set the next value returned by prompt_text_insert."""
        self._next_prompt_text_insert = result

    def set_next_prompt_value_replace(self, result: ValueReplaceResult) -> None:
        """Set the next value returned by prompt_value_replace."""
        self._next_prompt_value_replace = result

    def set_next_prompt_filter_match(
        self,
        result: TextFilterMatchResult,
    ) -> None:
        """Set the next value returned by prompt_filter_match."""
        self._next_prompt_filter_match = result

    def set_next_prompt_split_column(self, result: SplitColumnResult) -> None:
        """Set the next value returned by prompt_split_column."""
        self._next_prompt_split_column = result

    def set_next_prompt_merge_columns(self, result: MergeColumnsResult) -> None:
        """Set the next value returned by prompt_merge_columns."""
        self._next_prompt_merge_columns = result

    # ------------------------------------------------------------------
    # Message dialogs
    # ------------------------------------------------------------------

    def info(self, parent: QWidget, title: str, text: str) -> None:
        """Show an informational message box."""
        self.calls.append(("info", (title, text), {}))

    def warn(self, parent: QWidget, title: str, text: str) -> None:
        """Show a warning message box."""
        self.calls.append(("warn", (title, text), {}))

    def critical(self, parent: QWidget, title: str, text: str) -> None:
        """Show a critical error message box."""
        self.calls.append(("critical", (title, text), {}))

    # ------------------------------------------------------------------
    # Confirms
    # ------------------------------------------------------------------

    def confirm_profile_scope(self, parent: QWidget, **kwargs) -> ProfileChoice:
        """Show a confirmation dialog for profile scope."""
        self.calls.append(("confirm_profile_scope", (), kwargs))
        return self.default_profile_choice

    def confirm_delete(self, parent: QWidget, **kwargs) -> bool:
        """Show a confirmation dialog for deletion."""
        self.calls.append(("confirm_delete", (), kwargs))
        return self.default_confirm_delete

    # ------------------------------------------------------------------
    # Prompts
    # ------------------------------------------------------------------

    def prompt_text(self, parent: QWidget, **kwargs) -> tuple[str, bool]:
        """Show a prompt for text input."""
        self.calls.append(("prompt_text", (), kwargs))
        if self._next_prompt_text is not None:
            val = self._next_prompt_text
            self._next_prompt_text = None
            return val
        return "", True

    def prompt_choice(self, parent: QWidget, **kwargs) -> tuple[str, bool]:
        """Show a prompt for a choice from a list of options."""
        self.calls.append(("prompt_choice", (), kwargs))
        if self._next_prompt_choice is not None:
            val = self._next_prompt_choice
            self._next_prompt_choice = None
            return val
        choices = kwargs.get("choices") or []
        return (choices[0], True) if choices else ("", False)

    def prompt_yes_no(self, parent: QWidget, **kwargs) -> bool:
        """Show a yes/no confirmation dialog."""
        self.calls.append(("prompt_yes_no", (), kwargs))
        if self._next_prompt_yes_no is not None:
            val = self._next_prompt_yes_no
            self._next_prompt_yes_no = None
            return val
        return False

    def prompt_number(
        self,
        parent: QWidget,
        *,
        title: str,
        label: str,
        default: float | None,
        semantics: SeriesSemantics,
    ) -> tuple[float | int | None, bool]:
        """Show a prompt for numeric input."""
        self.calls.append((
            "prompt_number",
            (),
            {
                "title": title,
                "label": label,
                "default": default,
                "semantics": semantics,
            },
        ))

        if self._next_prompt_number is not None:
            val = self._next_prompt_number
            self._next_prompt_number = None
            return val

        return default, True

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
        self.calls.append((
            "prompt_datetime",
            (),
            {
                "title": title,
                "label": label,
                "default": default,
                "semantics": semantics,
            },
        ))

        if self._next_prompt_datetime is not None:
            val = self._next_prompt_datetime
            self._next_prompt_datetime = None
            return val

        return default, True

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
        """Show a prompt for a range."""
        self.calls.append((
            "prompt_between",
            (),
            {
                "title": title,
                "label_low": label_low,
                "label_high": label_high,
                "default_low": default_low,
                "default_high": default_high,
                "inclusive_default": inclusive_default,
                "semantics": semantics,
            },
        ))

        if self._next_prompt_between is not None:
            val = self._next_prompt_between
            self._next_prompt_between = None
            return val

        return {
            "low": default_low,
            "high": default_high,
            "inclusive": inclusive_default,
            "ok": True,
        }

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
        """Show a prompt for a comparison."""
        self.calls.append((
            "prompt_compare",
            (),
            {
                "title": title,
                "label_op": label_op,
                "label_value": label_value,
                "default_op": default_op,
                "default_value": default_value,
                "semantics": semantics,
            },
        ))

        if self._next_prompt_compare is not None:
            val = self._next_prompt_compare
            self._next_prompt_compare = None
            return val

        return {
            "op": default_op,
            "value": default_value,
            "ok": True,
        }

    def prompt_filter_match(
        self,
        parent: QWidget,
        *,
        title: str,
        label: str,
        default_value: str,
        default_case_sensitive: bool,
    ) -> TextFilterMatchResult:
        """Test implementation of filter contains dialog."""
        self.calls.append((
            "prompt_filter_match",
            (),
            {
                "title": title,
                "label": label,
                "default_value": default_value,
                "default_case_sensitive": default_case_sensitive,
            },
        ))

        if self._next_prompt_filter_match is not None:
            val = self._next_prompt_filter_match
            self._next_prompt_filter_match = None
            return val

        return {
            "value": default_value,
            "case_sensitive": default_case_sensitive,
            "ok": False,
        }

    def prompt_datetime_conversion(
        self,
        parent: QWidget,
        *,
        title: str,
        default_format_key: DateFormatKey,
        default_target: DateTimeTarget,
    ) -> DateTimeConversionResult:
        """Test implementation of datetime conversion dialog."""
        self.calls.append((
            "prompt_datetime_conversion",
            (),
            {
                "title": title,
                "default_format_key": default_format_key,
                "default_target": default_target,
            },
        ))

        if self._next_prompt_datetime_conversion is not None:
            val = self._next_prompt_datetime_conversion
            self._next_prompt_datetime_conversion = None
            return val

        # Default = cancelled dialog
        return {
            "format_key": default_format_key,
            "target": default_target,
            "ok": False,
        }

    def prompt_boolean_conversion(
        self,
        parent: QWidget,
        *,
        title: str,
        default_true_values: list[str],
        default_false_values: list[str],
    ) -> BooleanConversionResult:
        """Test implementation of boolean conversion dialog."""
        self.calls.append((
            "prompt_boolean_conversion",
            (),
            {
                "title": title,
                "default_true_values": default_true_values,
                "default_false_values": default_false_values,
            },
        ))

        if self._next_prompt_boolean_conversion is not None:
            val = self._next_prompt_boolean_conversion
            self._next_prompt_boolean_conversion = None
            return val

        # Default = cancelled dialog
        return {
            "true_values": list(default_true_values),
            "false_values": list(default_false_values),
            "ok": False,
        }

    def prompt_category_conversion(
        self,
        parent: QWidget,
        *,
        title: str,
        default_order: CategoryOrderKey,
        default_ordered: bool,
        default_strict: bool,
    ) -> CategoryConversionResult:
        """Test implementation of category conversion dialog."""
        self.calls.append((
            "prompt_category_conversion",
            (),
            {
                "title": title,
                "default_order": default_order,
                "default_ordered": default_ordered,
                "default_strict": default_strict,
            },
        ))

        if self._next_prompt_category_conversion is not None:
            val = self._next_prompt_category_conversion
            self._next_prompt_category_conversion = None
            return val

        # Default = cancelled dialog
        return {
            "order": default_order,
            "ordered": default_ordered,
            "strict": default_strict,
            "ok": False,
        }

    def prompt_category_rename(
        self,
        parent: QWidget,
        *,
        title: str,
        categories: list[str],
        default_old_value: str,
        default_new_value: str,
    ) -> CategoryRenameResult:
        """Test implementation of category rename dialog."""
        self.calls.append((
            "prompt_category_rename",
            (),
            {
                "title": title,
                "categories": list(categories),
                "default_old_value": default_old_value,
                "default_new_value": default_new_value,
            },
        ))

        if self._next_prompt_category_rename is not None:
            val = self._next_prompt_category_rename
            self._next_prompt_category_rename = None
            return val

        # Default = cancelled dialog
        return {
            "old": default_old_value,
            "new": default_new_value,
            "ok": False,
        }

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
        """Test implementation of category set order dialog."""
        self.calls.append((
            "prompt_category_set_order",
            (),
            {
                "title": title,
                "default_order_list": default_order_list,
                "default_ordered": default_ordered,
                "default_strict": default_strict,
                "default_append_missing_tail": default_append_missing_tail,
            },
        ))

        if self._next_prompt_category_set_order is not None:
            val = self._next_prompt_category_set_order
            self._next_prompt_category_set_order = None
            return val

        # Default = cancelled dialog
        return {
            "order_list": list(default_order_list),
            "ordered": default_ordered,
            "strict": default_strict,
            "append_missing_tail": default_append_missing_tail,
            "ok": False,
        }

    def prompt_text_replace(self, parent: QWidget, **kwargs) -> TextReplaceResult:
        """Show a prompt for text replacement."""
        self.calls.append(("prompt_text_replace", (), kwargs))
        if self._next_prompt_text_replace is not None:
            val = self._next_prompt_text_replace
            self._next_prompt_text_replace = None
            return val
        return {"old": "", "new": "", "case": True, "ok": False}

    def prompt_text_insert(self, parent: QWidget, **kwargs) -> TextInsertResult:
        """Show a prompt for text insertion."""
        self.calls.append(("prompt_text_insert", (), kwargs))
        if self._next_prompt_text_insert is not None:
            val = self._next_prompt_text_insert
            self._next_prompt_text_insert = None
            return val
        return {"insert": "", "position": 0, "ok": False}

    def prompt_value_replace(self, parent: QWidget, **kwargs) -> ValueReplaceResult:
        """Show a prompt for value replacement."""
        self.calls.append(("prompt_value_replace", (), kwargs))
        if self._next_prompt_value_replace is not None:
            val = self._next_prompt_value_replace
            self._next_prompt_value_replace = None
            return val
        return {"new_value": "", "replace_all": False, "ok": False}

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
        """Test implementation of split column dialog."""
        self.calls.append((
            "prompt_split_column",
            (),
            {
                "title": title,
                "column": column,
                "default_delimiter": default_delimiter,
                "default_keep_original": default_keep_original,
                "default_mode": default_mode,
            },
        ))

        if self._next_prompt_split_column is not None:
            val = self._next_prompt_split_column
            self._next_prompt_split_column = None
            return val

        # Default = cancelled dialog
        return {
            "delimiter": default_delimiter,
            "keep_original": default_keep_original,
            "mode": default_mode,
            "ok": False,
        }

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
        """Test implementation of merge columns dialog."""
        self.calls.append((
            "prompt_merge_columns",
            (),
            {
                "title": title,
                "all_columns": list(all_columns),
                "default_columns": list(default_columns),
                "default_delimiter": default_delimiter,
                "default_new_name": default_new_name,
                "default_keep_original": default_keep_original,
            },
        ))

        if self._next_prompt_merge_columns is not None:
            val = self._next_prompt_merge_columns
            self._next_prompt_merge_columns = None
            return val

        # Default = cancelled dialog
        return {
            "columns": list(default_columns),
            "delimiter": default_delimiter,
            "new_name": default_new_name,
            "keep_original": default_keep_original,
            "ok": False,
        }
