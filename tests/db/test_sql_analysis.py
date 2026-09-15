from __future__ import annotations

from expo_jbm329.db.sql_analysis import (
    ColumnRef,
    SqlDiagnostic,
    TableRef,
    _lint_keyword_typos,
    detect_statement_kind,
    extract_column_refs,
    extract_table_aliases,
    extract_table_refs,
    format_sql,
    has_multiple_statements,
    is_select_like,
    lint_editor_rules,
    lint_syntax,
    parse_many_safe,
    parse_one_safe,
    sqlglot_dialect,
)


def test_sqlglot_dialect_maps_known_engines():
    assert sqlglot_dialect("mssql") == "tsql"
    assert sqlglot_dialect("postgresql") == "postgres"
    assert sqlglot_dialect("sqlite") == "sqlite"
    assert sqlglot_dialect("custom") == "custom"
    assert sqlglot_dialect(" ") is None
    assert sqlglot_dialect(None) is None


def test_parse_helpers_handle_valid_and_invalid_sql():
    assert parse_one_safe("SELECT 1") is not None
    assert parse_one_safe("   ") is None
    assert parse_many_safe("SELECT 1; SELECT 2") != []
    assert parse_many_safe("   ") == []


def test_lint_editor_rules_detects_common_editor_errors():
    diagnostics = lint_editor_rules("SELEC * FROM t")
    assert diagnostics == [
        SqlDiagnostic(
            severity="error",
            message="Unknown SQL keyword. Did you mean SELECT?",
            line=1,
            column=1,
            length=5,
        )
    ]


def test_lint_editor_rules_detects_empty_select_and_brackets():
    diagnostics = lint_editor_rules("SELECT FROM t\nSELECT [bad")
    assert any(d.message == "SELECT is missing a column list before FROM." for d in diagnostics)
    assert any(d.message == "Unclosed bracketed identifier." for d in diagnostics)


def test_lint_syntax_returns_editor_diagnostics_before_parser_errors():
    diagnostics = lint_syntax("SELEC * FROM t")
    assert diagnostics
    assert diagnostics[0].message == "Unknown SQL keyword. Did you mean SELECT?"


def test_detect_statement_kind_and_select_like():
    assert detect_statement_kind("SELECT 1") == "select"
    assert detect_statement_kind("WITH cte AS (SELECT 1) SELECT * FROM cte") == "select"
    assert detect_statement_kind("EXEC dbo.proc") == "exec"
    assert detect_statement_kind("INSERT INTO t VALUES (1)") == "insert"
    assert is_select_like("SELECT 1")
    assert is_select_like("WITH cte AS (SELECT 1) SELECT * FROM cte")
    assert not is_select_like("DELETE FROM t")


def test_extract_table_and_column_refs():
    sql = "SELECT u.id, u.name FROM dbo.users AS u JOIN sales.orders o ON o.user_id = u.id"

    tables = extract_table_refs(sql)
    assert tables == [
        TableRef(name="users", schema="dbo", catalog=None, alias="u"),
        TableRef(name="orders", schema="sales", catalog=None, alias="o"),
    ]

    aliases = extract_table_aliases(sql)
    assert aliases["u"] == TableRef(name="users", schema="dbo", catalog=None, alias="u")
    assert aliases["o"] == TableRef(name="orders", schema="sales", catalog=None, alias="o")

    columns = extract_column_refs(sql)
    assert ColumnRef(name="id", table="u", schema=None, catalog=None) in columns
    assert ColumnRef(name="name", table="u", schema=None, catalog=None) in columns


def test_format_sql_and_multiple_statements():
    formatted = format_sql("SELECT 1", pretty=False)
    assert formatted.upper().startswith("SELECT")
    assert format_sql("   ", pretty=False) == "   "
    assert has_multiple_statements("SELECT 1; SELECT 2")


def test_lint_editor_rules_catches_from_typos_and_keyword_typos():
    diagnostics = lint_editor_rules("SELECT * FRM t")
    assert any(d.message == "Unknown SQL keyword. Did you mean FROM?" for d in diagnostics)

    typo_diagnostics = _lint_keyword_typos("SELCT * GRUP BY x")
    assert any(d.message == "Unknown SQL keyword. Did you mean SELECT?" for d in typo_diagnostics)
    assert any(d.message == "Unknown SQL keyword. Did you mean GROUP?" for d in typo_diagnostics)


def test_lint_syntax_checks_schema_violations_and_statement_fallbacks():
    schema = {"by_schema": {"dbo": {"users": ["id", "name"], "orders": ["id", "user_id"]}}}

    diagnostics = lint_syntax("SELECT users.id, missing_col FROM dbo.users", schema=schema)
    assert any(d.message == "Unknown column 'missing_col' for the current schema context." for d in diagnostics)

    diagnostics = lint_syntax("SELECT * FROM dbo.unknown_table", schema=schema)
    assert any(d.message == "Unknown table 'unknown_table'." for d in diagnostics)

    assert detect_statement_kind("TRUNCATE TABLE t") == "truncate"
    assert detect_statement_kind("FOOBAR 1") == "invalid"
