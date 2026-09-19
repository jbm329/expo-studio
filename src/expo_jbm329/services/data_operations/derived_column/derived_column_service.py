"""Service for creating numeric derived DataFrame columns.

This module provides the service layer for creating derived columns from
simple numeric formulas.

Supported phase 1 features:
    - Numeric constants
    - Numeric column references using [Column Name]
    - Operators: +, -, *, /
    - Parentheses
    - Nullable Float64 output

Examples:
    [A] + [B]
    [A] / [B] * 100
    ([A] + [B]) / 2
    10
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import numpy as np
import pandas as pd

from expo_jbm329.services.data_operations.convert import to_nullable_float_series
from expo_jbm329.services.data_operations.derived_column.derived_column_parser import (
    DerivedColumnFormulaError,
    FormulaToken,
    FormulaTokenType,
    FormulaValidationResult,
    parse_formula_to_rpn,
    validate_formula,
)
from expo_jbm329.services.data_operations.dtypes import (
    get_numeric_columns,
    is_numeric_series,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

logger = logging.getLogger("applogger.service")


# =====================================================================
# Exceptions
# =====================================================================


class DerivedColumnError(ValueError):
    """Structured error for derived column operations."""

    def __init__(
        self,
        code: str,
        *,
        context: dict[str, object] | None = None,
        message: str | None = None,
    ) -> None:
        """Initialize DerivedColumnError.

        Args:
            code: Error code.
            context: Additional context for the error.
            message: Custom error message. Defaults to error code if not provided.
        """
        self.code = code
        self.context = context or {}
        self.message = message or code

        super().__init__(self.message)

    def __repr__(self) -> str:
        """Return a string representation of the error."""
        return f"{self.__class__.__name__}(code={self.code!r}, context={self.context!r})"


# =====================================================================
# Models
# =====================================================================


@dataclass(frozen=True, slots=True)
class DerivedColumnSpec:
    """Specification for creating a derived numeric column.

    Attributes:
        column_name: Name of the output column.
        formula: Formula expression entered by the user.
        overwrite_existing: Whether an existing column may be overwritten.
        output_dtype: Output dtype strategy. Phase 1 defaults to nullable float.
        replace_inf_with_na: Whether inf/-inf should be converted to pd.NA.
    """

    column_name: str
    formula: str
    overwrite_existing: bool = False
    output_dtype: Literal["Float64"] = "Float64"
    replace_inf_with_na: bool = True


@dataclass(frozen=True, slots=True)
class DerivedColumnPreview:
    """Preview result for a derived column formula.

    Attributes:
        ok: Whether preview evaluation succeeded.
        message: Validation or evaluation message.
        data: Optional preview DataFrame.
    """

    ok: bool
    message: str = ""
    data: pd.DataFrame | None = None


# Type alias for formula evaluation stack values.
_Operand = pd.Series | float


# =====================================================================
# Public API
# =====================================================================


def validate_derived_column_spec(
    df: pd.DataFrame,
    spec: DerivedColumnSpec,
) -> FormulaValidationResult:
    """Validate a derived column specification.

    Args:
        df: Source DataFrame.
        spec: Derived column specification.

    Returns:
        FormulaValidationResult describing whether the formula is valid.

    Notes:
        This validates formula syntax and column references. It does not
        evaluate the expression on the DataFrame.
    """
    try:
        _validate_column_name(df, spec)

        numeric_columns = set(get_numeric_columns(df))
        return validate_formula(spec.formula, numeric_columns)

    except DerivedColumnError as exc:
        return FormulaValidationResult(ok=False, error=DerivedColumnFormulaError(exc.code, context=exc.context))


def create_derived_column(
    df: pd.DataFrame,
    spec: DerivedColumnSpec,
) -> pd.DataFrame:
    """Create a derived numeric column from a formula.

    Args:
        df: Source DataFrame.
        spec: Derived column specification.

    Returns:
        A new DataFrame with the derived column added or overwritten.

    Raises:
        DerivedColumnError: If the specification is invalid or evaluation fails.
    """
    output_column = _normalized_column_name(spec)

    logger.debug(
        "Creating derived column (column=%r, formula=%r, overwrite=%s)",
        output_column,
        spec.formula,
        spec.overwrite_existing,
    )

    _validate_column_name(df, spec)

    numeric_columns = set(get_numeric_columns(df))

    try:
        rpn = parse_formula_to_rpn(spec.formula, numeric_columns)
        result = evaluate_rpn(df, rpn)

    except DerivedColumnFormulaError:
        raise  # propagate unchanged

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
        logger.exception(
            "Failed evaluating derived column formula (column=%r, formula=%r)",
            output_column,
            spec.formula,
        )

        msg = "evaluation_failed"
        raise DerivedColumnError(
            msg,
            context={"error": str(exc)},
        ) from exc

    result_series = _normalize_result_series(
        result=result,
        index=df.index,
        output_dtype=spec.output_dtype,
        replace_inf_with_na=spec.replace_inf_with_na,
    )

    new_df = df.copy()

    if output_column in new_df.columns and spec.overwrite_existing:
        new_df[output_column] = result_series
    else:
        new_df.insert(len(new_df.columns), output_column, result_series)

    logger.info(
        "Derived column created (column=%r, rows=%s, dtype=%s)",
        output_column,
        len(new_df),
        new_df[output_column].dtype,
    )

    return new_df


def preview_derived_column(
    df: pd.DataFrame,
    spec: DerivedColumnSpec,
    *,
    rows: int = 20,
) -> DerivedColumnPreview:
    """Evaluate a derived column formula on a small preview sample.

    Args:
        df: Source DataFrame.
        spec: Derived column specification.
        rows: Number of rows to include in the preview.

    Returns:
        DerivedColumnPreview with success status and optional preview data.
    """
    try:
        sample = df.head(max(1, int(rows))).copy()
        result = create_derived_column(sample, spec)

        preview_columns = _build_preview_columns(
            df=sample,
            spec=spec,
            result_column=_normalized_column_name(spec),
        )

        return DerivedColumnPreview(
            ok=True,
            message="",
            data=result.loc[:, preview_columns],
        )

    except (DerivedColumnError, DerivedColumnFormulaError):
        return DerivedColumnPreview(
            ok=False,
            message="",
            data=None,
        )


def evaluate_rpn(
    df: pd.DataFrame,
    rpn_tokens: Iterable[FormulaToken],
) -> _Operand:
    """Evaluate RPN tokens against a DataFrame.

    Args:
        df: Source DataFrame.
        rpn_tokens: Formula tokens in Reverse Polish Notation.

    Returns:
        A pandas Series or scalar float.

    Raises:
        DerivedColumnError: If evaluation fails.
    """
    stack: list[_Operand] = []

    for token in rpn_tokens:
        if token.token_type == FormulaTokenType.NUMBER:
            stack.append(float(token.value))
            continue

        if token.token_type == FormulaTokenType.COLUMN:
            stack.append(_numeric_series(df, token.value))
            continue

        if token.token_type == FormulaTokenType.OPERATOR:
            if len(stack) < 2:
                msg = "missing_operand_runtime"
                raise DerivedColumnError(
                    msg,
                    context={"operator": token.value},
                )

            right = stack.pop()
            left = stack.pop()

            stack.append(
                _apply_operator(
                    left=left,
                    right=right,
                    operator=token.value,
                    index=df.index,
                )
            )
            continue

        msg = "unsupported_token_runtime"
        raise DerivedColumnError(
            msg,
            context={"token": token.value},
        )

    if len(stack) != 1:
        msg = "invalid_evaluation_result"
        raise DerivedColumnError(msg)

    return stack[0]


# =====================================================================
# Internal validation helpers
# =====================================================================


def _normalized_column_name(spec: DerivedColumnSpec) -> str:
    """Return normalized output column name.

    Args:
        spec: Derived column specification.

    Returns:
        Trimmed output column name.
    """
    return (spec.column_name or "").strip()


def _validate_column_name(
    df: pd.DataFrame,
    spec: DerivedColumnSpec,
) -> None:
    """Validate output column name.

    Args:
        df: Source DataFrame.
        spec: Derived column specification.

    Raises:
        DerivedColumnError: If the output column name is invalid.
    """
    column_name = _normalized_column_name(spec)

    if not column_name:
        msg = "missing_output_column_name"
        raise DerivedColumnError(msg)

    if "[" in column_name or "]" in column_name:
        msg = "invalid_output_column_name_characters"
        raise DerivedColumnError(msg)

    if column_name in df.columns and not spec.overwrite_existing:
        msg = "output_column_exists"
        raise DerivedColumnError(
            msg,
            context={"column": column_name},
        )


def _numeric_series(df: pd.DataFrame, column: str) -> pd.Series:
    """Return a DataFrame column as numeric Series.

    Args:
        df: Source DataFrame.
        column: Column name.

    Returns:
        Numeric pandas Series.

    Raises:
        DerivedColumnError: If the column does not exist, is duplicated,
            or is not numeric.
    """
    series = _get_unique_series(df, column)

    if not is_numeric_series(series, include_bool=False):
        msg = "non_numeric_column"
        raise DerivedColumnError(
            msg,
            context={"column": column},
        )

    numeric = pd.to_numeric(series, errors="coerce")

    if not isinstance(numeric, pd.Series):
        numeric = pd.Series(numeric, index=series.index, name=series.name)

    return numeric


def _get_unique_series(df: pd.DataFrame, column: str) -> pd.Series:
    """Return a unique DataFrame column as Series.

    Args:
        df: Source DataFrame.
        column: Column name.

    Returns:
        Column as pandas Series.

    Raises:
        DerivedColumnError: If the column does not exist or is not unique.
    """
    if column not in df.columns:
        msg = "unknown_column_runtime"
        raise DerivedColumnError(
            msg,
            context={"column": column},
        )

    location = df.columns.get_loc(column)

    if not isinstance(location, int):
        msg = "column_not_unique"
        raise DerivedColumnError(
            msg,
            context={"column": column},
        )

    return df.iloc[:, location]


# =====================================================================
# Internal evaluation helpers
# =====================================================================


def _apply_operator(
    *,
    left: _Operand,
    right: _Operand,
    operator: str,
    index: pd.Index,
) -> _Operand:
    """Apply a binary arithmetic operator.

    Args:
        left: Left operand.
        right: Right operand.
        operator: Operator string.
        index: DataFrame index used when scalar operations need expansion.

    Returns:
        A Series or scalar result.

    Raises:
        DerivedColumnError: If the operator is unsupported.
    """
    try:
        if operator == "+":
            return left + right

        if operator == "-":
            return left - right

        if operator == "*":
            return left * right

        if operator == "/":
            return _safe_divide(left=left, right=right, index=index)

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
    ) as err:
        msg = "operator_application_failed"
        raise DerivedColumnError(
            msg,
            context={
                "operator": operator,
                "error": str(err),
            },
        ) from err

    msg = "unsupported_operator_runtime"
    raise DerivedColumnError(
        msg,
        context={"operator": operator},
    )


def _safe_divide(
    *,
    left: _Operand,
    right: _Operand,
    index: pd.Index,
) -> _Operand:
    """Safely divide two operands.

    Division by zero is allowed during evaluation and normalized later to
    missing values via inf/-inf replacement.

    Args:
        left: Left operand.
        right: Right operand.
        index: DataFrame index.

    Returns:
        Division result as Series or scalar.
    """
    # Scalar / scalar is the only case where Python would raise immediately.
    if not isinstance(left, pd.Series) and not isinstance(right, pd.Series):
        left_value = left
        right_value = right

        if right_value == 0:
            return pd.Series(pd.NA, index=index, dtype="Float64")

        return left_value / right_value

    with np.errstate(divide="ignore", invalid="ignore"):
        return left / right


def _normalize_result_series(
    *,
    result: _Operand,
    index: pd.Index,
    output_dtype: Literal["Float64"],
    replace_inf_with_na: bool,
) -> pd.Series:
    """Normalize formula result to a nullable numeric Series.

    Args:
        result: Scalar or Series result from formula evaluation.
        index: Expected DataFrame index.
        output_dtype: Output dtype strategy.
        replace_inf_with_na: Whether inf/-inf should be converted to pd.NA.

    Returns:
        Nullable numeric Series.

    Raises:
        DerivedColumnError: If the result cannot be normalized.
    """
    series = result.copy() if isinstance(result, pd.Series) else pd.Series(result, index=index)

    if not series.index.equals(index):
        series = series.reindex(index)

    numeric_raw = pd.to_numeric(series, errors="coerce")

    if not isinstance(numeric_raw, pd.Series):
        numeric_raw = pd.Series(numeric_raw, index=index, name=series.name)

    numeric = numeric_raw

    if replace_inf_with_na:
        numeric = _replace_infinite_with_na(numeric)

    try:
        if output_dtype == "Float64":
            return to_nullable_float_series(numeric, errors="coerce")

        msg = "unsupported_output_dtype"
        raise DerivedColumnError(
            msg,
            context={"dtype": output_dtype},
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
    ) as err:
        msg = "result_conversion_failed"
        raise DerivedColumnError(
            msg,
            context={"dtype": output_dtype},
        ) from err


def _replace_infinite_with_na(series: pd.Series) -> pd.Series:
    """Replace positive and negative infinity with pd.NA.

    Args:
        series: Numeric Series.

    Returns:
        Series where inf/-inf values are replaced with pd.NA.
    """
    values = series.to_numpy(dtype="float64", na_value=np.nan)
    mask = pd.Series(np.isinf(values), index=series.index)

    return series.mask(mask, pd.NA)


def _build_preview_columns(
    *,
    df: pd.DataFrame,
    spec: DerivedColumnSpec,
    result_column: str,
) -> list[str]:
    """Build a compact list of columns for preview output.

    Args:
        df: Preview source DataFrame.
        spec: Derived column specification.
        result_column: Name of the created result column.

    Returns:
        Ordered list of preview columns.
    """
    validation = validate_derived_column_spec(df, spec)
    referenced = list(validation.referenced_columns)

    preview_columns: list[str] = []

    for column in referenced:
        if column in df.columns and column not in preview_columns:
            preview_columns.append(column)

    if result_column not in preview_columns:
        preview_columns.append(result_column)

    return preview_columns


__all__ = [
    "DerivedColumnError",
    "DerivedColumnPreview",
    "DerivedColumnSpec",
    "create_derived_column",
    "evaluate_rpn",
    "get_numeric_columns",
    "preview_derived_column",
    "validate_derived_column_spec",
]
