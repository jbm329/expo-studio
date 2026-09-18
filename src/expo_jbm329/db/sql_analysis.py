"""SQL parsing, linting, and analysis helpers.

This module centralizes SQL-aware functionality built on top of sqlglot.

It is intentionally UI-free so it can be reused by:
- SQL editor autocomplete
- SQL editor linting
- database execution validation
- query formatting
- future dialect-related helpers
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, cast

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError, SqlglotError

if TYPE_CHECKING:
    from sqlglot.expressions import Expression

SqlStatementKind = Literal[
    "select",
    "with",
    "exec",
    "insert",
    "update",
    "delete",
    "create",
    "drop",
    "alter",
    "truncate",
    "other",
    "empty",
    "invalid",
]


SQLGLOT_DIALECT_BY_ENGINE: dict[str, str] = {
    "mssql": "tsql",
    "tsql": "tsql",
    "postgresql": "postgres",
    "postgres": "postgres",
    "mysql": "mysql",
    "mariadb": "mysql",
    "sqlite": "sqlite",
    "oracle": "oracle",
}


@dataclass(frozen=True)
class SqlDiagnostic:
    """A SQL diagnostic suitable for editor linting.

    Attributes:
        severity: Diagnostic severity, usually "error", "warning", or "info".
        message: Human-readable diagnostic message.
        line: Optional 1-based line number.
        column: Optional 1-based column number.
        length: Number of characters to underline.
    """

    severity: str
    message: str
    line: int | None = None
    column: int | None = None
    length: int = 1


@dataclass(frozen=True)
class TableRef:
    """A table reference discovered in a SQL statement.

    Attributes:
        name: Table/object name without schema.
        schema: Optional schema/database qualifier.
        catalog: Optional catalog qualifier, when sqlglot can identify one.
        alias: Optional table alias.
    """

    name: str
    schema: str | None = None
    catalog: str | None = None
    alias: str | None = None


@dataclass(frozen=True)
class ColumnRef:
    """A column reference discovered in a SQL statement.

    Attributes:
        name: Column name.
        table: Optional table/alias qualifier.
        schema: Optional schema qualifier.
        catalog: Optional catalog qualifier.
    """

    name: str
    table: str | None = None
    schema: str | None = None
    catalog: str | None = None


@dataclass(frozen=True)
class ResolvedTable:
    """Resolved schema information for a table visible in a statement."""

    schema_name: str | None
    table_name: str
    columns: set[str]


@dataclass(frozen=True)
class SchemaLintContext:
    """Resolved schema context for schema-aware linting."""

    known_schemas: set[str]
    visible_tables: set[str]
    resolved_tables: dict[str, ResolvedTable]
    unresolved_tables: set[str]


def sqlglot_dialect(engine_or_dialect: str | None) -> str | None:
    """Return the sqlglot dialect name for an internal engine/dialect name.

    Args:
        engine_or_dialect: Internal database engine name or already-valid sqlglot
            dialect name.

    Returns:
        A sqlglot dialect name, or None when no dialect was supplied.
    """
    if not engine_or_dialect:
        return None

    key = engine_or_dialect.strip().lower()
    if not key:
        return None

    return SQLGLOT_DIALECT_BY_ENGINE.get(key, key)


# noinspection PyBroadException
def parse_one_safe(sql: str, dialect: str | None = None) -> exp.Expression | None:
    """Parse one SQL statement safely.

    Args:
        sql: SQL text to parse.
        dialect: Optional internal engine name or sqlglot dialect name.

    Returns:
        The parsed sqlglot expression, or None if parsing fails.
    """
    if not isinstance(sql, str) or not sql.strip():
        return None

    try:
        return sqlglot.parse_one(sql, read=sqlglot_dialect(dialect))
    except (
        AttributeError,
        ConnectionError,
        FileNotFoundError,
        IndexError,
        KeyError,
        LookupError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ):
        return None


# noinspection PyBroadException
def parse_many_safe(sql: str, dialect: str | None = None) -> list[Expression]:
    """Parse SQL text into zero or more statements safely.

    Args:
        sql: SQL text to parse.
        dialect: Optional internal engine name or sqlglot dialect name.

    Returns:
        A list of parsed sqlglot expressions. Returns an empty list on failure.
    """
    if not isinstance(sql, str) or not sql.strip():
        return []

    try:
        parsed = sqlglot.parse(sql, read=sqlglot_dialect(dialect))
        return [cast("Expression", expression) for expression in parsed if expression is not None]
    except (
        AttributeError,
        ConnectionError,
        FileNotFoundError,
        IndexError,
        KeyError,
        LookupError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ):
        return []


_EMPTY_SELECT_LIST_RE = re.compile(r"(?is)\bselect\b\s*\bfrom\b")


def lint_editor_rules(sql: str) -> list[SqlDiagnostic]:
    """Return lightweight editor-oriented SQL diagnostics.

    These rules catch cases that may be accepted or ambiguously parsed by a SQL
    parser but are not useful in the editor.
    """
    if not isinstance(sql, str) or not sql.strip():
        return []

    diagnostics: list[SqlDiagnostic] = []

    suspicious_keyword = _find_suspicious_leading_keyword(sql)
    if suspicious_keyword is not None:
        start, length, suggestion = suspicious_keyword
        line, column = _offset_to_line_column(sql, start)
        diagnostics.append(
            SqlDiagnostic(
                severity="error",
                message=f"Unknown SQL keyword. Did you mean {suggestion}?",
                line=line,
                column=column,
                length=length,
            )
        )

    suspicious_from = _find_suspicious_from_keyword(sql)
    if suspicious_from is not None:
        start, length, suggestion = suspicious_from
        line, column = _offset_to_line_column(sql, start)
        diagnostics.append(
            SqlDiagnostic(
                severity="error",
                message=f"Unknown SQL keyword. Did you mean {suggestion}?",
                line=line,
                column=column,
                length=length,
            )
        )

    unmatched_bracket = _find_unmatched_square_bracket(sql)
    if unmatched_bracket is not None:
        start, length = _identifier_like_span_from_offset(sql, unmatched_bracket)
        line, column = _offset_to_line_column(sql, start)
        diagnostics.append(
            SqlDiagnostic(
                severity="error",
                message="Unclosed bracketed identifier.",
                line=line,
                column=column,
                length=length,
            )
        )

    empty_select = _find_empty_select_list(sql)
    if empty_select is not None:
        line, column = _offset_to_line_column(sql, empty_select)
        diagnostics.append(
            SqlDiagnostic(
                severity="error",
                message="SELECT is missing a column list before FROM.",
                line=line,
                column=column,
                length=6,
            )
        )

    suspicious_adjacent_identifier = _find_suspicious_adjacent_select_identifier(sql)
    if suspicious_adjacent_identifier is not None:
        start, length = suspicious_adjacent_identifier
        line, column = _offset_to_line_column(sql, start)
        diagnostics.append(
            SqlDiagnostic(
                severity="warning",
                message=(
                    "Possible missing comma before this identifier. "
                    "If this is intended as an alias, consider using AS for clarity."
                ),
                line=line,
                column=column,
                length=length,
            )
        )

    incomplete_clause = _find_incomplete_trailing_clause(sql)
    if incomplete_clause is not None:
        start, length, message = incomplete_clause
        line, column = _offset_to_line_column(sql, start)
        diagnostics.append(
            SqlDiagnostic(
                severity="error",
                message=message,
                line=line,
                column=column,
                length=length,
            )
        )

    incomplete_top = _find_incomplete_top_clause(sql)
    if incomplete_top is not None:
        start, length, message = incomplete_top
        line, column = _offset_to_line_column(sql, start)
        diagnostics.append(
            SqlDiagnostic(
                severity="error",
                message=message,
                line=line,
                column=column,
                length=length,
            )
        )

    return diagnostics


_COMMON_LEADING_KEYWORDS = {
    "select",
    "with",
    "insert",
    "update",
    "delete",
    "create",
    "drop",
    "alter",
    "truncate",
    "exec",
    "execute",
}


def _find_suspicious_leading_keyword(sql: str) -> tuple[int, int, str] | None:
    """Find common misspellings of leading SQL keywords."""
    text = _strip_leading_sql_comments_and_whitespace(sql)
    leading_offset = len(sql) - len(text)

    match = re.match(r"[A-Za-z_][A-Za-z0-9_]*", text)
    if match is None:
        return None

    token = match.group(0)
    token_l = token.lower()

    if token_l in _COMMON_LEADING_KEYWORDS:
        return None

    if _looks_like_keyword_typo(token_l, "select"):
        return leading_offset + match.start(), len(token), "SELECT"

    if _looks_like_keyword_typo(token_l, "with"):
        return leading_offset + match.start(), len(token), "WITH"

    return None


def _find_suspicious_from_keyword(sql: str) -> tuple[int, int, str] | None:
    """Find common misspellings of FROM in SQL text."""
    for match in re.finditer(r"(?is)\b[A-Za-z_][A-Za-z0-9_]*\b", sql):
        token = match.group(0)
        token_l = token.lower()

        if token_l == "from":  # noqa S105
            continue

        if _looks_like_keyword_typo(token_l, "from"):
            return match.start(), len(token), "FROM"

    return None


def _looks_like_keyword_typo(token: str, keyword: str) -> bool:
    """Return True if token appears to be a typo of keyword."""
    if not token or not keyword:
        return False

    if abs(len(token) - len(keyword)) > 1:
        return False

    if token[0] != keyword[0]:
        return False

    return _levenshtein_distance_at_most_one(token, keyword)


def _levenshtein_distance_at_most_one(a: str, b: str) -> bool:
    """Return True when two strings have edit distance <= 1."""
    if a == b:
        return True

    if abs(len(a) - len(b)) > 1:
        return False

    if len(a) == len(b):
        differences = sum(1 for ca, cb in zip(a, b, strict=False) if ca != cb)
        return differences <= 1

    if len(a) > len(b):
        a, b = b, a

    i = 0
    j = 0
    edits = 0

    while i < len(a) and j < len(b):
        if a[i] == b[j]:
            i += 1
            j += 1
            continue

        edits += 1
        if edits > 1:
            return False

        j += 1

    return True


def _strip_leading_sql_comments_and_whitespace(sql: str) -> str:
    """Strip leading whitespace and common SQL comments."""
    text = sql

    while True:
        stripped = text.lstrip()

        if stripped.startswith("--"):
            newline_index = stripped.find("\n")
            if newline_index < 0:
                return ""
            text = stripped[newline_index + 1 :]
            continue

        if stripped.startswith("/*"):
            end_index = stripped.find("*/")
            if end_index < 0:
                return ""
            text = stripped[end_index + 2 :]
            continue

        return stripped


def _find_empty_select_list(sql: str) -> int | None:
    """Return offset of SELECT when SELECT has no expression before FROM."""
    match = _EMPTY_SELECT_LIST_RE.search(sql)
    if match is None:
        return None

    return match.start()


def _find_incomplete_top_clause(sql: str) -> tuple[int, int, str] | None:
    """Return a diagnostic when TOP is missing its row count."""
    match = re.search(r"(?is)\btop\b", sql)
    if match is None:
        return None

    remainder = sql[match.end() :]

    if re.match(r"^\s*(\(\s*(\d+|@\w+)\s*\)|\d+|@\w+)", remainder):
        return None

    start = match.start()
    length = max(1, match.end() - match.start())
    return start, length, "TOP is missing a row count."


def _offset_to_line_column(sql: str, offset: int) -> tuple[int, int]:
    """Convert zero-based text offset to one-based line and column."""
    safe_offset = max(0, min(offset, len(sql)))
    before = sql[:safe_offset]

    line = before.count("\n") + 1
    last_newline = before.rfind("\n")

    column = safe_offset + 1 if last_newline < 0 else safe_offset - last_newline

    return line, column


def _dedupe_diagnostics(diagnostics: list[SqlDiagnostic]) -> list[SqlDiagnostic]:
    """Remove duplicate diagnostics by message + location."""
    seen: set[tuple[str, int | None, int | None, int, str]] = set()
    deduped: list[SqlDiagnostic] = []

    for diagnostic in diagnostics:
        key = (
            diagnostic.message,
            diagnostic.line,
            diagnostic.column,
            diagnostic.length,
            diagnostic.severity,
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(diagnostic)

    return deduped


_COMMON_SQL_KEYWORDS = {
    "select",
    "with",
    "insert",
    "update",
    "delete",
    "from",
    "join",
    "where",
    "group",
    "order",
    "by",
    "having",
    "on",
    "as",
    "and",
    "or",
    "limit",
    "offset",
    "union",
    "intersect",
    "except",
    "into",
    "values",
    "case",
    "when",
    "then",
    "else",
    "end",
    "distinct",
    "top",
    "desc",
    "asc",
}

_COMMON_SQL_KEYWORD_ALIASES = {
    "orderby": "ORDER BY",
    "groupby": "GROUP BY",
    "orderbyby": "ORDER BY",
    "groupbyby": "GROUP BY",
}


def _lint_keyword_typos(sql: str) -> list[SqlDiagnostic]:
    """Return diagnostics for likely SQL keyword typos.

    This is intentionally lightweight. It focuses on positions where SQL
    keywords are actually expected so valid identifiers such as column names do
    not get flagged as keyword typos.
    """
    if not isinstance(sql, str) or not sql.strip():
        return []

    diagnostics: list[SqlDiagnostic] = []

    leading_keyword = _find_suspicious_leading_keyword(sql)
    if leading_keyword is not None:
        start, length, suggestion = leading_keyword
        line, column = _offset_to_line_column(sql, start)
        diagnostics.append(
            SqlDiagnostic(
                severity="error",
                message=f"Unknown SQL keyword. Did you mean {suggestion}?",
                line=line,
                column=column,
                length=length,
            )
        )

    for start, length, suggestion in _find_suspicious_clause_keywords(sql):
        line, column = _offset_to_line_column(sql, start)
        diagnostics.append(
            SqlDiagnostic(
                severity="error",
                message=f"Unknown SQL keyword. Did you mean {suggestion}?",
                line=line,
                column=column,
                length=length,
            )
        )

    return diagnostics


def _suggest_keyword(token: str) -> str | None:
    """Return a likely SQL keyword for a token typo."""
    if not token:
        return None

    token_l = token.lower()

    if token_l in _COMMON_SQL_KEYWORD_ALIASES:
        return _COMMON_SQL_KEYWORD_ALIASES[token_l]

    for candidate in _COMMON_SQL_KEYWORDS:
        if _looks_like_keyword_typo(token_l, candidate):
            return candidate.upper()

    return None


def _find_suspicious_clause_keywords(sql: str) -> list[tuple[int, int, str]]:
    """Find likely clause-keyword typos after valid SQL clause anchors."""
    diagnostics: list[tuple[int, int, str]] = []

    for match in re.finditer(r"(?is)\b[A-Za-z_][A-Za-z0-9_]*\b", sql):
        token = match.group(0)
        token_l = token.lower()

        if token_l in _COMMON_SQL_KEYWORDS:
            continue

        previous_keyword = _previous_meaningful_keyword(sql, match.start())
        suggestion = _suggest_keyword_for_context(token_l, previous_keyword)
        if suggestion is None:
            continue

        diagnostics.append((match.start(), len(token), suggestion))

    return diagnostics


def _previous_meaningful_keyword(sql: str, token_start: int) -> str | None:
    """Return the nearest preceding SQL keyword-like token."""
    previous_keyword: str | None = None

    for match in re.finditer(r"(?is)\b[A-Za-z_][A-Za-z0-9_]*\b", sql[:token_start]):
        candidate = match.group(0).lower()
        if candidate in _COMMON_SQL_KEYWORDS:
            previous_keyword = candidate

    return previous_keyword


def _suggest_keyword_for_context(token: str, previous_keyword: str | None) -> str | None:
    """Return a keyword suggestion when the surrounding clause expects one."""
    if not token:
        return None

    if previous_keyword == "select" and _levenshtein_distance_at_most_one(token, "from"):
        return "FROM"

    if previous_keyword == "group" and _levenshtein_distance_at_most_one(token, "by"):
        return "BY"

    if previous_keyword == "order" and _levenshtein_distance_at_most_one(token, "by"):
        return "BY"

    if _looks_like_keyword_typo(token, "group"):
        return "GROUP"

    if _looks_like_keyword_typo(token, "order"):
        return "ORDER"

    return None


_INCOMPLETE_TRAILING_CLAUSE_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"(?is)\bwhere\s*$", "WHERE is missing a condition."),
    (r"(?is)\border\s+by\s*$", "ORDER BY is missing a sort expression."),
    (r"(?is)\border\s*$", "ORDER is incomplete. Did you mean ORDER BY?"),
    (r"(?is)\bgroup\s+by\s*$", "GROUP BY is missing an expression."),
    (r"(?is)\bgroup\s*$", "GROUP is incomplete. Did you mean GROUP BY?"),
    (r"(?is)\bhaving\s*$", "HAVING is missing a condition."),
    (r"(?is)\bjoin\s*$", "JOIN is missing a table."),
    (r"(?is)\bon\s*$", "ON is missing a join condition."),
)


def _find_incomplete_trailing_clause(sql: str) -> tuple[int, int, str] | None:
    """Return a diagnostic span for a common incomplete trailing clause."""
    for pattern, message in _INCOMPLETE_TRAILING_CLAUSE_PATTERNS:
        match = re.search(pattern, sql)
        if match is None:
            continue
        return match.start(), max(1, match.end() - match.start()), message

    return None


def _normalize_identifier(value: str | None) -> str:
    """Normalize SQL identifiers for case-insensitive comparison."""
    if value is None:
        return ""
    return str(value).strip().strip('[]`"').casefold()


def _normalize_schema_for_lint(
    schema: dict[str, dict[str, list[str]]] | None,
) -> dict[str, dict[str, set[str]]]:
    """Normalize schema metadata to a table -> set(columns) map.

    Accepts both:
        {"dbo": {"Table": ["A", "B"]}}
    and:
        {"by_schema": {"dbo": {"Table": ["A", "B"]}}}
    """
    if not isinstance(schema, Mapping):
        return {}

    source = schema.get("by_schema") if isinstance(schema.get("by_schema"), Mapping) else schema

    normalized: dict[str, dict[str, set[str]]] = {}

    for schema_name, tables in source.items():
        if not isinstance(tables, Mapping):
            continue

        schema_key = _normalize_identifier(str(schema_name))
        normalized.setdefault(schema_key, {})

        for table_name, columns in tables.items():
            if not isinstance(columns, (list, tuple, set)):
                continue

            table_key = _normalize_identifier(str(table_name))
            normalized[schema_key].setdefault(table_key, set())

            for column in columns:
                if column is None:
                    continue
                normalized[schema_key][table_key].add(_normalize_identifier(str(column)))

    return normalized


def _build_schema_lint_context(
    expression: exp.Expression,
    normalized_schema: dict[str, dict[str, set[str]]],
) -> SchemaLintContext:
    """Resolve visible tables from a parsed SQL statement."""
    visible_tables: set[str] = set()
    resolved_tables: dict[str, ResolvedTable] = {}
    unresolved_tables: set[str] = set()
    known_schemas = set(normalized_schema.keys())

    for table in expression.find_all(exp.Table):
        table_name = str(table.name or "").strip()
        if not table_name:
            continue

        table_key = _normalize_identifier(table_name)
        visible_tables.add(table_key)

        schema_name = str(table.db or table.catalog or "").strip() or None
        schema_key = _normalize_identifier(schema_name) if schema_name else ""

        if schema_key:
            if schema_key not in known_schemas:
                unresolved_tables.add(table_key)
                continue

            table_columns = normalized_schema.get(schema_key, {}).get(table_key, set())
            if table_columns:
                resolved_tables[table_key] = ResolvedTable(
                    schema_name=schema_name,
                    table_name=table_name,
                    columns=table_columns,
                )
            else:
                unresolved_tables.add(table_key)
            continue

        matched_schema_name: str | None = None
        matched_columns: set[str] = set()

        for candidate_schema_name, tables in normalized_schema.items():
            candidate_columns = tables.get(table_key, set())
            if candidate_columns:
                matched_schema_name = candidate_schema_name
                matched_columns = candidate_columns
                break

        if matched_columns:
            resolved_tables[table_key] = ResolvedTable(
                schema_name=matched_schema_name,
                table_name=table_name,
                columns=matched_columns,
            )
        else:
            unresolved_tables.add(table_key)

    return SchemaLintContext(
        known_schemas=known_schemas,
        visible_tables=visible_tables,
        resolved_tables=resolved_tables,
        unresolved_tables=unresolved_tables,
    )


def _is_known_column(
    normalized_name: str,
    table_qualifier: str | None,
    context: SchemaLintContext,
) -> bool:
    """Return True if the column can be resolved in the current statement context."""
    if table_qualifier:
        resolved_table = context.resolved_tables.get(table_qualifier)
        if resolved_table is None:
            return False
        return normalized_name in resolved_table.columns

    return any(
        normalized_name in resolved_table.columns
        for resolved_table in context.resolved_tables.values()
    )


def _lint_unknown_tables(
    sql: str,
    expression: exp.Expression,
    context: SchemaLintContext,
) -> list[SqlDiagnostic]:
    """Return diagnostics for unknown schemas and tables."""
    diagnostics: list[SqlDiagnostic] = []

    for table in expression.find_all(exp.Table):
        table_name = str(table.name or "").strip()
        if not table_name:
            continue

        table_key = _normalize_identifier(table_name)
        schema_name = str(table.db or table.catalog or "").strip()
        schema_key = _normalize_identifier(schema_name) if schema_name else ""

        if schema_key and schema_key not in context.known_schemas:
            start, length = _find_identifier_span_in_sql(sql, schema_name)
            line, column = _offset_to_line_column(sql, start)

            diagnostics.append(
                SqlDiagnostic(
                    severity="error",
                    message=f"Unknown schema '{schema_name}'.",
                    line=line,
                    column=column,
                    length=max(1, length),
                )
            )
            continue

        if table_key in context.unresolved_tables:
            start, length = _find_identifier_span_in_sql(sql, table_name)
            line, column = _offset_to_line_column(sql, start)

            diagnostics.append(
                SqlDiagnostic(
                    severity="error",
                    message=f"Unknown table '{table_name}'.",
                    line=line,
                    column=column,
                    length=max(1, length),
                )
            )

    return diagnostics


def _lint_unknown_columns(
    sql: str,
    expression: exp.Expression,
    context: SchemaLintContext,
) -> list[SqlDiagnostic]:
    """Return diagnostics for unknown columns in the current statement context."""
    diagnostics: list[SqlDiagnostic] = []

    for column in expression.find_all(exp.Column):
        name = str(column.name or "").strip()
        if not name or name == "*":
            continue

        normalized_name = _normalize_identifier(name)
        table_qualifier = None
        if column.table:
            table_qualifier = _normalize_identifier(str(column.table))

        if _is_known_column(normalized_name, table_qualifier, context):
            continue

        if table_qualifier is not None:
            if table_qualifier not in context.visible_tables:
                continue
        elif not context.resolved_tables:
            continue

        start, length = _find_identifier_span_in_sql(sql, name)
        line, column_no = _offset_to_line_column(sql, start)

        diagnostics.append(
            SqlDiagnostic(
                severity="error",
                message=f"Unknown column '{name}' for the current schema context.",
                line=line,
                column=column_no,
                length=max(1, length),
            )
        )

    return diagnostics


def _lint_schema(
    sql: str,
    *,
    schema: dict[str, dict[str, list[str]]] | None,
    dialect: str | None = None,
) -> list[SqlDiagnostic]:
    """Schema-aware lint checks for schema, table, and column names."""
    if not schema:
        return []

    expression = parse_one_safe(sql, dialect)
    if expression is None:
        return []

    normalized_schema = _normalize_schema_for_lint(schema)
    if not normalized_schema:
        return []

    context = _build_schema_lint_context(expression, normalized_schema)

    diagnostics: list[SqlDiagnostic] = []
    diagnostics.extend(_lint_unknown_tables(sql, expression, context))
    diagnostics.extend(_lint_unknown_columns(sql, expression, context))
    return diagnostics


def _find_identifier_span_in_sql(
    sql: str,
    identifier: str,
    *,
    start_hint: int = 0,
) -> tuple[int, int]:
    """Return the token span for a SQL identifier.

    This avoids matching partial substrings inside longer identifiers such as
    matching Ref_Yrkesrol inside [Ref_Yrkesroll_ID].
    """
    if not isinstance(sql, str):
        return 0, 1

    text = (identifier or "").strip()
    if not text:
        return max(0, start_hint), 1

    safe_start = max(0, min(start_hint, len(sql)))

    patterns = [
        re.escape(f"[{text}]"),
        re.escape(f"`{text}`"),
        re.escape(f'"{text}"'),
        rf"(?<![A-Za-z0-9_]){re.escape(text)}(?![A-Za-z0-9_])",
    ]

    for pattern in patterns:
        match = re.search(pattern, sql[safe_start:], re.IGNORECASE)
        if match is not None:
            start = safe_start + match.start()
            length = max(1, match.end() - match.start())
            return start, length

    return max(0, safe_start), max(1, len(text))


def lint_syntax(
    sql: str,
    dialect: str | None = None,
    *,
    schema: dict[str, dict[str, list[str]]] | None = None,
) -> list[SqlDiagnostic]:
    """Lint SQL with layered checks.

    Order matters:
    1. editor-level quick checks
    2. keyword typo detection
    3. syntax parse validation
    4. schema-aware table/column checks
    """
    if not isinstance(sql, str) or not sql.strip():
        return []

    diagnostics: list[SqlDiagnostic] = []

    diagnostics.extend(lint_editor_rules(sql))
    diagnostics.extend(_lint_keyword_typos(sql))

    if any(diagnostic.severity == "error" for diagnostic in diagnostics):
        return _dedupe_diagnostics(diagnostics)

    try:
        sqlglot.parse(sql, read=sqlglot_dialect(dialect))
    except ParseError as exc:
        for error in getattr(exc, "errors", []) or []:
            message = str(error.get("description") or exc)
            line = _coerce_int_or_none(error.get("line"))
            column = _coerce_int_or_none(error.get("col"))

            diagnostics.append(
                SqlDiagnostic(
                    severity="error",
                    message=message,
                    line=line,
                    column=column,
                    length=1,
                )
            )

        if diagnostics:
            return _dedupe_diagnostics(diagnostics)

        start, length = _last_meaningful_token_span(sql)
        line, column = _offset_to_line_column(sql, start)
        diagnostics.append(
            SqlDiagnostic(
                severity="error",
                message=str(exc),
                line=line,
                column=column,
                length=length,
            )
        )
        return _dedupe_diagnostics(diagnostics)

    except SqlglotError as exc:
        diagnostics.append(
            SqlDiagnostic(
                severity="error",
                message=str(exc),
                length=1,
            )
        )
        return _dedupe_diagnostics(diagnostics)

    diagnostics.extend(_lint_schema(sql, schema=schema, dialect=dialect))
    return _dedupe_diagnostics(diagnostics)


def detect_statement_kind(sql: str, dialect: str | None = None) -> SqlStatementKind:
    """Detect the broad kind of a SQL statement.

    This uses sqlglot when possible and falls back to lightweight textual checks
    for statements that may not parse cleanly in every dialect, especially EXEC.
    """
    if not isinstance(sql, str) or not sql.strip():
        return "empty"

    leading_token = _first_meaningful_token(sql)

    if leading_token in {"exec", "execute"}:
        return "exec"

    expression = parse_one_safe(sql, dialect)
    if expression is None:
        return _fallback_statement_kind(leading_token, invalid=True)

    if isinstance(expression, exp.Select):
        return "select"

    if isinstance(expression, exp.Union | exp.Intersect | exp.Except):
        return "select"

    if isinstance(expression, exp.Insert):
        return "insert"

    if isinstance(expression, exp.Update):
        return "update"

    if isinstance(expression, exp.Delete):
        return "delete"

    if isinstance(expression, exp.Create):
        return "create"

    if isinstance(expression, exp.Drop):
        return "drop"

    if isinstance(expression, exp.Alter):
        return "alter"

    if isinstance(expression, exp.Command):
        command_name = str(expression.this or "").strip().lower()
        if command_name in {"truncate", "exec", "execute"}:
            return "truncate" if command_name == "truncate" else "exec"

    if leading_token == "with":  # noqa S105
        return "with"

    return _fallback_statement_kind(leading_token, invalid=False)


def extract_table_refs(sql: str, dialect: str | None = None) -> list[TableRef]:
    """Extract table references and aliases from SQL."""
    expressions = parse_many_safe(sql, dialect)
    refs: list[TableRef] = []

    for expression in expressions:
        for table in expression.find_all(exp.Table):
            name = table.name
            if not name:
                continue

            db_arg = table.args.get("db")
            catalog_arg = table.args.get("catalog")
            alias = table.alias

            refs.append(
                TableRef(
                    name=name,
                    schema=_expression_name_or_none(db_arg),
                    catalog=_expression_name_or_none(catalog_arg),
                    alias=alias or None,
                )
            )

    return refs


def extract_column_refs(sql: str, dialect: str | None = None) -> list[ColumnRef]:
    """Extract column references from SQL."""
    expressions = parse_many_safe(sql, dialect)
    refs: list[ColumnRef] = []

    for expression in expressions:
        for column in expression.find_all(exp.Column):
            name = column.name
            if not name:
                continue

            refs.append(
                ColumnRef(
                    name=name,
                    table=column.table or None,
                    schema=column.db or None,
                    catalog=column.catalog or None,
                )
            )

    return refs


def extract_table_aliases(sql: str, dialect: str | None = None) -> dict[str, TableRef]:
    """Return a mapping of visible table alias/name to table reference."""
    aliases: dict[str, TableRef] = {}

    for ref in extract_table_refs(sql, dialect):
        key = ref.alias or ref.name
        if key:
            aliases[key] = ref

    return aliases


def format_sql(
    sql: str,
    dialect: str | None = None,
    *,
    pretty: bool = True,
) -> str:
    """Format SQL using sqlglot."""
    if not isinstance(sql, str) or not sql.strip():
        return sql

    resolved_dialect = sqlglot_dialect(dialect)

    try:
        statements = sqlglot.transpile(
            sql,
            read=resolved_dialect,
            write=resolved_dialect,
            pretty=pretty,
        )
    except SqlglotError:
        return sql

    if not statements:
        return sql

    return ";\n\n".join(statements)


def is_select_like(sql: str, dialect: str | None = None) -> bool:
    """Return True if SQL appears to be a SELECT/WITH query."""
    return detect_statement_kind(sql, dialect) in {"select", "with"}


def has_multiple_statements(sql: str, dialect: str | None = None) -> bool:
    """Return True if SQL text parses as more than one statement."""
    return len(parse_many_safe(sql, dialect)) > 1


# noinspection PyBroadException
def _coerce_int_or_none(value: object) -> int | None:
    """Best-effort conversion of a value to int or None."""
    if value is None:
        return None

    if isinstance(value, int):
        return value

    if isinstance(value, float | str | bytes | bytearray):
        try:
            return int(value)
        except (
            AttributeError,
            ConnectionError,
            FileNotFoundError,
            IndexError,
            KeyError,
            LookupError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ):
            return None

    return None


def _expression_name_or_none(value: object) -> str | None:
    """Return a readable expression name or None."""
    if value is None:
        return None

    if isinstance(value, str):
        return value or None

    if isinstance(value, exp.Identifier):
        name = value.name
        return name if isinstance(name, str) and name else None

    if isinstance(value, exp.Expression):
        name = getattr(value, "name", None)
        if isinstance(name, str) and name:
            return name

        text = value.sql()
        if isinstance(text, str) and text:
            return text

    return None


def _first_meaningful_token(sql: str | None) -> str:
    """Return the first meaningful token after leading comments/whitespace."""
    text = _strip_leading_comments_and_whitespace(sql)
    token_chars: list[str] = []

    for char in text:
        if char.isalnum() or char == "_":
            token_chars.append(char)
            continue
        break

    return "".join(token_chars).lower()


# noinspection PyTypeChecker
def _strip_leading_comments_and_whitespace(sql: str | None) -> str:
    """Strip leading whitespace and SQL comments.

    Handles common line comments and block comments well enough for statement
    classification fallback.
    """
    if not isinstance(sql, str):
        return ""

    text = sql

    while True:
        stripped = text.lstrip()

        if stripped.startswith("--"):
            newline_index = stripped.find("\n")
            if newline_index < 0:
                return ""
            text = stripped[newline_index + 1 :]
            continue

        if stripped.startswith("/*"):
            end_index = stripped.find("*/")
            if end_index < 0:
                return ""
            text = stripped[end_index + 2 :]
            continue

        return stripped


def _find_unmatched_square_bracket(sql: str) -> int | None:
    """Return offset of an unmatched SQL Server-style '[' bracket.

    Ignores brackets inside single-quoted string literals.
    """
    stack: list[int] = []
    in_single_quote = False
    i = 0

    while i < len(sql):
        char = sql[i]

        if char == "'":
            if in_single_quote and i + 1 < len(sql) and sql[i + 1] == "'":
                i += 2
                continue

            in_single_quote = not in_single_quote
            i += 1
            continue

        if in_single_quote:
            i += 1
            continue

        if char == "[":
            stack.append(i)
            i += 1
            continue

        if char == "]":
            if stack:
                stack.pop()
            i += 1
            continue

        i += 1

    if not stack:
        return None

    return stack[-1]


def _identifier_like_span_from_offset(sql: str, offset: int) -> tuple[int, int]:
    """Return a useful underline span starting at offset."""
    if offset < 0 or offset >= len(sql):
        return max(0, min(offset, len(sql))), 1

    end = offset + 1
    while end < len(sql) and sql[end] not in " \t\r\n,;()":
        end += 1

    return offset, max(1, end - offset)


_ADJACENT_BRACKET_IDENTIFIERS_RE = re.compile(r"(?is)(\[[^\]]+\])\s+(\[[^\]]+\])")


def _find_suspicious_adjacent_select_identifier(sql: str) -> tuple[int, int] | None:
    """Find suspicious adjacent bracket identifiers in a SELECT list.

    This catches cases like:
        SELECT [Column1]
               [Column2]
    which is often a missing comma.
    """
    select_match = re.search(r"(?is)\bselect\b", sql)
    from_match = re.search(r"(?is)\bfrom\b", sql)

    if select_match is None or from_match is None or from_match.start() <= select_match.end():
        return None

    select_list = sql[select_match.end() : from_match.start()]
    match = _ADJACENT_BRACKET_IDENTIFIERS_RE.search(select_list)
    if match is None:
        return None

    start = select_match.end() + match.start(2)
    length = max(1, match.end(2) - match.start(2))
    return start, length


def _last_meaningful_token_span(sql: str) -> tuple[int, int]:
    """Return span for the last meaningful token in SQL text."""
    last_match = None
    for match in re.finditer(r"[A-Za-z_][A-Za-z0-9_]*|\[[^\]]*$|\[[^\]]+\]|`[^`]*$|`[^`]+`|\"[^\"]*$|\"[^\"]+\"", sql):
        last_match = match

    if last_match is None:
        return 0, 1

    return last_match.start(), max(1, last_match.end() - last_match.start())


def _fallback_statement_kind(
    leading_token: str,
    *,
    invalid: bool,
) -> SqlStatementKind:
    """Classify SQL from a leading token when AST classification is unavailable."""
    if leading_token in {"select"}:
        return "select"

    if leading_token in {"with"}:
        return "with"

    if leading_token in {"exec", "execute"}:
        return "exec"

    if leading_token in {"insert"}:
        return "insert"

    if leading_token in {"update"}:
        return "update"

    if leading_token in {"delete"}:
        return "delete"

    if leading_token in {"create"}:
        return "create"

    if leading_token in {"drop"}:
        return "drop"

    if leading_token in {"alter"}:
        return "alter"

    if leading_token in {"truncate"}:
        return "truncate"

    if invalid:
        return "invalid"

    return "other"
