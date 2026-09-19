"""Facade implementation delegating to dialog modules."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Literal

from PyQt6.QtWidgets import QMessageBox, QWidget

from expo_jbm329.gui.dialogs.service.common.localization import (
    localize_messagebox_buttons,
)
from expo_jbm329.gui.dialogs.service.common.window_hints import (
    apply_dialog_window_hints,
)
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
    from expo_jbm329.services.data_operations.category_orders import CategoryOrderKey
    from expo_jbm329.services.data_operations.datetime_formats import DateFormatKey
    from expo_jbm329.services.data_profile.semantics import SeriesSemantics


class QtDialogService(DialogService):
    """Qt-based facade for all user-facing dialogs.

    This class contains no dialog layout logic of its own (except simple
    message boxes). All complex dialogs are delegated to domain-specific
    modules under dialogs/service/.
    """

    # ------------------------------------------------------------------
    # Message dialogs (kept inline: trivial and ubiquitous)
    # ------------------------------------------------------------------

    def info(self, parent: QWidget, title: str, text: str) -> None:
        """Show an informational message box."""
        msg = QMessageBox(parent)
        msg.setWindowTitle(title)
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setText(text)
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        localize_messagebox_buttons(msg)
        apply_dialog_window_hints(msg, min_width=600)
        msg.exec()

    def warn(self, parent: QWidget, title: str, text: str) -> None:
        """Show a warning message box."""
        msg = QMessageBox(parent)
        msg.setWindowTitle(title)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setText(text)
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        localize_messagebox_buttons(msg)
        apply_dialog_window_hints(msg, min_width=600)
        msg.exec()

    def critical(self, parent: QWidget, title: str, text: str) -> None:
        """Show a critical error message box."""
        msg = QMessageBox(parent)
        msg.setWindowTitle(title)
        msg.setIcon(QMessageBox.Icon.Critical)
        msg.setText(text)
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        localize_messagebox_buttons(msg)
        apply_dialog_window_hints(msg, min_width=600)
        msg.exec()

    # ------------------------------------------------------------------
    # Confirms / choices
    # ------------------------------------------------------------------

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
        from expo_jbm329.gui.dialogs.service.prompts.choice import (
            confirm_profile_scope,
        )

        return confirm_profile_scope(
            parent,
            title=title,
            text=text,
            active_tab_text=active_tab_text,
            all_tabs_text=all_tabs_text,
        )

    def confirm_delete(
        self,
        parent: QWidget,
        *,
        title: str | None,
        name: str,
        full_path: str,
        size_hint: str | None = None,
    ) -> bool:
        """Show a confirmation dialog for deletion."""
        from expo_jbm329.gui.dialogs.service.prompts.choice import (
            confirm_delete,
        )

        return confirm_delete(parent, title=title, name=name, full_path=full_path, size_hint=size_hint)

    def prompt_choice(
        self,
        parent: QWidget,
        *,
        title: str,
        label: str,
        choices: list[str],
        default_index: int = 0,
        editable: bool = False,
    ) -> tuple[str, bool]:
        """Show a prompt for a choice from a list of options."""
        from expo_jbm329.gui.dialogs.service.prompts.choice import (
            prompt_choice,
        )

        return prompt_choice(
            parent,
            title=title,
            label=label,
            choices=choices,
            default_index=default_index,
            editable=editable,
        )

    def prompt_yes_no(
        self,
        parent: QWidget,
        *,
        title: str,
        text: str,
        informative: str | None = None,
        default_yes: bool = False,
    ) -> bool:
        """Show a yes/no confirmation dialog."""
        from expo_jbm329.gui.dialogs.service.prompts.choice import (
            prompt_yes_no,
        )

        return prompt_yes_no(
            parent,
            title=title,
            text=text,
            informative=informative,
            default_yes=default_yes,
        )

    # ------------------------------------------------------------------
    # Numeric / datetime prompts
    # ------------------------------------------------------------------

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
        from expo_jbm329.gui.dialogs.service.prompts.value_input import (
            prompt_value,
        )

        value, ok = prompt_value(
            parent,
            title=title,
            label=label,
            default=default,
            semantics=semantics,
        )

        if not ok:
            return None, False

        # Explicit type narrowing (guaranteed by semantics)
        if isinstance(value, (int, float)):
            return value, True

        # Should never happen, but keeps type checkers satisfied
        return None, False

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
        """Prompt for numeric or datetime range."""
        from expo_jbm329.gui.dialogs.service.prompts.compare_between import prompt_between

        return prompt_between(
            parent,
            title=title,
            label_low=label_low,
            label_high=label_high,
            default_low=default_low,
            default_high=default_high,
            inclusive_default=inclusive_default,
            semantics=semantics,
        )

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
        """Prompt for comparison between two values."""
        from expo_jbm329.gui.dialogs.service.prompts.compare_between import (
            prompt_compare,
        )

        return prompt_compare(
            parent,
            title=title,
            label_op=label_op,
            label_value=label_value,
            default_op=default_op,
            default_value=default_value,
            semantics=semantics,
        )

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
        from expo_jbm329.gui.dialogs.service.prompts.value_input import (
            prompt_value,
        )

        value, ok = prompt_value(
            parent,
            title=title,
            label=label,
            default=default,
            semantics=semantics,
        )
        if not ok:
            return None, False
        if isinstance(value, datetime) or value is None:
            return value, True
        return None, False

    # ------------------------------------------------------------------
    # Text prompts
    # ------------------------------------------------------------------

    def prompt_text(
        self,
        parent: QWidget,
        *,
        title: str,
        label: str,
        default: str | None = None,
    ) -> tuple[str, bool]:
        """Show a prompt for text input."""
        from expo_jbm329.gui.dialogs.service.prompts.text import (
            prompt_text,
        )

        return prompt_text(parent, title=title, label=label, default=default)

    def prompt_text_replace(
        self,
        parent: QWidget,
        *,
        title: str,
        default_old: str = "",
        default_new: str = "",
        default_case: bool = True,
    ) -> TextReplaceResult:
        """Show a prompt for text replacement."""
        from expo_jbm329.gui.dialogs.service.prompts.text import (
            prompt_text_replace,
        )

        return prompt_text_replace(
            parent,
            title=title,
            default_old=default_old,
            default_new=default_new,
            default_case=default_case,
        )

    def prompt_text_insert(
        self,
        parent: QWidget,
        *,
        title: str,
        default_insert: str = "",
        default_position: int = 0,
    ) -> TextInsertResult:
        """Show a prompt for text insertion."""
        from expo_jbm329.gui.dialogs.service.prompts.text import (
            prompt_text_insert,
        )

        return prompt_text_insert(
            parent,
            title=title,
            default_insert=default_insert,
            default_position=default_position,
        )

    def prompt_value_replace(
        self,
        parent: QWidget,
        *,
        title: str,
        column: str,
        current_value: str,
        default_new_value: str = "",
        default_replace_all: bool = False,
    ) -> ValueReplaceResult:
        """Show a prompt for value replacement."""
        from expo_jbm329.gui.dialogs.service.prompts.text import (
            prompt_value_replace,
        )

        return prompt_value_replace(
            parent,
            title=title,
            column=column,
            current_value=current_value,
            default_new_value=default_new_value,
            default_replace_all=default_replace_all,
        )

    def prompt_filter_match(
        self,
        parent: QWidget,
        *,
        title: str,
        label: str,
        default_value: str,
        default_case_sensitive: bool = True,
    ) -> TextFilterMatchResult:
        """Show a prompt for text-based match filtering (e.g. contains, equals)."""
        from expo_jbm329.gui.dialogs.service.prompts.filter_match import (
            prompt_filter_match,
        )

        return prompt_filter_match(
            parent,
            title=title,
            label=label,
            default_value=default_value,
            default_case_sensitive=default_case_sensitive,
        )

    # ------------------------------------------------------------------
    # Category dialogs
    # ------------------------------------------------------------------

    def prompt_category_conversion(
        self,
        parent: QWidget,
        *,
        title: str,
        default_order: CategoryOrderKey,
        default_ordered: bool,
        default_strict: bool,
    ) -> CategoryConversionResult:
        """Show a prompt for category conversion."""
        from expo_jbm329.gui.dialogs.service.categories.conversion import (
            prompt_category_conversion,
        )

        return prompt_category_conversion(
            parent,
            title=title,
            default_order=default_order,
            default_ordered=default_ordered,
            default_strict=default_strict,
        )

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
        from expo_jbm329.gui.dialogs.service.categories.rename import (
            prompt_category_rename,
        )

        return prompt_category_rename(
            parent,
            title=title,
            categories=categories,
            default_old_value=default_old_value,
            default_new_value=default_new_value,
        )

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
        from expo_jbm329.gui.dialogs.service.categories.order import (
            prompt_category_set_order,
        )

        return prompt_category_set_order(
            parent,
            title=title,
            default_order_list=default_order_list,
            default_ordered=default_ordered,
            default_strict=default_strict,
            default_append_missing_tail=default_append_missing_tail,
        )

    # ------------------------------------------------------------------
    # Datetime conversion dialog
    # ------------------------------------------------------------------

    def prompt_datetime_conversion(
        self,
        parent: QWidget,
        *,
        title: str,
        default_format_key: DateFormatKey,
        default_target: DateTimeTarget,
    ) -> DateTimeConversionResult:
        """Show a prompt for datetime conversion."""
        from expo_jbm329.gui.dialogs.service.prompts.datetime_conversion import (
            prompt_datetime_conversion,
        )

        return prompt_datetime_conversion(
            parent,
            title=title,
            default_format_key=default_format_key,
            default_target=default_target,
        )

    # ------------------------------------------------------------------
    # Boolean conversion dialog
    # ------------------------------------------------------------------

    def prompt_boolean_conversion(
        self,
        parent: QWidget,
        *,
        title: str,
        default_true_values: list[str],
        default_false_values: list[str],
    ) -> BooleanConversionResult:
        """Show a prompt for boolean conversion."""
        from expo_jbm329.gui.dialogs.service.prompts.boolean_conversion import (
            prompt_boolean_conversion,
        )

        return prompt_boolean_conversion(
            parent,
            title=title,
            default_true_values=default_true_values,
            default_false_values=default_false_values,
        )

    # ------------------------------------------------------------------
    # Column split / join dialogs
    # ------------------------------------------------------------------

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
        """Show a prompt for splitting a column."""
        from expo_jbm329.gui.dialogs.service.prompts.column_operations import (
            prompt_split_column,
        )

        return prompt_split_column(
            parent,
            title=title,
            column=column,
            default_delimiter=default_delimiter,
            default_keep_original=default_keep_original,
            default_mode=default_mode,
        )

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

        This is a thin facade that delegates all UI logic to the dialog module.
        No validation or transformation is performed here.
        """
        from expo_jbm329.gui.dialogs.service.prompts.column_operations import (
            prompt_merge_columns,
        )

        return prompt_merge_columns(
            parent,
            title=title,
            all_columns=all_columns,
            default_columns=default_columns,
            default_delimiter=default_delimiter,
            default_new_name=default_new_name,
            default_keep_original=default_keep_original,
        )
