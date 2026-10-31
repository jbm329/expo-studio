"""Qt-free identifier formatting and source spans for SQL completion."""

from __future__ import annotations

from dataclasses import dataclass

from expo_jbm329.db.dialects import (
    AnsiDialect,
    DuckDbDialect,
    MssqlDialect,
    MySqlDialect,
    PostgresDialect,
    SqliteDialect,
)
from expo_jbm329.db.sql_analysis import sqlglot_dialect

_IDENTIFIER_QUOTES = {"[": "]", '"': '"', "`": "`"}
_TOKEN_SEPARATORS = frozenset(" \r\n\t.,();+-*/%=<>!|&^~:'\"`[]")


@dataclass(frozen=True)
class IdentifierCompletion:
    """Source context for completing one identifier.

    Attributes:
        prefix: Original qualified text up to the cursor, including delimiters.
        start: Start of the active identifier, including its opening delimiter.
        end: End of the active identifier, including any suffix and closing delimiter.

    Offsets are Python string indices, not Qt UTF-16 cursor positions.
    """

    prefix: str
    start: int
    end: int


def quote_identifier(name: str, dialect: str | None = None) -> str:
    """Quote a raw metadata name without interpreting its literal characters.

    Args:
        name: Exact schema, table or column name from metadata.
        dialect: Engine or sqlglot dialect name. Missing or unregistered dialects
            use the application's ANSI double-quote formatting fallback.

    Returns:
        Unconditionally quoted name with embedded closing delimiters escaped.
    """
    match sqlglot_dialect(dialect):
        case "tsql":
            return MssqlDialect().quote_ident(name)
        case "mysql":
            return MySqlDialect().quote_ident(name)
        case "postgres":
            return PostgresDialect().quote_ident(name)
        case "sqlite":
            return SqliteDialect().quote_ident(name)
        case "duckdb":
            return DuckDbDialect().quote_ident(name)
        case _:
            return AnsiDialect().quote_ident(name)


def _quoted_end(text: str, start: int, close: str) -> tuple[int, bool]:
    """Return the end of a quoted token and whether its delimiter was closed."""
    pos = start + 1
    while pos < len(text):
        if text[pos] == close:
            if pos + 1 < len(text) and text[pos + 1] == close:
                pos += 2
                continue
            return pos + 1, True
        pos += 1
    return len(text), False


def identifier_lookup_name(source: str) -> str:
    """Decode one complete or unfinished identifier from editor text.

    Args:
        source: One identifier component, not a raw metadata name.

    Returns:
        Unquoted lookup name, preserving spaces and literal delimiters within it.
    """
    text = source.lstrip()
    if not text or text[0] not in _IDENTIFIER_QUOTES:
        return text.strip()
    close = _IDENTIFIER_QUOTES[text[0]]
    end, closed = _quoted_end(text, 0, close)
    inner = text[1 : end - 1] if closed else text[1:]
    return inner.replace(close * 2, close)


def split_identifier_prefix(prefix: str) -> tuple[str, ...]:
    """Split qualified source text only at dots outside identifier delimiters.

    Args:
        prefix: Complete or unfinished qualified identifier text.

    Returns:
        Original source components, including their delimiters. A trailing
        qualification dot produces an empty final component.
    """
    parts: list[str] = []
    start = pos = 0
    while pos < len(prefix):
        char = prefix[pos]
        if char in _IDENTIFIER_QUOTES:
            pos, _ = _quoted_end(prefix, pos, _IDENTIFIER_QUOTES[char])
        elif char == ".":
            parts.append(prefix[start:pos])
            pos += 1
            start = pos
        else:
            pos += 1
    parts.append(prefix[start:])
    return tuple(parts)


def identifier_completion(sql: str, cursor_pos: int) -> IdentifierCompletion | None:
    """Find the qualified prefix and replacement span at a Python cursor index.

    Args:
        sql: Full editor text.
        cursor_pos: Python string index of the cursor.

    Returns:
        Completion context, including an empty span at a token boundary, or
        None when the cursor is inside a string literal or comment.

    Raises:
        ValueError: If the cursor index is outside the editor text.
    """
    if not 0 <= cursor_pos <= len(sql):
        msg = "Completion cursor index is outside the SQL text."
        raise ValueError(msg)

    pos = chain_start = component_start = 0
    while pos < cursor_pos:
        char = sql[pos]
        if sql.startswith("--", pos):
            end = sql.find("\n", pos + 2)
            end = len(sql) if end == -1 else end
            if cursor_pos <= end:
                return None
            pos = chain_start = component_start = end
        elif sql.startswith("/*", pos):
            end = sql.find("*/", pos + 2)
            end = len(sql) if end == -1 else end + 2
            if cursor_pos <= end:
                return None
            pos = chain_start = component_start = end
        elif char == "'":
            end, _ = _quoted_end(sql, pos, "'")
            if cursor_pos <= end:
                return None
            pos = chain_start = component_start = end
        elif char == ".":
            pos += 1
            component_start = pos
        elif char in _IDENTIFIER_QUOTES or (not char.isspace() and char not in _TOKEN_SEPARATORS):
            if char in _IDENTIFIER_QUOTES:
                end, _ = _quoted_end(sql, pos, _IDENTIFIER_QUOTES[char])
            else:
                end = pos + 1
                while end < len(sql) and not sql[end].isspace() and sql[end] not in _TOKEN_SEPARATORS:
                    end += 1
            if cursor_pos <= end:
                return IdentifierCompletion(sql[chain_start:cursor_pos], component_start, end)
            pos = end
        else:
            pos += 1
            chain_start = component_start = pos

    return IdentifierCompletion(sql[chain_start:cursor_pos], component_start, cursor_pos)
