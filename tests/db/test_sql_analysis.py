from __future__ import annotations

from expo_jbm329.db.sql_analysis import (
    ColumnRef,
    ResolvedTable,
    SchemaLintContext,
    SqlDiagnostic,
    TableRef,
    _build_schema_lint_context,
    _coerce_int_or_none,
    _dedupe_diagnostics,
    _expression_name_or_none,
    _find_empty_select_list,
    _find_identifier_span_in_sql,
    _find_incomplete_top_clause,
    _find_incomplete_trailing_clause,
    _find_suspicious_adjacent_select_identifier,
    _find_suspicious_from_keyword,
    _find_suspicious_leading_keyword,
    _find_unmatched_square_bracket,
    _first_meaningful_token,
    _identifier_like_span_from_offset,
    _is_known_column,
    _last_meaningful_token_span,
    _levenshtein_distance_at_most_one,
    _lint_keyword_typos,
    _lint_schema,
    _lint_unknown_columns,
    _lint_unknown_tables,
    _looks_like_keyword_typo,
    _normalize_identifier,
    _normalize_schema_for_lint,
    _offset_to_line_column,
    _strip_leading_comments_and_whitespace,
    _strip_leading_sql_comments_and_whitespace,
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


SCHEMA = {
    "by_schema": {
        "dbo": {
            "Ref_Yrkesroll": ["Ref_Yrkesroll_ID", "Yrkesroll", "Source"],
            "users": ["id", "name"],
        },
        "sales": {
            "orders": ["id", "user_id"],
        },
    }
}


def test_sqlglot_dialect_maps_known_engines() -> None:
    assert sqlglot_dialect("mssql") == "tsql"
    assert sqlglot_dialect("postgresql") == "postgres"
    assert sqlglot_dialect("sqlite") == "sqlite"
    assert sqlglot_dialect("custom") == "custom"
    assert sqlglot_dialect(" ") is None
    assert sqlglot_dialect(None) is None


def test_parse_helpers_handle_valid_and_invalid_sql() -> None:
    assert parse_one_safe("SELECT 1") is not None
    assert parse_one_safe("   ") is None
    assert parse_many_safe("SELECT 1; SELECT 2") != []
    assert parse_many_safe("   ") == []


def test_lint_editor_rules_detect_common_cases() -> None:
    typo = lint_editor_rules("SELEC * FROM t")
    assert typo == [
        SqlDiagnostic(
            severity="error",
            message="Unknown SQL keyword. Did you mean SELECT?",
            line=1,
            column=1,
            length=5,
        )
    ]

    diagnostics = lint_editor_rules("SELECT FROM t\nSELECT [bad")
    assert any(d.message == "SELECT is missing a column list before FROM." for d in diagnostics)
    assert any(d.message == "Unclosed bracketed identifier." for d in diagnostics)

    missing_comma = lint_editor_rules("SELECT [A]\n       [B]\nFROM t")
    assert any("Possible missing comma" in d.message for d in missing_comma)

    trailing_clause = lint_editor_rules("SELECT * FROM t ORDER BY")
    assert trailing_clause[-1] == SqlDiagnostic(
        severity="error",
        message="ORDER BY is missing a sort expression.",
        line=1,
        column=17,
        length=8,
    )

    top_clause = lint_editor_rules("SELECT TOP [id] FROM t")
    assert top_clause[-1] == SqlDiagnostic(
        severity="error",
        message="TOP is missing a row count.",
        line=1,
        column=8,
        length=3,
    )


def test_keyword_typo_helpers_cover_common_keywords() -> None:
    assert _find_suspicious_leading_keyword("-- comment\nSELEC 1") == (11, 5, "SELECT")
    assert _find_suspicious_from_keyword("SELECT * FRM t") == (9, 3, "FROM")
    assert _looks_like_keyword_typo("grup", "group")
    assert not _looks_like_keyword_typo("table", "group")
    assert _levenshtein_distance_at_most_one("where", "where")
    assert _levenshtein_distance_at_most_one("wher", "where")
    assert not _levenshtein_distance_at_most_one("abc", "where")

    typo_diagnostics = _lint_keyword_typos("SELCT * GRUP BY x ORDR BY y")
    messages = {diagnostic.message for diagnostic in typo_diagnostics}
    assert "Unknown SQL keyword. Did you mean SELECT?" in messages
    assert "Unknown SQL keyword. Did you mean GROUP?" in messages
    assert "Unknown SQL keyword. Did you mean ORDER?" in messages


def test_editor_rule_helpers_find_incomplete_clauses() -> None:
    assert _find_empty_select_list("SELECT FROM t") == 0
    assert _find_empty_select_list("SELECT 1 FROM t") is None

    assert _find_incomplete_trailing_clause("SELECT * FROM t WHERE") == (
        16,
        5,
        "WHERE is missing a condition.",
    )
    assert _find_incomplete_trailing_clause("SELECT * FROM t GROUP BY") == (
        16,
        8,
        "GROUP BY is missing an expression.",
    )
    assert _find_incomplete_trailing_clause("SELECT * FROM t") is None

    assert _find_incomplete_top_clause("SELECT TOP x FROM t") == (
        7,
        3,
        "TOP is missing a row count.",
    )
    assert _find_incomplete_top_clause("SELECT TOP 10 x FROM t") is None
    assert _find_incomplete_top_clause("SELECT TOP (@n) x FROM t") is None


def test_location_helpers_cover_offsets_and_identifier_matching() -> None:
    assert _offset_to_line_column("a\nbc", 0) == (1, 1)
    assert _offset_to_line_column("a\nbc", 2) == (2, 1)

    assert _find_unmatched_square_bracket("SELECT [bad") == 7
    assert _find_unmatched_square_bracket("SELECT '[bad]'") is None

    assert _identifier_like_span_from_offset("abc def", 0) == (0, 3)
    assert _identifier_like_span_from_offset("abc", 99) == (3, 1)

    sql = "SELECT [Ref_Yrkesroll_ID] FROM [dbo].[Ref_Yrkesrol]"
    start, length = _find_identifier_span_in_sql(sql, "Ref_Yrkesrol", start_hint=0)
    assert sql[start:start + length] == "[Ref_Yrkesrol]"

    assert _find_suspicious_adjacent_select_identifier("SELECT [A]\n [B] FROM t") == (12, 3)
    assert _last_meaningful_token_span("SELECT [abc]") == (7, 5)


def test_normalization_and_scalar_helpers() -> None:
    assert _normalize_identifier('[AbC]') == "abc"
    assert _normalize_schema_for_lint(SCHEMA) == {
        "dbo": {
            "ref_yrkesroll": {"ref_yrkesroll_id", "yrkesroll", "source"},
            "users": {"id", "name"},
        },
        "sales": {
            "orders": {"id", "user_id"},
        },
    }
    assert _normalize_schema_for_lint({"dbo": {"users": ["id"]}}) == {
        "dbo": {"users": {"id"}}
    }
    assert _normalize_schema_for_lint(None) == {}

    assert _coerce_int_or_none(3) == 3
    assert _coerce_int_or_none("4") == 4
    assert _coerce_int_or_none("x") is None
    assert _expression_name_or_none("dbo") == "dbo"
    assert _expression_name_or_none(None) is None


def test_comment_and_token_helpers() -> None:
    assert _strip_leading_sql_comments_and_whitespace("  -- x\nSELECT 1") == "SELECT 1"
    assert _strip_leading_comments_and_whitespace("/* a */  SELECT 1") == "SELECT 1"
    assert _first_meaningful_token("  -- x\nWITH cte AS (SELECT 1) SELECT 1") == "with"


def test_dedupe_diagnostics_keeps_first_unique_entries() -> None:
    diagnostics = [
        SqlDiagnostic("error", "A", 1, 1, 1),
        SqlDiagnostic("error", "A", 1, 1, 1),
        SqlDiagnostic("warning", "A", 1, 1, 1),
    ]

    assert _dedupe_diagnostics(diagnostics) == [
        SqlDiagnostic("error", "A", 1, 1, 1),
        SqlDiagnostic("warning", "A", 1, 1, 1),
    ]


def test_schema_context_helpers_resolve_tables_and_columns() -> None:
    expression = parse_one_safe(
        "SELECT u.id, missing_col FROM dbo.users AS u JOIN sales.orders o ON o.user_id = u.id"
    )
    assert expression is not None

    context = _build_schema_lint_context(expression, _normalize_schema_for_lint(SCHEMA))
    assert context == SchemaLintContext(
        known_schemas={"dbo", "sales"},
        visible_tables={"users", "orders"},
        resolved_tables={
            "users": ResolvedTable(schema_name="dbo", table_name="users", columns={"id", "name"}),
            "orders": ResolvedTable(schema_name="sales", table_name="orders", columns={"id", "user_id"}),
        },
        unresolved_tables=set(),
    )

    assert _is_known_column("id", "users", context)
    assert _is_known_column("id", None, context)
    assert not _is_known_column("missing_col", None, context)
    assert not _is_known_column("id", "unknown_alias", context)


def test_schema_lint_helpers_report_unknown_schema_table_and_column() -> None:
    normalized_schema = _normalize_schema_for_lint(SCHEMA)

    unknown_schema_expression = parse_one_safe("SELECT * FROM bad.users")
    assert unknown_schema_expression is not None
    unknown_schema_context = _build_schema_lint_context(unknown_schema_expression, normalized_schema)
    assert _lint_unknown_tables("SELECT * FROM bad.users", unknown_schema_expression, unknown_schema_context) == [
        SqlDiagnostic(
            severity="error",
            message="Unknown schema 'bad'.",
            line=1,
            column=15,
            length=3,
        )
    ]

    unknown_table_expression = parse_one_safe("SELECT * FROM dbo.unknown_table")
    assert unknown_table_expression is not None
    unknown_table_context = _build_schema_lint_context(unknown_table_expression, normalized_schema)
    assert _lint_unknown_tables(
        "SELECT * FROM dbo.unknown_table",
        unknown_table_expression,
        unknown_table_context,
    ) == [
        SqlDiagnostic(
            severity="error",
            message="Unknown table 'unknown_table'.",
            line=1,
            column=19,
            length=13,
        )
    ]

    unknown_column_expression = parse_one_safe("SELECT users.id, missing_col FROM dbo.users")
    assert unknown_column_expression is not None
    unknown_column_context = _build_schema_lint_context(unknown_column_expression, normalized_schema)
    assert _lint_unknown_columns(
        "SELECT users.id, missing_col FROM dbo.users",
        unknown_column_expression,
        unknown_column_context,
    ) == [
        SqlDiagnostic(
            severity="error",
            message="Unknown column 'missing_col' for the current schema context.",
            line=1,
            column=18,
            length=11,
        )
    ]


def test_lint_schema_and_lint_syntax_cover_layered_schema_aware_behavior() -> None:
    diagnostics = _lint_schema(
        "SELECT [Ref_Yrkesroll_IDD], [Yrkesroll] FROM [dbo].[Ref_Yrkesroll]",
        schema=SCHEMA,
        dialect="tsql",
    )
    assert diagnostics == [
        SqlDiagnostic(
            severity="error",
            message="Unknown column 'Ref_Yrkesroll_IDD' for the current schema context.",
            line=1,
            column=8,
            length=19,
        )
    ]

    diagnostics = lint_syntax("SELEC * FROM t")
    assert diagnostics
    assert diagnostics[0].message == "Unknown SQL keyword. Did you mean SELECT?"

    diagnostics = lint_syntax("SELECT * FROM dbo.unknown_table", schema=SCHEMA)
    assert any(d.message == "Unknown table 'unknown_table'." for d in diagnostics)

    diagnostics = lint_syntax("SELECT * FROM bad.Ref_Yrkesroll", schema=SCHEMA)
    assert any(d.message == "Unknown schema 'bad'." for d in diagnostics)

    diagnostics = lint_syntax("SELECT * FROM dbo.users WHERE")
    assert any(d.message == "WHERE is missing a condition." for d in diagnostics)


def test_detect_statement_kind_and_select_like_cover_main_paths() -> None:
    assert detect_statement_kind("SELECT 1") == "select"
    assert detect_statement_kind("WITH cte AS (SELECT 1) SELECT * FROM cte") == "select"
    assert detect_statement_kind("EXEC dbo.proc") == "exec"
    assert detect_statement_kind("INSERT INTO t VALUES (1)") == "insert"
    assert detect_statement_kind("UPDATE t SET a = 1") == "update"
    assert detect_statement_kind("DELETE FROM t") == "delete"
    assert detect_statement_kind("CREATE TABLE t (id int)") == "create"
    assert detect_statement_kind("DROP TABLE t") == "drop"
    assert detect_statement_kind("ALTER TABLE t ADD c int") == "alter"
    assert detect_statement_kind("TRUNCATE TABLE t") == "truncate"
    assert detect_statement_kind("FOOBAR 1") == "invalid"
    assert detect_statement_kind("   ") == "empty"

    assert is_select_like("SELECT 1")
    assert is_select_like("WITH cte AS (SELECT 1) SELECT * FROM cte")
    assert not is_select_like("DELETE FROM t")


def test_extract_refs_format_sql_and_multiple_statements() -> None:
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

    formatted = format_sql("SELECT 1", pretty=False)
    assert formatted.upper().startswith("SELECT")
    assert format_sql("   ", pretty=False) == "   "
    assert has_multiple_statements("SELECT 1; SELECT 2")
