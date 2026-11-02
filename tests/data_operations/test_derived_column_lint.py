"""Position adapters retain raw formula offsets without inventing name spans."""

import pandas as pd
import pytest

from expo_jbm329.services.data_operations.derived_column.derived_column_lint import formula_error_span
from expo_jbm329.services.data_operations.derived_column.derived_column_parser import DerivedColumnFormulaError
from expo_jbm329.services.data_operations.derived_column.derived_column_service import (
    DerivedColumnSpec,
    validate_derived_column_spec,
)


@pytest.mark.parametrize(
    ("formula", "expected"),
    [
        ("  [missing]", (2, 11)),
        ("'😀' +\n [missing]", (7, 16)),
        ("IF(TRUE; 1; ", (12, 12)),
        ("'unclosed", (0, 9)),
        ("[Age", (0, 4)),
    ],
)
def test_service_errors_map_to_raw_formula_spans(formula, expected):
    result = validate_derived_column_spec(pd.DataFrame({"Age": [1]}), DerivedColumnSpec("Group", formula))
    assert not result.ok
    assert formula_error_span(formula, result.error) == expected


@pytest.mark.parametrize(
    "code",
    ["missing_output_column_name", "invalid_output_column_name_characters", "output_column_exists"],
)
def test_output_name_errors_have_no_formula_span(code):
    assert formula_error_span("[Age] + 1", DerivedColumnFormulaError(code)) is None


@pytest.mark.parametrize(
    ("context", "expected"),
    [
        ({}, None),
        ({"position": "bad"}, None),
        ({"position": 2}, (2, 2)),
        ({"position": 2, "end": "bad"}, (2, 2)),
        ({"position": -10, "end": 99}, (0, 3)),
        ({"position": 99, "end": -10}, (3, 3)),
    ],
)
def test_span_adapter_bounds_offsets_and_handles_unpositioned_errors(context, expected):
    assert formula_error_span("123", DerivedColumnFormulaError("test", context=context)) == expected
