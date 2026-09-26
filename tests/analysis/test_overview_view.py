from __future__ import annotations

from expo_jbm329.gui.dialogs.analysis.overview_view import OverviewView
from expo_jbm329.services.analysis.overview import DatasetOverviewResult
from expo_jbm329.utils.format_utils import fmt_int, fmt_pct


def _make_result(**overrides: object) -> DatasetOverviewResult:
    defaults: dict[str, object] = {
        "row_count": 100,
        "column_count": 10,
        "missing_cell_count": 25,
        "missing_cell_fraction": 0.025,
        "duplicate_row_count": 3,
        "duplicate_row_fraction": 0.03,
        "numeric_column_count": 4,
        "categorical_column_count": 3,
        "datetime_column_count": 1,
        "boolean_column_count": 1,
        "other_column_count": 1,
        "high_missing_columns": (),
    }
    defaults.update(overrides)
    return DatasetOverviewResult(**defaults)  # type: ignore[arg-type]


def test_summary_label_shows_rows_columns_missing_and_duplicates():
    result = _make_result(row_count=100, column_count=10, missing_cell_count=25, duplicate_row_count=3)
    view = OverviewView(result)

    text = view._build_summary_label().text()  # noqa: SLF001

    assert fmt_int(100) in text
    assert fmt_int(10) in text
    assert fmt_int(25) in text
    assert fmt_int(3) in text
    assert fmt_pct(result.missing_cell_fraction) in text
    assert fmt_pct(result.duplicate_row_fraction) in text


def test_column_types_label_shows_every_bucket_count():
    result = _make_result(
        numeric_column_count=4,
        categorical_column_count=3,
        datetime_column_count=1,
        boolean_column_count=1,
        other_column_count=1,
    )
    view = OverviewView(result)

    text = view._build_column_types_label().text()  # noqa: SLF001

    assert fmt_int(4) in text
    assert fmt_int(3) in text
    assert fmt_int(1) in text


def test_warnings_label_shows_no_issues_when_nothing_flagged():
    result = _make_result(high_missing_columns=())
    view = OverviewView(result)

    label = view._build_warnings_label()  # noqa: SLF001

    assert "No issues detected" in label.text()


def test_warnings_label_lists_high_missing_columns():
    result = _make_result(high_missing_columns=(("salary", 0.6), ("age", 0.25)))
    view = OverviewView(result)

    text = view._build_warnings_label().text()  # noqa: SLF001

    assert "salary" in text
    assert "age" in text
    assert fmt_pct(0.6) in text
    assert fmt_pct(0.25) in text
