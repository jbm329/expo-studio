"""Controller for creating derived DataFrame columns."""

from __future__ import annotations

import logging
import uuid
from functools import partial
from typing import TYPE_CHECKING

from PyQt6.QtCore import QT_TR_NOOP
from PyQt6.QtWidgets import QDialog, QTableView, QWidget

from expo_jbm329.gui.dialogs.service.qt_dialog_service import QtDialogService
from expo_jbm329.gui.dialogs.workflows.derived_column.derived_column_dialog import (
    DerivedColumnDialog,
)
from expo_jbm329.services.data_operations.derived_column.derived_column_parser import (
    DerivedColumnFormulaError,
    FormulaValidationResult,
)
from expo_jbm329.services.data_operations.derived_column.derived_column_service import (
    DerivedColumnError,
    DerivedColumnSpec,
    create_derived_column,
    validate_derived_column_spec,
)
from expo_jbm329.utils.i18n_utils import translate, translate_fmt

if TYPE_CHECKING:
    from collections.abc import Callable

    import pandas as pd

    from expo_jbm329.gui.dialogs.service.dialog_service import DialogService
    from expo_jbm329.workbench.controllers.async_operation_controller import (
        AsyncOperationController,
    )


class DerivedColumnController:
    """Controller for derived column workflow."""

    # --- i18n markers (pylupdate6-visible) -----------------------------
    TR_DERIVED_COLUMN = QT_TR_NOOP("Derived column")
    TR_CREATED_COLUMN = QT_TR_NOOP("Derived column '{column_name}' created successfully.")
    TR_CREATING_COLUMN = QT_TR_NOOP("Creating derived column '{column_name}'")
    TR_VALID_FORMULA = QT_TR_NOOP("Valid formula.")

    # Errors
    TR_FAILURE = QT_TR_NOOP("Failure")

    # ---------------------------
    # Parser / formula errors
    # ---------------------------
    TR_INVALID_EXPRESSION = QT_TR_NOOP("Invalid expression.")
    TR_UNKNOWN = QT_TR_NOOP("Unknown error.")
    TR_MISSING_OPERATOR = QT_TR_NOOP("Operator missing before position {position}.")
    TR_UNSUPPORTED_CHARACTER = QT_TR_NOOP("Unsupported character '{char}' at position {position}.")
    TR_UNKNOWN_COLUMN = QT_TR_NOOP("Column '{column}' does not exist (position {position}).")
    TR_FORMULA_EMPTY = QT_TR_NOOP("Formula cannot be empty.")

    TR_UNCLOSED_COLUMN_REFERENCE = QT_TR_NOOP("Unclosed column reference at position {position}.")
    TR_EMPTY_COLUMN_REFERENCE = QT_TR_NOOP("Empty column reference at position {position}.")
    TR_MISSING_OPERAND_BEFORE_OPERATOR = QT_TR_NOOP(
        "Missing operand before operator '{operator}' at position {position}."
    )
    TR_MISSING_OPERAND_BEFORE_CLOSING_PAREN = QT_TR_NOOP("Missing operand before ')' at position {position}.")
    TR_MISSING_OPERATOR_BEFORE_OPENING_PAREN = QT_TR_NOOP("Missing operator before '(' at position {position}.")
    TR_UNMATCHED_CLOSING_PAREN = QT_TR_NOOP("Unmatched closing parenthesis at position {position}.")
    TR_UNMATCHED_OPENING_PAREN = QT_TR_NOOP("Unmatched opening parenthesis.")
    TR_FORMULA_ENDS_WITH_OPERATOR = QT_TR_NOOP("Formula cannot end with operator '{operator}'.")
    TR_FORMULA_INCOMPLETE = QT_TR_NOOP("Incomplete formula.")
    TR_FORMULA_MISSING_VALUE = QT_TR_NOOP("Formula must contain at least one value.")
    TR_UNSUPPORTED_TOKEN = QT_TR_NOOP("Unsupported token '{token}'.")
    TR_UNSUPPORTED_OPERATOR = QT_TR_NOOP("Unsupported operator '{token}'.")
    TR_UNCLOSED_STRING = QT_TR_NOOP("Unclosed text literal at position {position}. Use single quotes around text.")
    TR_INVALID_NUMBER = QT_TR_NOOP("Invalid or nonfinite number at position {position}.")
    TR_EXPECTED_TOKEN = QT_TR_NOOP("Expected '{expected}' at position {position}.")
    TR_EXPECTED_EXPRESSION = QT_TR_NOOP("Expected a value or expression at position {position}.")
    TR_EXPECTED_LITERAL = QT_TR_NOOP("Expected a literal value in the IN list at position {position}.")
    TR_UNEXPECTED_TOKEN = QT_TR_NOOP("Unexpected token '{token}' at position {position}.")
    TR_NESTING_LIMIT = QT_TR_NOOP("Formula nesting is too deep (limit {limit}). Simplify the expression.")
    TR_INVALID_OPERAND_TYPE = QT_TR_NOOP(
        "Incompatible operand at position {position}. Use numbers for arithmetic and conditions for Boolean logic."
    )
    TR_INCOMPATIBLE_OPERANDS = QT_TR_NOOP(
        "Comparison operands must have compatible types at position {position}. Do not mix text and numbers."
    )
    TR_INCOMPATIBLE_BRANCHES = QT_TR_NOOP("IF results must both be text or both be numeric. NULL is allowed in either.")
    TR_INVALID_RESULT_TYPE = QT_TR_NOOP("The formula must return text, a number, or NULL, not a condition.")
    TR_UNSUPPORTED_COLUMN_TYPE = QT_TR_NOOP(
        "Unsupported column type at position {position}. Use numeric or text values, or test with IS NULL."
    )
    TR_NON_TEXT_COLUMN = QT_TR_NOOP("Column '{column}' contains nontext values. Text expressions require text values.")
    TR_EXPRESSION_EVALUATION_FAILED = QT_TR_NOOP(
        "Could not evaluate the expression at position {position}. Check operand values and types."
    )
    TR_DATETIME_OPERAND_REQUIRED = QT_TR_NOOP(
        "Function '{token}' at position {position} requires a datetime column. Convert text dates before using it."
    )

    # ---------------------------
    # Service / runtime errors
    # ---------------------------

    TR_MISSING_OUTPUT_COLUMN_NAME = QT_TR_NOOP("Column name is required.")
    TR_INVALID_OUTPUT_COLUMN_NAME_CHARS = QT_TR_NOOP("Column name cannot contain '[' or ']'.")
    TR_OUTPUT_COLUMN_EXISTS = QT_TR_NOOP("Column '{column}' already exists.")
    TR_NON_NUMERIC_COLUMN = QT_TR_NOOP("Column '{column}' is not numeric.")
    TR_COLUMN_NOT_UNIQUE = QT_TR_NOOP("Column '{column}' is not unique.")
    TR_UNKNOWN_COLUMN_RUNTIME = QT_TR_NOOP("Column '{column}' does not exist.")
    TR_MISSING_OPERAND_RUNTIME = QT_TR_NOOP("Missing operand for operator '{operator}'.")
    TR_UNSUPPORTED_TOKEN_RUNTIME = QT_TR_NOOP("Unsupported token '{token}' in evaluation.")
    TR_INVALID_EVALUATION_RESULT = QT_TR_NOOP("Formula did not produce a valid result.")
    TR_OPERATOR_APPLICATION_FAILED = QT_TR_NOOP("Error applying operator '{operator}'.")
    TR_UNSUPPORTED_OPERATOR_RUNTIME = QT_TR_NOOP("Unsupported operator '{operator}'.")
    TR_UNSUPPORTED_OUTPUT_DTYPE = QT_TR_NOOP("Unsupported output type '{dtype}'.")
    TR_RESULT_CONVERSION_FAILED = QT_TR_NOOP("Could not convert result to '{dtype}'.")
    TR_EVALUATION_FAILED = QT_TR_NOOP("Failed to evaluate formula.")

    @staticmethod
    def _tr(text: str) -> str:
        return translate("DerivedColumnController", text)

    @staticmethod
    def _tr_fmt(text: str, **kwargs: object) -> str:
        return translate_fmt("DerivedColumnController", text, **kwargs)

    __slots__ = (
        "_apply_to_view",
        "_async_ops",
        "_dialogs",
        "_logger",
        "_main_window",
    )

    def __init__(
        self,
        *,
        async_ops: AsyncOperationController,
        apply_to_view: Callable[[QTableView, pd.DataFrame, str], None],
        dialogs: DialogService | None = None,
        main_window: QWidget,
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialize controller.

        Args:
            async_ops: Async operation controller.
            apply_to_view: Callback for applying a result to its originating view.
            dialogs: Dialog service for error/info dialogs.
            main_window: Parent window.
            logger: Optional logger.
        """
        self._async_ops = async_ops
        self._apply_to_view = apply_to_view
        self._dialogs = dialogs if dialogs is not None else QtDialogService()
        self._logger = logger if logger is not None else logging.getLogger("applogger.ui")
        self._main_window = main_window

    # ==================================================================
    # Public API
    # ==================================================================

    def create_derived_column(self, view: QTableView, df: pd.DataFrame, column: int) -> None:
        """Open the dialog and insert a derived column after the clicked header.

        Args:
            view: Originating result view.
            df: Source dataset resolved from the originating view.
            column: Zero-based position of the clicked column.

        Raises:
            IndexError: If the clicked column is outside the source dataset.
        """
        if not 0 <= column < len(df.columns):
            msg = f"Invalid source column index: {column}"
            raise IndexError(msg)

        dialog = DerivedColumnDialog(
            df=df,
            validate_callback=partial(self._validate, df),
            parent=self._main_window,
        )

        result = dialog.exec()

        if result != QDialog.DialogCode.Accepted:
            return

        spec = dialog.get_result()

        if spec is None:
            return

        spec = DerivedColumnSpec(
            column_name=spec.column_name.strip(),
            formula=spec.formula.strip(),
            overwrite_existing=spec.overwrite_existing,
            output_dtype=spec.output_dtype,
            replace_inf_with_na=spec.replace_inf_with_na,
            month_labels=spec.month_labels,
        )

        self._run_create_derived_column(view, df, spec, insertion_index=column + 1)

    # ==================================================================
    # Validation
    # ==================================================================

    def _validate(self, df: pd.DataFrame, column_name: str, formula: str) -> tuple[FormulaValidationResult, str]:
        """Validation callback used by dialog.

        Args:
            df: Source dataset captured when the dialog was opened.
            column_name: Proposed column name.
            formula: Formula string.

        Returns:
            Structured validation result and localized message.
        """
        spec = DerivedColumnSpec(
            column_name=column_name,
            formula=formula,
        )

        result = validate_derived_column_spec(df, spec)

        if result.ok:
            return result, self._tr(self.TR_VALID_FORMULA)

        exc = result.error
        if exc is None:
            exc = DerivedColumnFormulaError(code="unknown")
        return result, self._format_error(exc)

    # ==================================================================
    # Internal helpers
    # ==================================================================
    def _run_create_derived_column(
        self,
        view: QTableView,
        df: pd.DataFrame,
        spec: DerivedColumnSpec,
        *,
        insertion_index: int,
    ) -> None:
        """Create a derived column asynchronously and apply the result."""
        safe_df = df
        safe_spec = spec
        corr_id = uuid.uuid4().hex

        self._logger.debug(
            "DerivedColumnController: scheduling derived column creation (column=%s, formula=%s, corr=%s).",
            safe_spec.column_name,
            safe_spec.formula,
            corr_id,
        )

        def _work(
            *,
            progress_cb: Callable[[int], None] | None = None,
            cancel_cb: Callable[[], bool] | None = None,
            **_: object,
        ) -> tuple[bool, pd.DataFrame | None, Exception | None] | None:
            del progress_cb
            if cancel_cb and cancel_cb():
                return None

            try:
                new_df = create_derived_column(safe_df, safe_spec, insertion_index=insertion_index)

            except (DerivedColumnError, DerivedColumnFormulaError) as exc:
                return False, None, exc
            else:
                return True, new_df, None

        def _apply_result(result: tuple[bool, pd.DataFrame | None, Exception | None] | None) -> None:
            if result is None:
                return

            ok, new_df, exc = result

            if not ok:
                if exc is None:
                    exc = DerivedColumnError(code="unknown")
                self._logger.warning(
                    "DerivedColumnController: derived column failed (column=%s, corr=%s): %s",
                    safe_spec.column_name,
                    corr_id,
                    exc,
                )

                self._dialogs.critical(
                    parent=self._main_window,
                    title=self._tr(self.TR_FAILURE),
                    text=self._format_error(exc),
                )
                return

            if new_df is None:
                return

            self._logger.info(
                "DerivedColumnController: derived column applied (column=%s, formula=%s, corr=%s).",
                safe_spec.column_name,
                safe_spec.formula,
                corr_id,
            )

            self._apply_result(view, new_df, safe_spec)

        self._async_ops.run_dataframe_operation(
            view=view,
            runner="pool",
            work=_work,
            apply_result=_apply_result,
            busy_message=self._tr_fmt(
                self.TR_CREATING_COLUMN,
                column_name=safe_spec.column_name,
            ),
            scope=f"derived_column:{safe_spec.column_name}",
            operation_name=self._tr(self.TR_DERIVED_COLUMN),
            corr_id=corr_id,
        )

    def _apply_result(
        self,
        view: QTableView,
        new_df: pd.DataFrame,
        spec: DerivedColumnSpec,
    ) -> None:
        """Apply the result DataFrame back to its originating result view.

        Args:
            view: Originating result view.
            new_df: Updated DataFrame.
            spec: Column specification.
        """
        try:
            self._apply_to_view(
                view,
                new_df,
                self._tr_fmt(self.TR_CREATED_COLUMN, column_name=spec.column_name),
            )

        except (
            AttributeError,
            ConnectionError,
            FileNotFoundError,
            IndexError,
            KeyError,
            LookupError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as exc:
            self._logger.exception("Failed to apply derived column result")

            self._dialogs.critical(
                parent=self._main_window,
                title=self._tr(self.TR_FAILURE),
                text=str(exc),
            )

    def _format_error(self, exc: Exception) -> str:
        code = getattr(exc, "code", "unknown")
        ctx = getattr(exc, "context", {})

        expression_errors = {
            "datetime_operand_required": self.TR_DATETIME_OPERAND_REQUIRED,
            "unclosed_string_literal": self.TR_UNCLOSED_STRING,
            "invalid_number_literal": self.TR_INVALID_NUMBER,
            "expected_token": self.TR_EXPECTED_TOKEN,
            "expected_expression": self.TR_EXPECTED_EXPRESSION,
            "expected_literal": self.TR_EXPECTED_LITERAL,
            "unexpected_token": self.TR_UNEXPECTED_TOKEN,
            "expression_nesting_limit": self.TR_NESTING_LIMIT,
            "invalid_operand_type": self.TR_INVALID_OPERAND_TYPE,
            "incompatible_operand_types": self.TR_INCOMPATIBLE_OPERANDS,
            "incompatible_branch_types": self.TR_INCOMPATIBLE_BRANCHES,
            "invalid_result_type": self.TR_INVALID_RESULT_TYPE,
            "unsupported_column_type": self.TR_UNSUPPORTED_COLUMN_TYPE,
            "non_text_column": self.TR_NON_TEXT_COLUMN,
            "expression_evaluation_failed": self.TR_EXPRESSION_EVALUATION_FAILED,
        }
        if code in expression_errors:
            return self._tr_fmt(
                expression_errors[code],
                position=str(ctx.get("position", "?")),
                expected=str(ctx.get("expected", "")),
                token=str(ctx.get("token", "")),
                limit=str(ctx.get("limit", "")),
                column=str(ctx.get("column", "")),
            )

        # ---------------------------
        # Parser / formula errors
        # ---------------------------

        if code == "formula_empty":
            return self._tr(self.TR_FORMULA_EMPTY)

        if code == "unknown_column":
            return self._tr_fmt(
                self.TR_UNKNOWN_COLUMN,
                column=str(ctx.get("column", "")),
                position=str(ctx.get("position", "?")),
            )

        if code == "unsupported_character":
            return self._tr_fmt(
                self.TR_UNSUPPORTED_CHARACTER,
                char=str(ctx.get("char", "")),
                position=str(ctx.get("position", "?")),
            )

        if code == "unclosed_column_reference":
            return self._tr_fmt(
                self.TR_UNCLOSED_COLUMN_REFERENCE,
                position=str(ctx.get("position", "?")),
            )

        if code == "empty_column_reference":
            return self._tr_fmt(
                self.TR_EMPTY_COLUMN_REFERENCE,
                position=str(ctx.get("position", "?")),
            )

        if code == "missing_operator_before_operand":
            return self._tr_fmt(
                self.TR_MISSING_OPERATOR,
                position=str(ctx.get("position", "?")),
            )

        if code == "missing_operand_before_operator":
            return self._tr_fmt(
                self.TR_MISSING_OPERAND_BEFORE_OPERATOR,
                operator=str(ctx.get("operator", "")),
                position=str(ctx.get("position", "?")),
            )

        if code == "missing_operand_before_closing_parenthesis":
            return self._tr_fmt(
                self.TR_MISSING_OPERAND_BEFORE_CLOSING_PAREN,
                position=str(ctx.get("position", "?")),
            )

        if code == "missing_operand_before_opening_parenthesis":
            return self._tr_fmt(
                self.TR_MISSING_OPERATOR_BEFORE_OPENING_PAREN,
                position=str(ctx.get("position", "?")),
            )

        if code == "unmatched_closing_parenthesis":
            return self._tr_fmt(
                self.TR_UNMATCHED_CLOSING_PAREN,
                position=str(ctx.get("position", "?")),
            )

        if code == "unmatched_opening_parenthesis":
            return self._tr(self.TR_UNMATCHED_OPENING_PAREN)

        if code == "formula_ends_with_operator":
            return self._tr_fmt(
                self.TR_FORMULA_ENDS_WITH_OPERATOR,
                operator=str(ctx.get("operator", "")),
            )

        if code == "formula_incomplete":
            return self._tr(self.TR_FORMULA_INCOMPLETE)

        if code == "formula_missing_value":
            return self._tr(self.TR_FORMULA_MISSING_VALUE)

        if code == "unsupported_token":
            return self._tr_fmt(
                self.TR_UNSUPPORTED_TOKEN,
                token=str(ctx.get("token", "")),
            )

        if code == "unsupported_operator":
            return self._tr_fmt(
                self.TR_UNSUPPORTED_OPERATOR,
                token=str(ctx.get("token", "")),
            )

        # ---------------------------
        # Service / runtime errors
        # ---------------------------

        if code == "missing_output_column_name":
            return self._tr(self.TR_MISSING_OUTPUT_COLUMN_NAME)

        if code == "invalid_output_column_name_characters":
            return self._tr(self.TR_INVALID_OUTPUT_COLUMN_NAME_CHARS)

        if code == "output_column_exists":
            return self._tr_fmt(
                self.TR_OUTPUT_COLUMN_EXISTS,
                column=str(ctx.get("column", "")),
            )

        if code == "non_numeric_column":
            return self._tr_fmt(
                self.TR_NON_NUMERIC_COLUMN,
                column=str(ctx.get("column", "")),
            )

        if code == "column_not_unique":
            return self._tr_fmt(
                self.TR_COLUMN_NOT_UNIQUE,
                column=str(ctx.get("column", "")),
            )

        if code == "unknown_column_runtime":
            return self._tr_fmt(
                self.TR_UNKNOWN_COLUMN_RUNTIME,
                column=str(ctx.get("column", "")),
            )

        if code == "missing_operand_runtime":
            return self._tr_fmt(
                self.TR_MISSING_OPERAND_RUNTIME,
                operator=str(ctx.get("operator", "")),
            )

        if code == "unsupported_token_runtime":
            return self._tr_fmt(
                self.TR_UNSUPPORTED_TOKEN_RUNTIME,
                token=str(ctx.get("token", "")),
            )

        if code == "invalid_evaluation_result":
            return self._tr(self.TR_INVALID_EVALUATION_RESULT)

        if code == "operator_application_failed":
            return self._tr_fmt(
                self.TR_OPERATOR_APPLICATION_FAILED,
                operator=str(ctx.get("operator", "")),
            )

        if code == "unsupported_operator_runtime":
            return self._tr_fmt(
                self.TR_UNSUPPORTED_OPERATOR_RUNTIME,
                operator=str(ctx.get("operator", "")),
            )

        if code == "unsupported_output_dtype":
            return self._tr_fmt(
                self.TR_UNSUPPORTED_OUTPUT_DTYPE,
                dtype=str(ctx.get("dtype", "")),
            )

        if code == "result_conversion_failed":
            return self._tr_fmt(
                self.TR_RESULT_CONVERSION_FAILED,
                dtype=str(ctx.get("dtype", "")),
            )

        if code == "evaluation_failed":
            return self._tr(self.TR_EVALUATION_FAILED)

        # ---------------------------
        # fallback
        # ---------------------------

        return self._tr(self.TR_UNKNOWN)
