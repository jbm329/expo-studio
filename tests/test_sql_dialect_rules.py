from __future__ import annotations

import pytest

from expo_jbm329.workbench.highlighter.schema_names import collect_schema_highlight_names
from expo_jbm329.workbench.highlighter.sql_dialect_rules import (
    BACKTICK_QUOTE,
    BRACKET_QUOTE,
    DOUBLE_QUOTE,
    rules_for_dialect,
)


@pytest.mark.parametrize("dialect", [None, "", "unknown"])
def test_generic_rules_cover_all_dialects(dialect: str | None) -> None:
    rules = rules_for_dialect(dialect)
    assert rules.name == "generic"
    assert {"TOP", "LIMIT", "PRAGMA", "ILIKE", "ROWNUM"} <= rules.keywords
    assert {"GETDATE", "IFNULL", "NVL", "DATE_TRUNC"} <= rules.functions
    assert set(rules.identifier_quotes) == {BRACKET_QUOTE, DOUBLE_QUOTE, BACKTICK_QUOTE}


def test_tsql_rules() -> None:
    rules = rules_for_dialect("TSQL")
    assert rules.name == "tsql"
    assert "TOP" in rules.keywords
    assert "LIMIT" not in rules.keywords
    assert BRACKET_QUOTE in rules.identifier_quotes
    assert "GETDATE" in rules.functions


def test_sqlite_rules() -> None:
    rules = rules_for_dialect("sqlite")
    assert {"LIMIT", "OFFSET", "PRAGMA"} <= rules.keywords
    assert "TOP" not in rules.keywords
    assert set(rules.identifier_quotes) == {BRACKET_QUOTE, DOUBLE_QUOTE, BACKTICK_QUOTE}
    assert rules.string_quotes == ("'",)


def test_mysql_rules() -> None:
    rules = rules_for_dialect("mysql")
    assert rules.identifier_quotes == (BACKTICK_QUOTE,)
    assert '"' in rules.string_quotes
    assert "#" in rules.line_comment_prefixes
    assert rules.backslash_escapes is True


@pytest.mark.parametrize("dialect", ["postgres", "oracle"])
def test_ansi_style_dialects_use_double_quotes(dialect: str) -> None:
    rules = rules_for_dialect(dialect)
    assert rules.identifier_quotes == (DOUBLE_QUOTE,)
    assert "SELECT" in rules.keywords


def test_collect_schema_highlight_names() -> None:
    objects, columns = collect_schema_highlight_names({
        "main": {"Order": ["Id", "Total"], "Table": []},
        "": {"ignored_schema_table": ["c"]},
        "bad": "not a dict",
        "other": {"t": None},
    })
    assert objects == {"main", "Order", "Table", "ignored_schema_table", "bad", "other", "t"}
    assert columns == {"Id", "Total", "c"}


def test_collect_schema_highlight_names_empty() -> None:
    assert collect_schema_highlight_names({}) == (frozenset(), frozenset())
