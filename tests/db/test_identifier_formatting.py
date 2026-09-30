from __future__ import annotations

import pytest

from expo_jbm329.db.dialects.ansi import AnsiDialect
from expo_jbm329.db.dialects.mssql import MssqlDialect
from expo_jbm329.db.dialects.mysql import MySqlDialect
from expo_jbm329.db.dialects.sqlite import SqliteDialect
from expo_jbm329.db.identifier_formatting import build_identifier_text, is_valid_schema_meta


def table(schema: str, name: str, kind: str = "table") -> dict[str, str]:
    return {"type": kind, "schema": schema, "name": name}


def column(schema: str, tbl: str, col: str) -> dict[str, str]:
    return {"type": "column", "schema": schema, "table": tbl, "column": col}


@pytest.mark.parametrize(
    ("dialect", "expected"),
    [
        (MssqlDialect(), "[dbo].[Customers]"),
        (MySqlDialect(), "`dbo`.`Customers`"),
        (SqliteDialect(), '"dbo"."Customers"'),
        (AnsiDialect(), '"dbo"."Customers"'),
    ],
)
def test_table_is_quoted_per_dialect(dialect, expected):
    assert build_identifier_text([table("dbo", "Customers")], dialect) == expected


def test_view_is_formatted_like_table():
    assert build_identifier_text([table("dbo", "V", kind="view")], MssqlDialect()) == "[dbo].[V]"


def test_sqlite_main_schema_is_included():
    assert build_identifier_text([table("main", "t"), column("main", "t", "c")], SqliteDialect()) == (
        '"main"."t"\n"main"."t"."c"'
    )


def test_columns_from_same_table_are_multiline():
    metas = [column("db", "t", "a"), column("db", "t", "b"), column("db", "t", "c")]

    assert build_identifier_text(metas, MySqlDialect()) == "`db`.`t`.`a`,\n    `db`.`t`.`b`,\n    `db`.`t`.`c`"


def test_multiline_can_be_disabled_and_indent_customized():
    metas = [column("dbo", "t", "a"), column("dbo", "t", "b")]
    dialect = MssqlDialect()

    assert build_identifier_text(metas, dialect, prefer_multiline_for_same_table=False) == (
        "[dbo].[t].[a]\n[dbo].[t].[b]"
    )
    assert build_identifier_text(metas, dialect, indent="\t") == "[dbo].[t].[a],\n\t[dbo].[t].[b]"


def test_mixed_types_and_tables_are_newline_separated():
    metas = [table("dbo", "t"), column("dbo", "t", "a"), column("dbo", "u", "b")]

    assert build_identifier_text(metas, MssqlDialect()) == "[dbo].[t]\n[dbo].[t].[a]\n[dbo].[u].[b]"


def test_duplicates_and_invalid_meta_are_ignored():
    metas = [
        table("dbo", "t"),
        table("dbo", "t"),
        {"type": "placeholder", "kind": "columns"},
        {"type": "table", "schema": "dbo"},
        None,
        "not a dict",
    ]

    assert build_identifier_text(metas, MssqlDialect()) == "[dbo].[t]"


def test_empty_input_returns_empty_string():
    assert build_identifier_text([], MssqlDialect()) == ""


def test_identifiers_with_quote_chars_are_escaped():
    assert build_identifier_text([table("dbo", "we]ird")], MssqlDialect()) == "[dbo].[we]]ird]"


@pytest.mark.parametrize(
    ("meta", "expected"),
    [
        (table("s", "t"), True),
        (table("s", "v", kind="view"), True),
        (column("s", "t", "c"), True),
        ({"type": "column", "schema": "s", "table": "t"}, False),
        ({"type": "group", "group": "tables"}, False),
        (None, False),
    ],
)
def test_is_valid_schema_meta(meta, expected):
    assert is_valid_schema_meta(meta) is expected
