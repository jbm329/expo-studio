from __future__ import annotations

from types import SimpleNamespace

import pytest

from expo_jbm329.db.core.errors import (
    ORACLE_AMBIGUOUS_COLUMN,
    POSTGRES_AMBIGUOUS_COLUMN,
    TR_AMBIGUOUS_COLUMN,
    TR_AMBIGUOUS_COLUMN_HINT,
    classify_mssql,
    classify_mysql,
    classify_oracle,
    classify_postgresql,
    classify_sqlite,
)


@pytest.mark.parametrize(
    ("classifier", "exception", "expected_code"),
    [
        (
            classify_mssql,
            Exception("[Microsoft][ODBC SQL Server Driver] Ambiguous column name 'id'. (209)"),
            209,
        ),
        (
            classify_mysql,
            Exception("(1052, \"Column 'id' in field list is ambiguous\")"),
            1052,
        ),
        (classify_sqlite, Exception("ambiguous column name: id"), None),
        (
            classify_postgresql,
            Exception('column reference "id" is ambiguous SQLSTATE 42702'),
            POSTGRES_AMBIGUOUS_COLUMN,
        ),
        (
            classify_oracle,
            Exception("ORA-00918: column ambiguously defined"),
            ORACLE_AMBIGUOUS_COLUMN,
        ),
    ],
)
def test_classifiers_map_ambiguous_columns(classifier, exception, expected_code):
    error = classifier(exception)

    assert error.category == "ambiguous_column"
    assert error.code == expected_code
    assert error.message == TR_AMBIGUOUS_COLUMN
    assert error.hint == TR_AMBIGUOUS_COLUMN_HINT


def test_postgresql_classifier_reads_wrapped_sqlstate():
    exception = Exception("statement failed")
    exception.orig = SimpleNamespace(sqlstate="42702")

    error = classify_postgresql(exception)

    assert error.category == "ambiguous_column"
    assert error.code == POSTGRES_AMBIGUOUS_COLUMN


@pytest.mark.parametrize(
    ("classifier", "exception"),
    [
        (classify_mssql, Exception("unexpected SQL Server error")),
        (classify_mysql, Exception("unexpected MySQL error")),
        (classify_sqlite, Exception("unexpected SQLite error")),
        (classify_postgresql, Exception("unexpected PostgreSQL error")),
        (classify_oracle, Exception("unexpected Oracle error")),
    ],
)
def test_classifiers_preserve_unknown_fallback(classifier, exception):
    assert classifier(exception).category == "unknown"
