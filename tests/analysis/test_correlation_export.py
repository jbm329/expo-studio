from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from expo_jbm329.services.analysis.correlation import (
    CorrelationError,
    CorrelationMethod,
    CorrelationStrength,
    analyze_correlation_matrix,
)
from expo_jbm329.services.analysis.correlation_export import (
    CorrelationExportComponent as Component,
)
from expo_jbm329.services.analysis.correlation_export import (
    CorrelationExportRequest,
    CorrelationExportSnapshot,
    correlation_export_table,
)
from expo_jbm329.services.analysis.statistics import StatisticsExportFormat as Format


def _snapshot() -> CorrelationExportSnapshot:
    """Create a complete ranked matrix with defined and undefined pairs."""
    base = np.arange(12, dtype=float)
    frame = pd.DataFrame({
        "Original X": base,
        "Y / unchanged": 3 * base + np.array([0, 1, -1] * 4, dtype=float),
        "No variation": np.ones(12, dtype=float),
        "Too sparse": [1.0, 2.0, *([np.nan] * 10)],
    })
    matrix = analyze_correlation_matrix(frame, tuple(frame.columns), CorrelationMethod.PEARSON)
    assert matrix is not None
    return CorrelationExportSnapshot(matrix, frame.copy(deep=True))


def test_snapshot_accepts_successful_matrix_and_validates_column_and_pair_payloads() -> None:
    snapshot = _snapshot()
    assert snapshot.matrix_data.columns.tolist() == list(snapshot.matrix.columns)
    assert snapshot.matrix_data is not None

    with pytest.raises(TypeError, match="typed correlation"):
        CorrelationExportSnapshot(None, snapshot.matrix_data)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="failed"):
        CorrelationExportSnapshot(replace(snapshot.matrix, error=CorrelationError.INVALID_COLUMN), snapshot.matrix_data)
    with pytest.raises(ValueError, match="columns"):
        CorrelationExportSnapshot(snapshot.matrix, snapshot.matrix_data[["Y / unchanged"]])
    with pytest.raises(TypeError, match="DataFrame"):
        CorrelationExportSnapshot(snapshot.matrix, None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="columns"):
        CorrelationExportSnapshot(snapshot.matrix, snapshot.matrix_data.astype(str))
    with pytest.raises(ValueError, match="dimensions"):
        CorrelationExportSnapshot(replace(snapshot.matrix, coefficients=()), snapshot.matrix_data)
    with pytest.raises(ValueError, match="every unique"):
        CorrelationExportSnapshot(replace(snapshot.matrix, pairs=snapshot.matrix.pairs[:-1]), snapshot.matrix_data)
    first = snapshot.matrix.pairs[0]
    mismatched = replace(first, coefficient=first.coefficient / 2)
    with pytest.raises(ValueError, match="statistics"):
        CorrelationExportSnapshot(
            replace(snapshot.matrix, pairs=(mismatched, *snapshot.matrix.pairs[1:])),
            snapshot.matrix_data,
        )
    coefficients = [list(row) for row in snapshot.matrix.coefficients]
    coefficients[1][0] = 0.0
    with pytest.raises(ValueError, match="statistics"):
        CorrelationExportSnapshot(
            replace(snapshot.matrix, coefficients=tuple(tuple(row) for row in coefficients)),
            snapshot.matrix_data,
        )
    first, second, *remaining = snapshot.matrix.pairs
    with pytest.raises(ValueError, match="orientation"):
        CorrelationExportSnapshot(
            replace(
                snapshot.matrix,
                pairs=(
                    replace(first, x_column=first.y_column, y_column=first.x_column),
                    second,
                    *remaining,
                ),
            ),
            snapshot.matrix_data,
        )
    with pytest.raises(ValueError, match="ranking"):
        CorrelationExportSnapshot(
            replace(snapshot.matrix, pairs=tuple(reversed(snapshot.matrix.pairs))),
            snapshot.matrix_data,
        )


def test_table_preserves_ranked_pairs_numeric_statistics_and_undefined_values() -> None:
    snapshot = _snapshot()
    frame = correlation_export_table(snapshot, (Component.STRONGEST_CORRELATIONS,))

    assert frame[["variable_1", "variable_2"]].to_numpy().tolist() == [
        [pair.x_column, pair.y_column] for pair in snapshot.matrix.pairs
    ]
    assert frame.columns.tolist() == [
        "variable_1",
        "variable_2",
        "coefficient",
        "ci_low",
        "ci_high",
        "p_value",
        "adjusted_p_value",
        "n",
        "strength",
        "significant",
        "method",
    ]
    assert frame["method"].eq("pearson").all()
    assert frame["n"].tolist() == [pair.n for pair in snapshot.matrix.pairs]
    for row, pair in zip(frame.itertuples(index=False), snapshot.matrix.pairs, strict=True):
        for field in ("coefficient", "ci_low", "ci_high", "p_value", "adjusted_p_value"):
            actual = getattr(row, field)
            expected = getattr(pair, field)
            assert (pd.isna(actual) and np.isnan(expected)) or actual == expected
        expected_strength = (
            CorrelationStrength.NEGLIGIBLE.value if np.isnan(pair.coefficient) else abs(pair.coefficient)
        )
        if isinstance(expected_strength, float):
            assert row.strength == (
                CorrelationStrength.STRONG.value
                if expected_strength >= 0.5
                else CorrelationStrength.MODERATE.value
                if expected_strength >= 0.3
                else CorrelationStrength.WEAK.value
                if expected_strength >= 0.1
                else CorrelationStrength.NEGLIGIBLE.value
            )
        else:
            assert pd.isna(row.strength)
        if np.isfinite(pair.adjusted_p_value):
            assert bool(row.significant) is (pair.adjusted_p_value < 0.05)
        else:
            assert pd.isna(row.significant)
    assert frame["strength"].dtype == pd.StringDtype()
    assert frame["significant"].dtype == pd.BooleanDtype()
    assert frame["n"].dtype == pd.Int64Dtype()
    assert frame["coefficient"].isna().any()
    assert frame["ci_low"].isna().any()
    assert frame["adjusted_p_value"].isna().any()


@pytest.mark.parametrize("format_choice", list(Format))
def test_table_request_accepts_single_ranked_table_in_each_format(format_choice: Format) -> None:
    snapshot = _snapshot()
    request = CorrelationExportRequest(snapshot, (Component.STRONGEST_CORRELATIONS,), format_choice)
    assert request.snapshot is snapshot
    assert request.format is format_choice


@pytest.mark.parametrize(
    ("components", "format_choice"),
    [
        ((), Format.EXCEL),
        ((Component.STRONGEST_CORRELATIONS, Component.STRONGEST_CORRELATIONS), Format.EXCEL),
        ((Component.MATRIX_PLOT,), Format.EXCEL),
        ((Component.SCATTERPLOTS,), Format.EXCEL),
        (("unknown",), Format.EXCEL),
    ],
)
def test_export_request_rejects_unavailable_components(
    components: tuple[Component, ...] | tuple[str, ...],
    format_choice: Format,
) -> None:
    with pytest.raises(ValueError):
        CorrelationExportRequest(_snapshot(), components, format_choice)  # type: ignore[arg-type]


def test_export_request_rejects_unknown_format() -> None:
    with pytest.raises(TypeError, match="format"):
        CorrelationExportRequest(_snapshot(), (Component.STRONGEST_CORRELATIONS,), "csv")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "components",
    [(), (Component.MATRIX_PLOT,), (Component.SCATTERPLOTS,), ("unknown",)],
)
def test_table_builder_rejects_empty_unknown_or_future_components(
    components: tuple[Component, ...] | tuple[str, ...],
) -> None:
    with pytest.raises(ValueError, match="strongest-correlations"):
        correlation_export_table(_snapshot(), components)  # type: ignore[arg-type]
