"""Typed exports of a successfully displayed correlation matrix."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from itertools import combinations
from typing import TYPE_CHECKING

import pandas as pd

from expo_jbm329.services.analysis.correlation import (
    MIN_SELECTED_COLUMNS,
    SIGNIFICANCE_LEVEL,
    CorrelationMatrixResult,
    correlation_strength,
)
from expo_jbm329.services.analysis.statistics import StatisticsExportFormat

if TYPE_CHECKING:
    from collections.abc import Sequence


class CorrelationExportComponent(StrEnum):
    """Selectable correlation export components."""

    STRONGEST_CORRELATIONS = "strongest_correlations"
    MATRIX_PLOT = "matrix_plot"
    SCATTERPLOTS = "scatterplots"


@dataclass(frozen=True, slots=True)
class CorrelationExportSnapshot:
    """Own the successful applied matrix and its selected numeric source columns."""

    matrix: CorrelationMatrixResult
    matrix_data: pd.DataFrame

    def __post_init__(self) -> None:
        """Reject failed, incomplete or mismatched matrix snapshots."""
        matrix = self.matrix
        data = self.matrix_data
        if not isinstance(matrix, CorrelationMatrixResult):  # pyright: ignore[reportUnnecessaryIsInstance]
            message = "A typed correlation matrix is required."
            raise TypeError(message)
        if matrix.error is not None:
            message = "A failed correlation matrix cannot be exported."
            raise ValueError(message)
        if not isinstance(data, pd.DataFrame):  # pyright: ignore[reportUnnecessaryIsInstance]
            message = "Owned correlation data must be a DataFrame."
            raise TypeError(message)
        if (
            len(matrix.columns) < MIN_SELECTED_COLUMNS
            or len(set(matrix.columns)) != len(matrix.columns)
            or not set(matrix.columns).issubset(matrix.available_columns)
            or tuple(data.columns) != matrix.columns
            or not all(pd.api.types.is_numeric_dtype(data[column].dtype) for column in matrix.columns)
        ):
            message = "Correlation snapshot columns do not match the applied matrix."
            raise ValueError(message)
        size = len(matrix.columns)
        if len(matrix.coefficients) != size or any(len(row) != size for row in matrix.coefficients):
            message = "Correlation snapshot data or matrix dimensions are malformed."
            raise ValueError(message)
        expected_pairs = {frozenset(pair) for pair in combinations(matrix.columns, 2)}
        actual_pairs = [frozenset((pair.x_column, pair.y_column)) for pair in matrix.pairs]
        if len(actual_pairs) != len(expected_pairs) or set(actual_pairs) != expected_pairs:
            message = "Correlation matrix must contain every unique applied column pair."
            raise ValueError(message)
        index = {column: position for position, column in enumerate(matrix.columns)}
        if any(index[pair.x_column] >= index[pair.y_column] for pair in matrix.pairs):
            message = "Correlation pairs must retain the applied matrix column orientation."
            raise ValueError(message)
        matrix_order = tuple(combinations(matrix.columns, 2))
        pair_coefficients = {(pair.x_column, pair.y_column): pair.coefficient for pair in matrix.pairs}
        ranked_order = tuple(
            sorted(
                matrix_order,
                key=lambda pair_columns: _ranking_key(pair_coefficients[pair_columns]),
            )
        )
        if tuple((pair.x_column, pair.y_column) for pair in matrix.pairs) != ranked_order:
            message = "Correlation pairs do not match the applied matrix ranking."
            raise ValueError(message)
        for pair in matrix.pairs:
            coefficient = matrix.coefficients[index[pair.x_column]][index[pair.y_column]]
            reverse_coefficient = matrix.coefficients[index[pair.y_column]][index[pair.x_column]]
            if (
                not (math.isnan(coefficient) and math.isnan(pair.coefficient)) and coefficient != pair.coefficient
            ) or not (
                (math.isnan(coefficient) and math.isnan(reverse_coefficient)) or coefficient == reverse_coefficient
            ):
                message = "Correlation pair statistics do not match the applied matrix."
                raise ValueError(message)


@dataclass(frozen=True, slots=True)
class CorrelationExportRequest:
    """Selected applied components; charts require Excel output."""

    snapshot: CorrelationExportSnapshot
    components: tuple[CorrelationExportComponent, ...]
    format: StatisticsExportFormat

    def __post_init__(self) -> None:
        """Validate distinct components and format-specific chart constraints."""
        if not self.components or len(set(self.components)) != len(self.components):
            message = "Select a distinct available correlation component."
            raise ValueError(message)
        if any(
            not isinstance(item, CorrelationExportComponent)  # pyright: ignore[reportUnnecessaryIsInstance]
            for item in self.components
        ):
            message = "Unknown correlation export component."
            raise ValueError(message)
        if not isinstance(self.format, StatisticsExportFormat):  # pyright: ignore[reportUnnecessaryIsInstance]
            message = "Unknown correlation export format."
            raise TypeError(message)
        if self.format is not StatisticsExportFormat.EXCEL and self.components != (
            CorrelationExportComponent.STRONGEST_CORRELATIONS,
        ):
            message = "CSV and binary exports require the ranked table only; charts require Excel."
            raise ValueError(message)


def correlation_export_table(
    snapshot: CorrelationExportSnapshot,
    components: Sequence[CorrelationExportComponent],
) -> pd.DataFrame:
    """Build every displayed pair in its ranked order without formatting numbers.

    Args:
        snapshot: Successful applied matrix and its owned numeric columns.
        components: The selected export table.

    Returns:
        A DataFrame containing the matrix ranking, numeric statistics, labels
        and display context.

    Raises:
        ValueError: If any component other than the available ranked table is requested.
    """
    if tuple(components) != (CorrelationExportComponent.STRONGEST_CORRELATIONS,):
        message = "Select only the strongest-correlations table."
        raise ValueError(message)
    matrix = snapshot.matrix
    rows: list[dict[str, object]] = []
    for pair in matrix.pairs:
        strength = correlation_strength(pair.coefficient)
        rows.append({
            "variable_1": pair.x_column,
            "variable_2": pair.y_column,
            "coefficient": pair.coefficient,
            "ci_low": pair.ci_low,
            "ci_high": pair.ci_high,
            "p_value": pair.p_value,
            "adjusted_p_value": pair.adjusted_p_value,
            "n": pair.n,
            "strength": strength.value if strength is not None else pd.NA,
            "significant": (
                pair.adjusted_p_value < SIGNIFICANCE_LEVEL if math.isfinite(pair.adjusted_p_value) else pd.NA
            ),
            "method": matrix.method.value,
        })
    frame = pd.DataFrame(rows)
    frame["strength"] = frame["strength"].astype(pd.StringDtype())
    frame["significant"] = frame["significant"].astype(pd.BooleanDtype())
    frame["n"] = frame["n"].astype(pd.Int64Dtype())
    return frame


def _ranking_key(coefficient: float) -> tuple[bool, float]:
    """Match the matrix's descending absolute-coefficient ranking."""
    undefined = math.isnan(coefficient)
    return undefined, 0.0 if undefined else -abs(coefficient)
