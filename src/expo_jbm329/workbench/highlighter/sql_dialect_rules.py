"""Dialect-specific lexical rules for SQL syntax highlighting.

The rules describe which words are keywords/functions and how identifiers,
strings and comments are delimited for a given sqlglot dialect name. The module
has no Qt dependencies so it can be unit tested in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache

BASE_KEYWORDS: frozenset[str] = frozenset({
    "ALL",
    "ALTER",
    "AND",
    "AS",
    "ASC",
    "BEGIN",
    "BETWEEN",
    "BY",
    "CASE",
    "CAST",
    "COMMIT",
    "CONSTRAINT",
    "CREATE",
    "CROSS",
    "CURRENT",
    "DEFAULT",
    "DELETE",
    "DESC",
    "DISTINCT",
    "DROP",
    "ELSE",
    "END",
    "EXCEPT",
    "EXISTS",
    "FALSE",
    "FETCH",
    "FIRST",
    "FOLLOWING",
    "FOREIGN",
    "FROM",
    "FULL",
    "GROUP",
    "HAVING",
    "IF",
    "IN",
    "INDEX",
    "INNER",
    "INSERT",
    "INTERSECT",
    "INTO",
    "IS",
    "JOIN",
    "KEY",
    "LEFT",
    "LIKE",
    "MATERIALIZED",
    "MERGE",
    "NEXT",
    "NOT",
    "NULL",
    "NULLS",
    "OFFSET",
    "ON",
    "ONLY",
    "OR",
    "ORDER",
    "OUTER",
    "OVER",
    "PARTITION",
    "PRECEDING",
    "PRIMARY",
    "RANGE",
    "RECURSIVE",
    "REFERENCES",
    "RIGHT",
    "ROLLBACK",
    "ROW",
    "ROWS",
    "SELECT",
    "SET",
    "TABLE",
    "THEN",
    "TRUE",
    "TRUNCATE",
    "UNBOUNDED",
    "UNION",
    "UNIQUE",
    "UPDATE",
    "USING",
    "VALUES",
    "VIEW",
    "WHEN",
    "WHERE",
    "WINDOW",
    "WITH",
})

BASE_FUNCTIONS: frozenset[str] = frozenset({
    "ABS",
    "AVG",
    "CAST",
    "CEILING",
    "COALESCE",
    "COUNT",
    "CURRENT_DATE",
    "CURRENT_TIMESTAMP",
    "DENSE_RANK",
    "FLOOR",
    "LAG",
    "LEAD",
    "LEFT",
    "LENGTH",
    "LOWER",
    "LTRIM",
    "MAX",
    "MIN",
    "NULLIF",
    "POWER",
    "RANK",
    "REPLACE",
    "RIGHT",
    "ROUND",
    "ROW_NUMBER",
    "RTRIM",
    "SUBSTRING",
    "SUM",
    "TRIM",
    "UPPER",
})

_DIALECT_KEYWORDS: dict[str, frozenset[str]] = {
    "tsql": frozenset({
        "APPLY",
        "DECLARE",
        "EXEC",
        "EXECUTE",
        "GO",
        "NOLOCK",
        "OUTPUT",
        "PERCENT",
        "PIVOT",
        "PROCEDURE",
        "TOP",
        "UNPIVOT",
    }),
    "mysql": frozenset({
        "AUTO_INCREMENT",
        "DUPLICATE",
        "ENGINE",
        "IGNORE",
        "LIMIT",
        "REGEXP",
        "REPLACE",
        "SHOW",
    }),
    "sqlite": frozenset({
        "AUTOINCREMENT",
        "GLOB",
        "LIMIT",
        "PRAGMA",
        "REPLACE",
        "RETURNING",
        "VACUUM",
        "WITHOUT",
    }),
    "postgres": frozenset({
        "ILIKE",
        "LATERAL",
        "LIMIT",
        "RETURNING",
        "SIMILAR",
    }),
    "oracle": frozenset({
        "CONNECT",
        "MINUS",
        "PRIOR",
        "ROWNUM",
        "START",
        "SYSDATE",
    }),
}

_DIALECT_FUNCTIONS: dict[str, frozenset[str]] = {
    "tsql": frozenset({
        "CHARINDEX",
        "CONVERT",
        "DATEADD",
        "DATEDIFF",
        "DATENAME",
        "DATEPART",
        "FORMAT",
        "GETDATE",
        "IIF",
        "ISNULL",
        "LEN",
        "NEWID",
        "STRING_AGG",
        "SYSDATETIME",
        "TRY_CAST",
        "TRY_CONVERT",
    }),
    "mysql": frozenset({
        "CONCAT",
        "CONCAT_WS",
        "DATE_ADD",
        "DATE_FORMAT",
        "DATE_SUB",
        "DATEDIFF",
        "GROUP_CONCAT",
        "IF",
        "IFNULL",
        "NOW",
        "STR_TO_DATE",
    }),
    "sqlite": frozenset({
        "DATE",
        "DATETIME",
        "GROUP_CONCAT",
        "IFNULL",
        "IIF",
        "INSTR",
        "JULIANDAY",
        "PRINTF",
        "STRFTIME",
        "SUBSTR",
        "TIME",
    }),
    "postgres": frozenset({
        "AGE",
        "ARRAY_AGG",
        "CONCAT",
        "DATE_PART",
        "DATE_TRUNC",
        "NOW",
        "STRING_AGG",
        "TO_CHAR",
        "TO_DATE",
    }),
    "oracle": frozenset({
        "DECODE",
        "INSTR",
        "LISTAGG",
        "NVL",
        "NVL2",
        "SUBSTR",
        "TO_CHAR",
        "TO_DATE",
        "TRUNC",
    }),
}

BRACKET_QUOTE = ("[", "]")
DOUBLE_QUOTE = ('"', '"')
BACKTICK_QUOTE = ("`", "`")


@dataclass(frozen=True)
class SqlDialectRules:
    """Lexical rules used by the SQL highlighter tokenizer.

    Attributes:
        name: Dialect name (sqlglot naming) or "generic".
        keywords: Upper-case keywords.
        functions: Upper-case function names (highlighted when followed by "(").
        identifier_quotes: (open, close) delimiter pairs for quoted identifiers.
        string_quotes: Characters starting string literals.
        line_comment_prefixes: Prefixes starting a comment running to end of line.
        backslash_escapes: Whether a backslash escapes the next character in strings.
    """

    name: str
    keywords: frozenset[str]
    functions: frozenset[str]
    identifier_quotes: tuple[tuple[str, str], ...]
    string_quotes: tuple[str, ...] = ("'",)
    line_comment_prefixes: tuple[str, ...] = ("--",)
    backslash_escapes: bool = False


def _rules(
    name: str,
    *,
    identifier_quotes: tuple[tuple[str, str], ...],
    string_quotes: tuple[str, ...] = ("'",),
    line_comment_prefixes: tuple[str, ...] = ("--",),
    backslash_escapes: bool = False,
) -> SqlDialectRules:
    """Build rules for one dialect from base and dialect-specific word lists."""
    return SqlDialectRules(
        name=name,
        keywords=BASE_KEYWORDS | _DIALECT_KEYWORDS[name],
        functions=BASE_FUNCTIONS | _DIALECT_FUNCTIONS[name],
        identifier_quotes=identifier_quotes,
        string_quotes=string_quotes,
        line_comment_prefixes=line_comment_prefixes,
        backslash_escapes=backslash_escapes,
    )


@cache
def rules_for_dialect(dialect: str | None) -> SqlDialectRules:
    """Return highlighting rules for a sqlglot dialect name.

    Unknown dialects and None return generic rules combining all known
    dialect keywords and functions, so nothing is lost when no connection is
    bound to the editor.

    Args:
        dialect: sqlglot dialect name such as "tsql", "mysql", "sqlite",
            "postgres" or "oracle", or None.

    Returns:
        The lexical rules for the dialect.
    """
    match (dialect or "").lower():
        case "tsql":
            return _rules("tsql", identifier_quotes=(BRACKET_QUOTE, DOUBLE_QUOTE))
        case "mysql":
            # Without ANSI_QUOTES MySQL treats double quotes as string delimiters.
            return _rules(
                "mysql",
                identifier_quotes=(BACKTICK_QUOTE,),
                string_quotes=("'", '"'),
                line_comment_prefixes=("--", "#"),
                backslash_escapes=True,
            )
        case "sqlite":
            return _rules("sqlite", identifier_quotes=(DOUBLE_QUOTE, BRACKET_QUOTE, BACKTICK_QUOTE))
        case "postgres":
            return _rules("postgres", identifier_quotes=(DOUBLE_QUOTE,))
        case "oracle":
            return _rules("oracle", identifier_quotes=(DOUBLE_QUOTE,))
        case _:
            return SqlDialectRules(
                name="generic",
                keywords=BASE_KEYWORDS.union(*_DIALECT_KEYWORDS.values()),
                functions=BASE_FUNCTIONS.union(*_DIALECT_FUNCTIONS.values()),
                identifier_quotes=(BRACKET_QUOTE, DOUBLE_QUOTE, BACKTICK_QUOTE),
            )
