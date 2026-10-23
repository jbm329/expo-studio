"""Full-data Reshape calculations with a bounded, output-independent preview."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from expo_jbm329.services.data_operations.reshape_conditions import (
    ConditionColumn,
    ConditionError,
    ConditionLiteralType,
    ConditionMatch,
    ConditionOperator,
    ConditionRule,
    condition_columns,
    condition_value,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence


class ReshapeFunction(StrEnum):
    """Supported aggregation functions."""

    SUM = "SUM"
    AVG = "AVG"
    COUNT = "COUNT"
    COUNT_DISTINCT = "COUNT DISTINCT"
    MIN = "MIN"
    MAX = "MAX"


class ReshapeProblem(StrEnum):
    """Stable failures translated at the presentation boundary."""

    CONFIGURATION = "configuration"
    OUTPUT_NAMES = "output_names"
    VALUE = "value"
    DATA = "data"


class ReshapeError(ValueError):
    """Explicit configuration, literal conversion or data-operation failure."""

    def __init__(self, problem: ReshapeProblem, name: str = "") -> None:
        """Capture a translatable problem and its column/metric name."""
        self.problem = problem
        self.name = name
        super().__init__(f"{problem.value}: {name}")


@dataclass(frozen=True, slots=True)
class ReshapeMetric:
    """One immutable metric and its parsed, postfix row condition."""

    name: str
    function: ReshapeFunction
    source_position: int
    condition: tuple[ConditionRule | ConditionMatch, ...] = ()


@dataclass(frozen=True, slots=True)
class ReshapeRequest:
    """Applied configuration independent of mutable widgets."""

    dimensions: tuple[int, ...]
    metrics: tuple[ReshapeMetric, ...]


@dataclass(frozen=True, slots=True)
class ReshapePreview:
    """At most five calculated output rows and the full output row count."""

    request: ReshapeRequest
    frame: pd.DataFrame
    total_rows: int


def validate_reshape(request: ReshapeRequest, columns: Sequence[ConditionColumn], dtypes: Sequence[str]) -> None:
    """Reject incomplete, ambiguous or unsupported output configurations."""
    if not request.metrics or len(columns) != len(dtypes):
        raise ReshapeError(ReshapeProblem.CONFIGURATION)
    if len(set(request.dimensions)) != len(request.dimensions):
        raise ReshapeError(ReshapeProblem.CONFIGURATION)
    for position in request.dimensions:
        if not 0 <= position < len(columns):
            raise ReshapeError(ReshapeProblem.CONFIGURATION)
    names = [columns[position].name for position in request.dimensions]
    for metric in request.metrics:
        position = metric.source_position
        if not metric.name.strip() or not 0 <= position < len(columns):
            raise ReshapeError(ReshapeProblem.CONFIGURATION, metric.name)
        names.append(metric.name)
        numeric = columns[position].literal_type == ConditionLiteralType.NUMBER
        datetime = pd.api.types.is_datetime64_any_dtype(dtypes[position])
        if metric.function in {ReshapeFunction.SUM, ReshapeFunction.AVG} and not numeric:
            raise ReshapeError(ReshapeProblem.CONFIGURATION, metric.name)
        if metric.function in {ReshapeFunction.MIN, ReshapeFunction.MAX} and not (numeric or datetime):
            raise ReshapeError(ReshapeProblem.CONFIGURATION, metric.name)
        depth = 0
        for instruction in metric.condition:
            if isinstance(instruction, ConditionRule):
                column = instruction.column
                if (
                    not 0 <= column.position < len(columns)
                    or column != columns[column.position]
                    or not column.available
                ):
                    raise ReshapeError(ReshapeProblem.CONFIGURATION, metric.name)
                depth += 1
            else:
                if depth <= 1:
                    raise ReshapeError(ReshapeProblem.CONFIGURATION, metric.name)
                depth -= 1
        if metric.condition and depth != 1:
            raise ReshapeError(ReshapeProblem.CONFIGURATION, metric.name)
    if len(names) != len(set(names)):
        raise ReshapeError(ReshapeProblem.OUTPUT_NAMES)


def _operand_values(rule: ConditionRule, series: pd.Series) -> pd.Series:
    values: list[object] = []
    canonical: dict[str, object] = {}
    if isinstance(series.dtype, pd.CategoricalDtype) or pd.api.types.is_object_dtype(series.dtype):
        identities: dict[str, str] = {}
        try:
            # unique() would collapse equal Python scalars such as True and 1.
            for scalar in series.array:
                identity = condition_value(scalar)
                if identity is None:
                    continue
                if identity.text in identities and identities[identity.text] != identity.kind:
                    raise ReshapeError(ReshapeProblem.DATA, rule.column.name)
                identities[identity.text] = identity.kind
                canonical[identity.text] = scalar
            if len(set(identities.values())) > 1:
                raise ReshapeError(ReshapeProblem.DATA, rule.column.name)
        except (TypeError, ConditionError) as error:
            raise ReshapeError(ReshapeProblem.DATA, rule.column.name) from error
    for operand in rule.operands:
        if rule.column.literal_type == ConditionLiteralType.NUMBER:
            value = (
                float(operand.text)
                if any(character in operand.text.lower() for character in ".e")
                else int(operand.text)
            )
            if isinstance(value, float) and not math.isfinite(value):
                raise ReshapeError(ReshapeProblem.VALUE, rule.column.name)
            values.append(value)
        elif rule.column.literal_type == ConditionLiteralType.BOOLEAN:
            values.append(operand.text.upper() == "TRUE")
        elif pd.api.types.is_datetime64_any_dtype(series.dtype):
            timestamp = pd.Timestamp(operand.text)
            if pd.isna(timestamp):
                raise ReshapeError(ReshapeProblem.VALUE, rule.column.name)
            timezone = series.dt.tz
            if timezone is None and timestamp.tzinfo is not None:
                raise ReshapeError(ReshapeProblem.VALUE, rule.column.name)
            if timezone is not None:
                localized = (
                    timestamp.tz_localize(timezone, ambiguous="NaT", nonexistent="NaT")
                    if timestamp.tzinfo is None
                    else timestamp.tz_convert(timezone)
                )
                if not isinstance(localized, pd.Timestamp):
                    raise ReshapeError(ReshapeProblem.VALUE, rule.column.name)
                timestamp = localized
            values.append(timestamp)
        else:
            values.append(canonical.get(operand.text, operand.text))
    return pd.Series(values, dtype=object)


def _predicate(source: pd.DataFrame, rule: ConditionRule) -> pd.Series:
    series = source.iloc[:, rule.column.position].reset_index(drop=True)
    operator = rule.operator
    if operator == ConditionOperator.IS_NULL:
        return series.isna()
    if operator == ConditionOperator.IS_NOT_NULL:
        return series.notna()
    try:
        values = _operand_values(rule, series)
    except ReshapeError:
        raise
    except (ValueError, TypeError, OverflowError) as error:
        raise ReshapeError(ReshapeProblem.VALUE, rule.column.name) from error
    try:
        if operator.is_membership:
            mask = series.isin(values)
            if operator == ConditionOperator.NOT_IN:
                mask = ~mask
        else:
            value = values.iloc[0]
            match operator:
                case ConditionOperator.EQUAL:
                    mask = series.eq(value)
                case ConditionOperator.NOT_EQUAL:
                    mask = series.ne(value)
                case ConditionOperator.GREATER:
                    mask = series.gt(value)
                case ConditionOperator.GREATER_EQUAL:
                    mask = series.ge(value)
                case ConditionOperator.LESS:
                    mask = series.lt(value)
                case ConditionOperator.LESS_EQUAL:
                    mask = series.le(value)
                case _:
                    raise ReshapeError(ReshapeProblem.CONFIGURATION, rule.column.name)
        return (mask.fillna(False) & series.notna()).astype(bool)
    except (TypeError, ValueError, OverflowError) as error:
        raise ReshapeError(ReshapeProblem.DATA, rule.column.name) from error


def evaluate_condition(
    source: pd.DataFrame,
    instructions: tuple[ConditionRule | ConditionMatch, ...],
    cancel_cb: Callable[[], bool] | None = None,
) -> pd.Series | None:
    """Evaluate parsed instructions with positional, nonmissing row masks."""
    stack: list[pd.Series] = []
    for instruction in instructions:
        if cancel_cb is not None and cancel_cb():
            return None
        if isinstance(instruction, ConditionRule):
            stack.append(_predicate(source, instruction))
        else:
            right = stack.pop()
            left = stack.pop()
            stack.append(left & right if instruction == ConditionMatch.ALL else left | right)
    return stack[0] if stack else pd.Series(True, index=pd.RangeIndex(len(source)), dtype=bool)


def compute_reshape_preview(
    source: pd.DataFrame,
    request: ReshapeRequest,
    *,
    progress_cb: Callable[[int], None] | None = None,
    cancel_cb: Callable[[], bool] | None = None,
) -> ReshapePreview | None:
    """Aggregate the entire source, returning five output rows or cancellation.

    Args:
        source: Captured source frame; never mutated.
        request: Frozen dimensions, metrics and parsed conditions.
        progress_cb: Optional phase/metric progress callback.
        cancel_cb: Cooperative cancellation callback.

    Returns:
        Bounded preview with full group count, or None if cancelled.

    Raises:
        ReshapeError: If configuration, literals or source data cannot be processed.
    """
    columns = condition_columns(list(source.columns), list(source.dtypes))
    validate_reshape(request, columns, [str(dtype) for dtype in source.dtypes])
    if cancel_cb is not None and cancel_cb():
        return None
    if progress_cb is not None:
        progress_cb(0)
    if request.dimensions:
        dimensions = source.iloc[:, list(request.dimensions)]
        try:
            if source.empty:
                codes = np.zeros(0, dtype=np.int64)
                total_rows = 0
            else:
                codes, groups = pd.factorize(pd.MultiIndex.from_frame(dimensions), sort=False, use_na_sentinel=False)
                total_rows = len(groups)
        except (TypeError, ValueError) as error:
            raise ReshapeError(ReshapeProblem.DATA, ", ".join(str(name) for name in dimensions.columns)) from error
        _, first = np.unique(codes, return_index=True)
        frame = dimensions.iloc[first[:5]].reset_index(drop=True).copy()
        frame.columns = [columns[position].name for position in request.dimensions]
    else:
        codes = np.zeros(len(source), dtype=np.int64)
        total_rows = 1
        frame = pd.DataFrame(index=pd.RangeIndex(1))
    group_ids = pd.Series(codes, index=pd.RangeIndex(len(source)))
    preview_ids = pd.RangeIndex(min(5, total_rows))
    if progress_cb is not None:
        progress_cb(10)
    for index, metric in enumerate(request.metrics):
        mask = evaluate_condition(source, metric.condition, cancel_cb)
        if mask is None or (cancel_cb is not None and cancel_cb()):
            return None
        series = source.iloc[:, metric.source_position].reset_index(drop=True)
        try:
            grouped = series[mask].groupby(group_ids[mask], sort=False)
            match metric.function:
                case ReshapeFunction.COUNT:
                    aggregate = grouped.count().astype("Int64")
                case ReshapeFunction.COUNT_DISTINCT:
                    aggregate = grouped.nunique(dropna=True).astype("Int64")
                case ReshapeFunction.SUM:
                    aggregate = grouped.sum(min_count=1)
                case ReshapeFunction.AVG:
                    aggregate = grouped.mean()
                case ReshapeFunction.MIN:
                    aggregate = grouped.min()
                case ReshapeFunction.MAX:
                    aggregate = grouped.max()
            if pd.api.types.is_integer_dtype(aggregate.dtype):
                aggregate = aggregate.astype(
                    "UInt64" if pd.api.types.is_unsigned_integer_dtype(aggregate.dtype) else "Int64"
                )
            result = aggregate.reindex(preview_ids)
            if metric.function in {ReshapeFunction.COUNT, ReshapeFunction.COUNT_DISTINCT}:
                result = result.fillna(0)
            frame[metric.name] = result
        except (TypeError, ValueError, OverflowError) as error:
            raise ReshapeError(ReshapeProblem.DATA, metric.name) from error
        if progress_cb is not None:
            progress_cb(10 + (index + 1) * 90 // len(request.metrics))
    if cancel_cb is not None and cancel_cb():
        return None
    return ReshapePreview(request, frame, total_rows)
