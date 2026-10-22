from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import duckdb
import pytest
from PyQt6.QtCore import QTranslator
from sqlalchemy.exc import OperationalError

from expo_jbm329.db.core.errors import (
    ORACLE_AMBIGUOUS_COLUMN,
    POSTGRES_AMBIGUOUS_COLUMN,
    TR_AMBIGUOUS_COLUMN,
    TR_AMBIGUOUS_COLUMN_HINT,
    TR_CONNECTION_FAILED_POSTGRES,
    TR_DRIVER_MISSING_HINT_DUCKDB,
    TR_DRIVER_MISSING_HINT_MYSQL,
    TR_DRIVER_MISSING_HINT_POSTGRES,
    TR_DRIVER_MISSING_MYSQL,
    TR_DRIVER_MISSING_POSTGRES,
    TR_FUNCTION_NOT_EXISTS_POSTGRES,
    TR_INVALID_CONFIG_DUCKDB,
    TR_INVALID_CONFIG_HINT_DUCKDB,
    TR_LOCKED_HINT_DUCKDB,
    TR_PERMISSION_DENIED_POSTGRES,
    TR_PERMISSION_HINT_DUCKDB,
    TR_SQL_SYNTAX_ERROR_POSTGRES,
    TR_TABLE_OR_VIEW_NOT_EXISTS_POSTGRES,
    TR_TIMEOUT_POSTGRES,
    TR_UNKNOWN_COLUMN_POSTGRES,
    TR_UNKNOWN_DATABASE_POSTGRES,
    classify_duckdb,
    classify_mssql,
    classify_mysql,
    classify_oracle,
    classify_postgresql,
    classify_sqlite,
)
from expo_jbm329.i18n.language import Language


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
    ("exception", "category"),
    [
        (ValueError("invalid configuration"), "connection"),
        (FileNotFoundError("missing.duckdb"), "connection"),
        (IsADirectoryError("directory"), "connection"),
        (PermissionError("file denied"), "permission"),
        (duckdb.PermissionException("Cannot write"), "permission"),
        (duckdb.IOException("Could not set lock on file: Conflicting lock is held"), "connection"),
        (duckdb.IOException("file is not a valid DuckDB database file"), "connection"),
        (duckdb.CatalogException("Schema with name missing does not exist!"), "missing_object"),
        (ModuleNotFoundError("No module named duckdb_engine"), "driver_missing"),
        (RuntimeError("Can't load plugin: sqlalchemy.dialects:duckdb"), "driver_missing"),
        (RuntimeError("unrecognized database failure"), "unknown"),
    ],
)
def test_duckdb_classification_handles_native_and_wrapped_errors(exception, category):
    for error in (exception, OperationalError("SELECT 1", {}, exception)):
        classified = classify_duckdb(error)
        assert classified.category == category
        assert classified.code is None
        assert classified.message
        assert classified.hint


@pytest.mark.parametrize("language", list(Language))
def test_duckdb_error_messages_have_compiled_translations(language):
    catalog = Path(__file__).parents[2] / "src" / "expo_jbm329" / "i18n" / "locales" / f"app_{language.value}.qm"
    translator = QTranslator()
    assert translator.load(str(catalog))
    sources = [
        TR_INVALID_CONFIG_DUCKDB,
        TR_INVALID_CONFIG_HINT_DUCKDB,
        TR_LOCKED_HINT_DUCKDB,
        TR_PERMISSION_HINT_DUCKDB,
        TR_DRIVER_MISSING_HINT_DUCKDB,
    ]
    for source in sources:
        translated = translator.translate("DbErrors", source)
        if language.value == "en":
            assert not translated
        else:
            assert translated and translated != source


@pytest.mark.parametrize(
    "exception",
    [
        ModuleNotFoundError("No module named 'mysql'"),
        ModuleNotFoundError("No module named 'pymysql'"),
        ModuleNotFoundError("No module named 'mysql.connector'"),
        ImportError("cannot import name 'connector' from 'mysql'"),
        Exception("No module named 'mysql'"),
        Exception("No module named 'pymysql'"),
    ],
)
def test_mysql_classifier_detects_missing_driver(exception):
    error = classify_mysql(exception)

    assert error.category == "driver_missing"
    assert error.code is None
    assert error.message == TR_DRIVER_MISSING_MYSQL
    assert error.hint == TR_DRIVER_MISSING_HINT_MYSQL


@pytest.mark.parametrize(
    "exception",
    [
        ModuleNotFoundError("No module named 'psycopg'"),
        ImportError("cannot import name 'connect' from 'psycopg'"),
        Exception("No module named 'psycopg'"),
    ],
)
def test_postgresql_classifier_detects_missing_driver(exception):
    error = classify_postgresql(exception)

    assert error.category == "driver_missing"
    assert error.code is None
    assert error.message == TR_DRIVER_MISSING_POSTGRES
    assert error.hint == TR_DRIVER_MISSING_HINT_POSTGRES


@pytest.mark.parametrize(
    ("exception", "expected_category", "expected_code", "expected_message"),
    [
        (
            Exception('relation "users" does not exist (SQLSTATE 42P01)'),
            "missing_object",
            None,
            TR_TABLE_OR_VIEW_NOT_EXISTS_POSTGRES,
        ),
        (
            Exception('column "email" does not exist (SQLSTATE 42703)'),
            "syntax",
            42703,
            TR_UNKNOWN_COLUMN_POSTGRES,
        ),
        (
            Exception("function my_func(integer) does not exist (SQLSTATE 42883)"),
            "missing_proc",
            42883,
            TR_FUNCTION_NOT_EXISTS_POSTGRES,
        ),
        (
            Exception('syntax error at or near "SELCT" (SQLSTATE 42601)'),
            "syntax",
            42601,
            TR_SQL_SYNTAX_ERROR_POSTGRES,
        ),
        (
            Exception('password authentication failed for user "postgres" (SQLSTATE 28P01)'),
            "permission",
            None,
            TR_PERMISSION_DENIED_POSTGRES,
        ),
        (
            Exception('database "unknown_db" does not exist (SQLSTATE 3D000)'),
            "connection",
            None,
            TR_UNKNOWN_DATABASE_POSTGRES,
        ),
        (
            Exception("canceling statement due to statement timeout (SQLSTATE 57014)"),
            "timeout",
            57014,
            TR_TIMEOUT_POSTGRES,
        ),
        (
            Exception("could not connect to server: Connection refused (SQLSTATE 08001)"),
            "connection",
            8001,
            TR_CONNECTION_FAILED_POSTGRES,
        ),
    ],
)
def test_postgresql_classifier_maps_sqlstate_codes(exception, expected_category, expected_code, expected_message):
    error = classify_postgresql(exception)

    assert error.category == expected_category
    assert error.code == expected_code
    assert error.message == expected_message


def test_postgresql_classifier_reads_wrapped_pgcode():
    exception = Exception("statement failed")
    exception.orig = SimpleNamespace(pgcode="42P01")

    error = classify_postgresql(exception)

    assert error.category == "missing_object"
    assert error.message == TR_TABLE_OR_VIEW_NOT_EXISTS_POSTGRES


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
