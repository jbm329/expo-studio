from __future__ import annotations

import pytest

from expo_jbm329.workbench.highlighter.sql_dialect_rules import rules_for_dialect
from expo_jbm329.workbench.highlighter.sql_tokenizer import (
    STATE_IN_BLOCK_COMMENT,
    STATE_IN_DOUBLE_QUOTED_STRING,
    STATE_IN_STRING,
    STATE_NONE,
    SqlToken,
    TokenKind,
    tokenize_line,
)


def _kinds(text: str, dialect: str | None = None) -> list[tuple[TokenKind, str]]:
    tokens, _ = tokenize_line(text, rules_for_dialect(dialect))
    return [(t.kind, text[t.start : t.start + t.length]) for t in tokens]


def _token_at(text: str, fragment: str, dialect: str | None = None) -> SqlToken:
    tokens, _ = tokenize_line(text, rules_for_dialect(dialect))
    start = text.index(fragment)
    return next(t for t in tokens if t.start == start)


@pytest.mark.parametrize(
    ("dialect", "quoted"),
    [("sqlite", '"Order"'), ("tsql", "[Order]"), ("mysql", "`Order`"), (None, '"Table"')],
)
def test_quoted_keywords_are_identifiers(dialect: str | None, quoted: str) -> None:
    text = f"SELECT * FROM {quoted}"
    token = _token_at(text, quoted, dialect)
    assert token.kind == TokenKind.QUOTED_IDENTIFIER
    assert token.length == len(quoted)
    assert token.name == quoted[1:-1]
    assert (TokenKind.KEYWORD, "Order") not in _kinds(text, dialect)


def test_keywords_not_detected_inside_strings_or_comments() -> None:
    kinds = _kinds("SELECT 'from where' /* select */ -- order by")
    assert kinds == [
        (TokenKind.KEYWORD, "SELECT"),
        (TokenKind.STRING, "'from where'"),
        (TokenKind.COMMENT, "/* select */"),
        (TokenKind.COMMENT, "-- order by"),
    ]


def test_double_dash_inside_string_is_not_a_comment() -> None:
    kinds = _kinds("SELECT '--x' FROM t")
    assert (TokenKind.STRING, "'--x'") in kinds
    assert (TokenKind.KEYWORD, "FROM") in kinds


def test_apostrophe_inside_quoted_identifier_does_not_start_string() -> None:
    tokens, state = tokenize_line('SELECT "it\'s" FROM t', rules_for_dialect("sqlite"))
    assert state == STATE_NONE
    assert tokens[1].kind == TokenKind.QUOTED_IDENTIFIER
    assert tokens[1].name == "it's"
    assert tokens[2].kind == TokenKind.KEYWORD


def test_doubled_delimiters_are_escapes() -> None:
    assert _token_at('SELECT "a""b"', '"a""b"').name == 'a"b'
    assert _token_at("SELECT [a]]b]", "[a]]b]", "tsql").name == "a]b"


def test_word_after_dot_is_not_keyword() -> None:
    text = "SELECT a.left, a.order FROM t a"
    assert _token_at(text, "left").kind == TokenKind.IDENTIFIER
    assert _token_at(text, "left").qualified is True
    assert _token_at(text, "order").kind == TokenKind.IDENTIFIER


def test_qualifier_flag_marks_part_before_dot() -> None:
    text = '"main"."Customers"'
    assert _token_at(text, '"main"', "sqlite").qualifier is True
    assert _token_at(text, '"Customers"', "sqlite").qualified is True
    assert _token_at(text, '"Customers"', "sqlite").qualifier is False


def test_limit_and_offset_are_keywords() -> None:
    kinds = _kinds("SELECT * FROM t LIMIT 10 OFFSET 5", "sqlite")
    assert (TokenKind.KEYWORD, "LIMIT") in kinds
    assert (TokenKind.KEYWORD, "OFFSET") in kinds


def test_function_requires_parenthesis() -> None:
    assert _token_at("SELECT COUNT (*)", "COUNT").kind == TokenKind.FUNCTION
    assert _token_at("SELECT count FROM t", "count").kind == TokenKind.IDENTIFIER
    assert _token_at("SELECT LEFT(x, 1)", "LEFT").kind == TokenKind.FUNCTION
    assert _token_at("FROM a LEFT JOIN b", "LEFT").kind == TokenKind.KEYWORD


def test_top_is_keyword_for_tsql_but_not_sqlite() -> None:
    assert _token_at("SELECT TOP 10 *", "TOP", "tsql").kind == TokenKind.KEYWORD
    assert _token_at("SELECT TOP 10 *", "TOP", "sqlite").kind == TokenKind.IDENTIFIER


def test_mysql_hash_comment_and_double_quoted_string() -> None:
    kinds = _kinds('SELECT "from" # comment', "mysql")
    assert kinds == [
        (TokenKind.KEYWORD, "SELECT"),
        (TokenKind.STRING, '"from"'),
        (TokenKind.COMMENT, "# comment"),
    ]


def test_mysql_backslash_escape_in_string() -> None:
    tokens, state = tokenize_line(r"SELECT 'a\'b' FROM t", rules_for_dialect("mysql"))
    assert state == STATE_NONE
    assert tokens[1].kind == TokenKind.STRING
    assert tokens[1].length == len(r"'a\'b'")
    assert tokens[2].kind == TokenKind.KEYWORD


def test_backslash_is_literal_in_standard_sql() -> None:
    tokens, state = tokenize_line(r"SELECT 'C:\' FROM t", rules_for_dialect("tsql"))
    assert state == STATE_NONE
    assert tokens[1].length == len(r"'C:\'")


def test_tsql_variables_and_temp_tables_are_identifiers() -> None:
    kinds = _kinds("SELECT @x FROM #tmp", "tsql")
    assert (TokenKind.IDENTIFIER, "@x") in kinds
    assert (TokenKind.IDENTIFIER, "#tmp") in kinds


def test_numbers() -> None:
    kinds = _kinds("SELECT 1, 2.5, 1e10, abc1")
    assert (TokenKind.NUMBER, "1") in kinds
    assert (TokenKind.NUMBER, "2.5") in kinds
    assert (TokenKind.NUMBER, "1e10") in kinds
    assert (TokenKind.IDENTIFIER, "abc1") in kinds


def test_multiline_block_comment_states() -> None:
    rules = rules_for_dialect(None)
    tokens, state = tokenize_line("SELECT /* start", rules)
    assert state == STATE_IN_BLOCK_COMMENT
    assert tokens[-1] == SqlToken(TokenKind.COMMENT, 7, 8)

    tokens, state = tokenize_line("from */ FROM", rules, state)
    assert state == STATE_NONE
    assert tokens[0] == SqlToken(TokenKind.COMMENT, 0, 7)
    assert tokens[1].kind == TokenKind.KEYWORD

    tokens, state = tokenize_line("select", rules, STATE_IN_BLOCK_COMMENT)
    assert state == STATE_IN_BLOCK_COMMENT
    assert tokens == [SqlToken(TokenKind.COMMENT, 0, 6)]


def test_multiline_string_states() -> None:
    rules = rules_for_dialect("mysql")
    _, state = tokenize_line("SELECT 'abc", rules)
    assert state == STATE_IN_STRING
    tokens, state = tokenize_line("from' FROM", rules, state)
    assert state == STATE_NONE
    assert tokens[0] == SqlToken(TokenKind.STRING, 0, 5)

    _, state = tokenize_line('SELECT "abc', rules)
    assert state == STATE_IN_DOUBLE_QUOTED_STRING
    tokens, state = tokenize_line('x" y', rules, state)
    assert state == STATE_NONE
    assert tokens[0] == SqlToken(TokenKind.STRING, 0, 2)


def test_unclosed_quoted_identifier_ends_at_line_end() -> None:
    tokens, state = tokenize_line('SELECT "abc', rules_for_dialect("sqlite"))
    assert state == STATE_NONE
    assert tokens[-1].kind == TokenKind.QUOTED_IDENTIFIER
    assert tokens[-1].length == 4


def test_empty_text() -> None:
    assert tokenize_line("", rules_for_dialect(None)) == ([], STATE_NONE)
