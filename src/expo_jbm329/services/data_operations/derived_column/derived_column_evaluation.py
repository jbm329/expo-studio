"""Positional, vectorized evaluation of typed derived column expressions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

import numpy as np
import pandas as pd

from expo_jbm329.services.data_operations.derived_column.derived_column_expression import (
    TIME_FUNCTION_TYPES,
    ExpressionType,
    FormulaExpression,
)
from expo_jbm329.services.data_operations.derived_column.derived_column_expression import (
    ExpressionOperation as Op,
)
from expo_jbm329.services.data_operations.derived_column.derived_column_parser import DerivedColumnFormulaError
from expo_jbm329.services.data_operations.derived_column.derived_column_time import (
    DEFAULT_MONTH_LABELS,
    MonthLabels,
    extract_time_part,
)
from expo_jbm329.services.data_operations.expression_primitives import compare_values, membership_mask

if TYPE_CHECKING:
    from numpy.typing import NDArray


def _failure(node: FormulaExpression, code: str, **context: object) -> DerivedColumnFormulaError:
    return DerivedColumnFormulaError(
        code,
        context={"position": node.start, "end": node.end, "column": node.value, **context},
    )


def _literal(node: FormulaExpression) -> str | int | float | bool | None:
    match node.value_type:
        case ExpressionType.NULL:
            return None
        case ExpressionType.NUMBER:
            return float(node.value) if any(character in node.value.lower() for character in ".e") else int(node.value)
        case ExpressionType.BOOLEAN:
            return node.value == "TRUE"
        case _:
            return node.value


def _column(source: pd.DataFrame, node: FormulaExpression, rows: NDArray[np.intp]) -> pd.Series:
    if node.column_position is None:
        raise _failure(node, "invalid_evaluation_result")
    series = source.iloc[rows, node.column_position].reset_index(drop=True)
    if node.value_type == ExpressionType.TEXT:
        # Object storage is only a text candidate; never stringify mixed objects.
        if not all(isinstance(value, str) for value in series.dropna().array):
            raise _failure(node, "non_text_column")
        return series.astype(pd.StringDtype())
    if isinstance(series.dtype, pd.CategoricalDtype):
        category_dtype = series.cat.categories.dtype
        if node.value_type == ExpressionType.BOOLEAN:
            dtype = "boolean"
        elif pd.api.types.is_integer_dtype(category_dtype):
            dtype = "UInt64" if pd.api.types.is_unsigned_integer_dtype(category_dtype) else "Int64"
        else:
            dtype = "Float64"
        # Categorical.astype can round integer categories through float when
        # missing codes exist. Decode into a nullable array directly instead.
        categories = pd.Series(series.cat.categories, dtype=dtype).array
        return pd.Series(
            categories.take(series.cat.codes.to_numpy(), allow_fill=True), index=series.index, name=series.name
        )
    return series


def _compare(left: pd.Series, right: pd.Series, operator: str) -> pd.Series:
    if left.isna().all() or right.isna().all():
        return pd.Series(pd.NA, index=left.index, dtype="boolean")
    return compare_values(left, right, operator, preserve_unknown=True)


def _apply(node: FormulaExpression, values: list[pd.Series], month_labels: MonthLabels) -> pd.Series:
    left = values[0]
    operation = node.operation
    if operation in TIME_FUNCTION_TYPES:
        return extract_time_part(left, operation, month_labels)
    if operation in {Op.IS_NULL, Op.IS_NOT_NULL}:
        return left.isna() if operation == Op.IS_NULL else left.notna()
    if operation in {Op.POSITIVE, Op.NEGATIVE}:
        return left if operation == Op.POSITIVE else -left
    if operation == Op.NOT:
        return ~left.astype("boolean")
    if operation in {Op.IN, Op.NOT_IN}:
        candidates = pd.Series([_literal(operand) for operand in node.operands[1:]], dtype=object)
        return membership_mask(left, candidates, negate=operation == Op.NOT_IN, preserve_unknown=True)
    right = values[1]
    if operation in {Op.AND, Op.OR}:
        left, right = left.astype("boolean"), right.astype("boolean")
        return left & right if operation == Op.AND else left | right
    if operation in {Op.BETWEEN, Op.NOT_BETWEEN}:
        mask = _compare(left, right, ">=") & _compare(left, values[2], "<=")
        return ~mask if operation == Op.NOT_BETWEEN else mask
    if operation in {Op.EQUAL, Op.NOT_EQUAL, Op.GREATER, Op.GREATER_EQUAL, Op.LESS, Op.LESS_EQUAL}:
        return _compare(left, right, operation.value)
    if operation == Op.ADD:
        return left + right
    if operation == Op.SUBTRACT:
        return left - right
    if operation == Op.MULTIPLY:
        return left * right
    if operation == Op.DIVIDE:
        with np.errstate(divide="ignore", invalid="ignore"):
            return left / right
    raise _failure(node, "unsupported_operator_runtime", operator=operation.value)


def evaluate_expression(
    source: pd.DataFrame,
    expression: FormulaExpression,
    *,
    month_labels: MonthLabels = DEFAULT_MONTH_LABELS,
) -> pd.Series:
    """Evaluate a parsed expression without recursion or label-based alignment.

    Args:
        source: Unmodified source DataFrame matching the captured schema.
        expression: Validated expression from parse_expression_formula.
        month_labels: Captured month names; defaults to deterministic English.

    Returns:
        Result values in source order with the original, possibly duplicate index.
        IF evaluates each branch only on its selected positional rows. Boolean
        unknown selects else; intermediate comparisons retain three-valued logic.

    Raises:
        DerivedColumnFormulaError: For incompatible stored values or failed
            operations, with the failing expression's source span.
    """
    rows = np.arange(len(source), dtype=np.intp)
    pending: list[tuple[FormulaExpression, NDArray[np.intp], str]] = [(expression, rows, "visit")]
    results: list[pd.Series] = []
    selections: list[tuple[pd.Series, NDArray[np.intp], NDArray[np.intp]]] = []
    while pending:
        node, selected, stage = pending.pop()
        try:
            if stage == "condition":
                condition = results.pop().astype("boolean").fillna(False)
                yes = np.flatnonzero(condition.to_numpy(dtype=bool))
                no = np.flatnonzero(~condition.to_numpy(dtype=bool))
                selections.append((condition, yes, no))
                pending.extend((
                    (node, selected, "merge"),
                    (node.operands[2], selected[no], "visit"),
                    (node.operands[1], selected[yes], "visit"),
                ))
            elif stage == "merge":
                otherwise, then = results.pop(), results.pop()
                condition, yes, no = selections.pop()
                dtype: pd.StringDtype | Literal["Float64"] = (
                    pd.StringDtype() if node.value_type == ExpressionType.TEXT else "Float64"
                )
                result = pd.Series(pd.NA, index=condition.index, dtype=dtype)
                result.iloc[yes] = then.astype(dtype).array
                result.iloc[no] = otherwise.astype(dtype).array
                results.append(result)
            elif stage == "apply":
                count = 1 if node.operation in {Op.IN, Op.NOT_IN} else len(node.operands)
                values = results[-count:]
                del results[-count:]
                results.append(_apply(node, values, month_labels))
            elif node.operation == Op.LITERAL:
                literal_dtype: str | pd.StringDtype | None = None
                if node.value_type == ExpressionType.TEXT:
                    literal_dtype = pd.StringDtype()
                elif node.value_type == ExpressionType.BOOLEAN:
                    literal_dtype = "boolean"
                elif node.value_type == ExpressionType.NULL:
                    literal_dtype = "Float64"
                results.append(pd.Series(_literal(node), index=pd.RangeIndex(len(selected)), dtype=literal_dtype))
            elif node.operation == Op.COLUMN:
                results.append(_column(source, node, selected))
            elif node.operation == Op.IF:
                pending.extend(((node, selected, "condition"), (node.operands[0], selected, "visit")))
            else:
                pending.append((node, selected, "apply"))
                operands = node.operands[:1] if node.operation in {Op.IN, Op.NOT_IN} else node.operands
                pending.extend((operand, selected, "visit") for operand in reversed(operands))
        except DerivedColumnFormulaError:
            raise
        except (TypeError, ValueError, OverflowError, ArithmeticError) as error:
            raise _failure(node, "expression_evaluation_failed", error=str(error)) from error
    result = results.pop()
    result.index = source.index
    return result
