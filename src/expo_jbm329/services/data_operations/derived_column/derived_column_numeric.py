"""Qt-free numeric inference and checked integer arithmetic for derived columns."""

from __future__ import annotations

import math
from enum import StrEnum
from typing import TYPE_CHECKING, Literal

import numpy as np
import pandas as pd

from expo_jbm329.services.data_operations.derived_column.derived_column_parser import DerivedColumnFormulaError

if TYPE_CHECKING:
    from numpy.typing import NDArray

IntegerOperation = Literal["+", "-", "*", "positive", "negative"]
_INT64_MIN = -(2**63)
_INT64_MAX = 2**63 - 1
_UINT64_MAX = 2**64 - 1


class NumericKind(StrEnum):
    """Supported numeric storage, separate from expression compatibility."""

    SIGNED = "Int64"
    UNSIGNED = "UInt64"
    FLOAT = "Float64"


def numeric_kind_from_dtype(dtype: object) -> NumericKind | None:
    """Classify numeric schema without reading source values.

    Narrow unsigned integers widen to signed 64-bit storage for arithmetic.
    Categories inherit their category-value dtype; booleans are not numbers.
    """
    if isinstance(dtype, pd.CategoricalDtype):
        dtype = getattr(dtype.categories, "dtype", None)
    dtype_name = str(dtype)
    if pd.api.types.is_integer_dtype(dtype_name):
        numpy_dtype = np.dtype(dtype_name.lower().replace("[pyarrow]", ""))
        return NumericKind.UNSIGNED if numpy_dtype == np.dtype("uint64") else NumericKind.SIGNED
    if pd.api.types.is_float_dtype(dtype_name):
        return NumericKind.FLOAT
    return None


def parse_numeric_literal(text: str) -> int | float:
    """Parse validated numeric spelling without rounding integer literals.

    Bounds for integer literals are checked when the selected expression is
    evaluated, not while validating an inactive IF branch.

    Raises:
        DerivedColumnFormulaError: If the spelling is invalid or nonfinite.
    """
    code = "invalid_number_literal"
    try:
        value = float(text) if any(character in text.lower() for character in ".e") else int(text)
    except ValueError as error:
        raise DerivedColumnFormulaError(code, context={"token": text}) from error
    if isinstance(value, float) and not math.isfinite(value):
        raise DerivedColumnFormulaError(code, context={"token": text})
    return value


def numeric_literal_kind(value: float) -> NumericKind:
    """Infer a literal's storage kind without converting integers to floats."""
    if isinstance(value, float):
        return NumericKind.FLOAT
    return NumericKind.UNSIGNED if value > _INT64_MAX else NumericKind.SIGNED


def common_numeric_kind(
    left: NumericKind | None,
    right: NumericKind | None,
    *,
    left_literal: int | None = None,
    right_literal: int | None = None,
) -> NumericKind | None:
    """Infer arithmetic/IF storage from both operands, with NULL as neutral.

    Nonnegative integer literals can join UInt64 operands without introducing
    signed storage. Other mixed signed/unsigned operands require checked Int64.
    """
    if left is None:
        return right
    if right is None:
        return left
    if NumericKind.FLOAT in {left, right}:
        return NumericKind.FLOAT
    if left == right:
        return left
    if left == NumericKind.UNSIGNED and right_literal is not None and right_literal >= 0:
        return NumericKind.UNSIGNED
    if right == NumericKind.UNSIGNED and left_literal is not None and left_literal >= 0:
        return NumericKind.UNSIGNED
    return NumericKind.SIGNED


def _integer_bounds(kind: NumericKind) -> tuple[int, int]:
    if kind == NumericKind.FLOAT:
        message = "Checked integer arithmetic requires an integer numeric kind."
        raise ValueError(message)
    return (0, _UINT64_MAX) if kind == NumericKind.UNSIGNED else (_INT64_MIN, _INT64_MAX)


def prepare_integer_operand(values: pd.Series, kind: NumericKind) -> pd.Series:
    """Widen integer values exactly, validating mixed signed/unsigned ranges.

    Args:
        values: Evaluated positional integer operand, or an all-missing operand.
        kind: Inferred target integer kind.

    Returns:
        A nullable integer Series on the unchanged index. Correctly typed
        nullable operands are reused; callers must not mutate them.

    Raises:
        DerivedColumnFormulaError: If values are noninteger or outside the range.
        ValueError: If the requested kind is floating.
    """
    _, upper = _integer_bounds(kind)
    if pd.api.types.is_bool_dtype(values.dtype) or not pd.api.types.is_integer_dtype(values.dtype):
        if not values.isna().all():
            code = "integer_operand_required"
            raise DerivedColumnFormulaError(code)
        return pd.Series(pd.NA, index=values.index, dtype=kind.value, name=values.name)
    if values.dtype == kind.value:
        return values
    source_unsigned = pd.api.types.is_unsigned_integer_dtype(values.dtype)
    if source_unsigned and kind == NumericKind.SIGNED:
        out_of_range = bool((values > upper).any())
    elif not source_unsigned and kind == NumericKind.UNSIGNED:
        out_of_range = bool((values < 0).any())
    else:
        out_of_range = False
    if out_of_range:
        code = "integer_out_of_range"
        raise DerivedColumnFormulaError(code, context={"dtype": kind.value})
    return values.astype(kind.value)


def _unsigned_magnitude(values: NDArray[np.int64]) -> NDArray[np.uint64]:
    unsigned = values.view(np.uint64)
    # Unsigned negation handles abs(INT64_MIN) exactly without signed overflow.
    return np.where(values < 0, -unsigned, unsigned)


def _signed_multiplication_overflow(left: NDArray[np.int64], right: NDArray[np.int64]) -> NDArray[np.bool_]:
    left_magnitude = _unsigned_magnitude(left)
    right_magnitude = _unsigned_magnitude(right)
    negative = (left < 0) ^ (right < 0)
    limit = np.where(negative, np.uint64(2**63), np.uint64(_INT64_MAX))
    divisor = np.maximum(right_magnitude, np.uint64(1))
    overflow: NDArray[np.bool_] = (right_magnitude != 0) & (left_magnitude > limit // divisor)
    return overflow


def checked_integer_arithmetic(
    operation: IntegerOperation,
    left: pd.Series | int,
    right: pd.Series | int | None = None,
    *,
    kind: NumericKind,
) -> pd.Series | int:
    """Evaluate integer arithmetic with exact vectorized overflow checks.

    Args:
        operation: Supported arithmetic or unary operation.
        left: Integer Series or exact scalar.
        right: Second operand for binary operations; absent for unary operations.
        kind: Schema-inferred integer result kind.

    Returns:
        A nullable Series on the operand index, or an exact integer scalar.
        Missing operands propagate without triggering overflow checks.

    Raises:
        DerivedColumnFormulaError: For out-of-range operands or integer overflow.
        ValueError: For invalid arity, index mismatch or floating result kinds.
    """
    lower, upper = _integer_bounds(kind)
    range_code = "integer_out_of_range"
    overflow_code = "integer_overflow"
    if operation not in {"+", "-", "*", "positive", "negative"}:
        message = "Unsupported checked integer operation."
        raise ValueError(message)
    unary = operation in {"positive", "negative"}
    if unary != (right is None):
        message = "Integer operation has an invalid number of operands."
        raise ValueError(message)
    if isinstance(left, bool) or isinstance(right, bool):
        code = "integer_operand_required"
        raise DerivedColumnFormulaError(code)
    if not isinstance(left, pd.Series) and not isinstance(right, pd.Series):
        # A scalar negative literal can spell INT64_MIN using its positive magnitude.
        if not lower <= left <= upper and not (
            operation == "negative" and kind == NumericKind.SIGNED and left == 2**63
        ):
            raise DerivedColumnFormulaError(range_code, context={"dtype": kind.value})
        if right is not None and not lower <= right <= upper:
            raise DerivedColumnFormulaError(range_code, context={"dtype": kind.value})
        match operation:
            case "positive":
                result = left
            case "negative":
                result = -left
            case "+" | "-" | "*":
                if right is None:
                    message = "Binary integer operation requires a right operand."
                    raise ValueError(message)
                result = left + right if operation == "+" else left - right if operation == "-" else left * right
        if not lower <= result <= upper:
            raise DerivedColumnFormulaError(overflow_code, context={"operator": operation, "dtype": kind.value})
        return result
    index = left.index if isinstance(left, pd.Series) else right.index if isinstance(right, pd.Series) else None
    if index is None:
        message = "Vector integer arithmetic requires a Series index."
        raise ValueError(message)
    operands: list[pd.Series] = []
    for operand in (left,) if unary else (left, right):
        if isinstance(operand, pd.Series):
            if not operand.index.equals(index):
                message = "Integer operands must have identical positional indexes."
                raise ValueError(message)
            operands.append(prepare_integer_operand(operand, kind))
        else:
            if operand is None:
                raise DerivedColumnFormulaError(range_code, context={"dtype": kind.value})
            if len(index) == 0:
                operands.append(pd.Series(index=index, dtype=kind.value))
                continue
            if not lower <= operand <= upper:
                raise DerivedColumnFormulaError(range_code, context={"dtype": kind.value})
            operands.append(pd.Series(operand, index=index, dtype=kind.value))
    missing = operands[0].isna().to_numpy(dtype=bool)
    numpy_dtype = np.uint64 if kind == NumericKind.UNSIGNED else np.int64
    a = operands[0].to_numpy(dtype=numpy_dtype, na_value=0)
    if unary:
        result_array = a if operation == "positive" else -a
        overflow = (a != 0) if kind == NumericKind.UNSIGNED else (a == _INT64_MIN)
        if operation == "positive":
            overflow = np.zeros(len(a), dtype=bool)
    else:
        missing |= operands[1].isna().to_numpy(dtype=bool)
        b = operands[1].to_numpy(dtype=numpy_dtype, na_value=0)
        # Wrapped array results are exposed only after the exact overflow check.
        if operation == "+":
            result_array = a + b
            overflow = (
                (result_array < a) if kind == NumericKind.UNSIGNED else (((a ^ result_array) & (b ^ result_array)) < 0)
            )
        elif operation == "-":
            result_array = a - b
            overflow = (a < b) if kind == NumericKind.UNSIGNED else (((a ^ b) & (a ^ result_array)) < 0)
        else:
            if kind == NumericKind.UNSIGNED:
                overflow = (b != 0) & (a > np.uint64(_UINT64_MAX) // np.maximum(b, np.uint64(1)))
            else:
                overflow = _signed_multiplication_overflow(a, b)
            result_array = a * b
    if (overflow & ~missing).any():
        raise DerivedColumnFormulaError(overflow_code, context={"operator": operation, "dtype": kind.value})
    return pd.Series(pd.arrays.IntegerArray(result_array, missing), index=index)
