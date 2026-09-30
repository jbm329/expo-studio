"""Single-pass SQL tokenizer used for syntax highlighting.

The tokenizer scans one text block (line) from left to right. Comments,
strings and quoted identifiers are consumed as a whole, so keywords are never
detected inside them. Multi-line block comments and strings are supported via
an integer block state compatible with ``QSyntaxHighlighter`` block states.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from expo_jbm329.workbench.highlighter.sql_dialect_rules import SqlDialectRules

STATE_NONE = 0
STATE_IN_BLOCK_COMMENT = 1
STATE_IN_STRING = 2
STATE_IN_DOUBLE_QUOTED_STRING = 3

_STRING_STATE_BY_QUOTE: dict[str, int] = {"'": STATE_IN_STRING, '"': STATE_IN_DOUBLE_QUOTED_STRING}
_QUOTE_BY_STRING_STATE: dict[int, str] = {state: quote for quote, state in _STRING_STATE_BY_QUOTE.items()}

_OPERATOR_CHARS = frozenset("+-*/%=<>!,;().:|&^~")
_WORD_START_EXTRA = frozenset("_@#")
_WORD_PART_EXTRA = frozenset("_@#$")


class TokenKind(StrEnum):
    """Kinds of highlightable SQL tokens."""

    KEYWORD = "keyword"
    FUNCTION = "function"
    IDENTIFIER = "identifier"
    QUOTED_IDENTIFIER = "quoted_identifier"
    STRING = "string"
    NUMBER = "number"
    OPERATOR = "operator"
    COMMENT = "comment"


@dataclass(frozen=True)
class SqlToken:
    """A token in a single text block.

    Attributes:
        kind: Token kind.
        start: Start offset within the block.
        length: Token length in characters.
        name: Unquoted identifier name for identifier tokens, otherwise the raw text.
        quote: Opening quote character for quoted identifiers, otherwise "".
        qualified: True if the token directly follows a "." (e.g. ``t.col``).
        qualifier: True if the token is directly followed by a "." (e.g. ``schema.``).
    """

    kind: TokenKind
    start: int
    length: int
    name: str = ""
    quote: str = ""
    qualified: bool = False
    qualifier: bool = False


def _is_word_start(ch: str) -> bool:
    return ch.isalpha() or ch in _WORD_START_EXTRA


def _is_word_part(ch: str) -> bool:
    return ch.isalnum() or ch in _WORD_PART_EXTRA


def _next_non_space(text: str, pos: int) -> str:
    n = len(text)
    while pos < n and text[pos].isspace():
        pos += 1
    return text[pos] if pos < n else ""


def _find_string_end(text: str, start: int, quote: str, *, backslash_escapes: bool) -> int | None:
    """Return the index of the closing quote, handling doubled quotes and escapes."""
    i = start
    n = len(text)
    while i < n:
        ch = text[i]
        if backslash_escapes and ch == "\\":
            i += 2
            continue
        if ch == quote:
            if i + 1 < n and text[i + 1] == quote:
                i += 2
                continue
            return i
        i += 1
    return None


def _find_quoted_identifier_end(text: str, start: int, close: str) -> int | None:
    """Return the index of the closing delimiter; a doubled delimiter is an escape."""
    i = start
    n = len(text)
    while i < n:
        if text[i] == close:
            if i + 1 < n and text[i + 1] == close:
                i += 2
                continue
            return i
        i += 1
    return None


def _scan_number(text: str, pos: int) -> int:
    """Return the end index of a numeric literal starting at pos."""
    n = len(text)
    i = pos
    while i < n and text[i].isdigit():
        i += 1
    if i + 1 < n and text[i] == "." and text[i + 1].isdigit():
        i += 1
        while i < n and text[i].isdigit():
            i += 1
    if i < n and text[i] in "eE":
        j = i + 1
        if j < n and text[j] in "+-":
            j += 1
        if j < n and text[j].isdigit():
            i = j
            while i < n and text[i].isdigit():
                i += 1
    return i


def tokenize_line(
    text: str,
    rules: SqlDialectRules,
    start_state: int = STATE_NONE,
) -> tuple[list[SqlToken], int]:
    """Tokenize one text block.

    Args:
        text: The block text (a single line without newline).
        rules: Dialect rules controlling keywords, quotes and comments.
        start_state: Block state carried over from the previous block.

    Returns:
        A tuple of (tokens, end_state). ``end_state`` is non-zero when a block
        comment or string continues into the next block.
    """
    tokens: list[SqlToken] = []
    n = len(text)
    pos = 0

    # ---- Continue a multi-line construct from the previous block -----------
    if start_state == STATE_IN_BLOCK_COMMENT:
        end = text.find("*/")
        if end < 0:
            if n:
                tokens.append(SqlToken(TokenKind.COMMENT, 0, n))
            return tokens, STATE_IN_BLOCK_COMMENT
        pos = end + 2
        tokens.append(SqlToken(TokenKind.COMMENT, 0, pos))
    elif start_state in _QUOTE_BY_STRING_STATE:
        quote = _QUOTE_BY_STRING_STATE[start_state]
        end_idx = _find_string_end(text, 0, quote, backslash_escapes=rules.backslash_escapes)
        if end_idx is None:
            if n:
                tokens.append(SqlToken(TokenKind.STRING, 0, n))
            return tokens, start_state
        pos = end_idx + 1
        tokens.append(SqlToken(TokenKind.STRING, 0, pos))

    identifier_close = dict(rules.identifier_quotes)
    after_dot = False

    while pos < n:
        ch = text[pos]

        if ch.isspace():
            pos += 1
            continue

        # ---- Comments ------------------------------------------------------
        if any(text.startswith(prefix, pos) for prefix in rules.line_comment_prefixes):
            tokens.append(SqlToken(TokenKind.COMMENT, pos, n - pos))
            return tokens, STATE_NONE

        if text.startswith("/*", pos):
            end = text.find("*/", pos + 2)
            if end < 0:
                tokens.append(SqlToken(TokenKind.COMMENT, pos, n - pos))
                return tokens, STATE_IN_BLOCK_COMMENT
            tokens.append(SqlToken(TokenKind.COMMENT, pos, end + 2 - pos))
            pos = end + 2
            after_dot = False
            continue

        # ---- Strings -------------------------------------------------------
        if ch in rules.string_quotes:
            end_idx = _find_string_end(text, pos + 1, ch, backslash_escapes=rules.backslash_escapes)
            if end_idx is None:
                tokens.append(SqlToken(TokenKind.STRING, pos, n - pos))
                return tokens, _STRING_STATE_BY_QUOTE.get(ch, STATE_IN_STRING)
            tokens.append(SqlToken(TokenKind.STRING, pos, end_idx + 1 - pos))
            pos = end_idx + 1
            after_dot = False
            continue

        # ---- Quoted identifiers -------------------------------------------
        close = identifier_close.get(ch)
        if close is not None:
            end_idx = _find_quoted_identifier_end(text, pos + 1, close)
            end = n if end_idx is None else end_idx + 1
            inner = text[pos + 1 : end_idx if end_idx is not None else n]
            tokens.append(
                SqlToken(
                    TokenKind.QUOTED_IDENTIFIER,
                    pos,
                    end - pos,
                    name=inner.replace(close + close, close),
                    quote=ch,
                    qualified=after_dot,
                    qualifier=_next_non_space(text, end) == ".",
                )
            )
            pos = end
            after_dot = False
            continue

        # ---- Numbers ---------------------------------------------------------
        if ch.isdigit():
            end = _scan_number(text, pos)
            if end < n and _is_word_part(text[end]):
                # Identifier starting with digits (e.g. 1abc) -> treat as word.
                while end < n and _is_word_part(text[end]):
                    end += 1
                tokens.append(SqlToken(TokenKind.IDENTIFIER, pos, end - pos, name=text[pos:end]))
            else:
                tokens.append(SqlToken(TokenKind.NUMBER, pos, end - pos, name=text[pos:end]))
            pos = end
            after_dot = False
            continue

        # ---- Words -----------------------------------------------------------
        if _is_word_start(ch):
            end = pos + 1
            while end < n and _is_word_part(text[end]):
                end += 1
            word = text[pos:end]
            upper = word.upper()
            next_char = _next_non_space(text, end)

            if after_dot:
                # Qualified parts (schema.table.column) are never keywords.
                kind = TokenKind.IDENTIFIER
            elif next_char == "(" and upper in rules.functions:
                kind = TokenKind.FUNCTION
            elif upper in rules.keywords:
                kind = TokenKind.KEYWORD
            else:
                kind = TokenKind.IDENTIFIER

            tokens.append(
                SqlToken(
                    kind,
                    pos,
                    end - pos,
                    name=word,
                    qualified=after_dot,
                    qualifier=next_char == ".",
                )
            )
            pos = end
            after_dot = False
            continue

        # ---- Operators / punctuation ----------------------------------------
        if ch in _OPERATOR_CHARS:
            tokens.append(SqlToken(TokenKind.OPERATOR, pos, 1, name=ch))
            after_dot = ch == "."
            pos += 1
            continue

        pos += 1
        after_dot = False

    return tokens, STATE_NONE
