import pytest

from expo_jbm329.gui.autocomplete.identifiers import (
    IdentifierCompletion,
    identifier_completion,
    identifier_lookup_name,
    quote_identifier,
    split_identifier_prefix,
)


@pytest.mark.parametrize(
    ("dialect", "opening", "closing"),
    [
        ("mssql", "[", "]"),
        ("tsql", "[", "]"),
        (" MSSQL ", "[", "]"),
        ("mysql", "`", "`"),
        ("mariadb", "`", "`"),
        ("postgresql", '"', '"'),
        ("postgres", '"', '"'),
        ("sqlite", '"', '"'),
        ("duckdb", '"', '"'),
        ("oracle", '"', '"'),
        ("ansi", '"', '"'),
        ("other", '"', '"'),
        (None, '"', '"'),
        ("", '"', '"'),
    ],
)
@pytest.mark.parametrize(
    "name",
    ["users", "select", "MixedCase", "order details", "table.name", 'a]b"c`d', "[literal]", '"literal"', "", " a "],
)
def test_quote_identifier_uses_dialect_and_preserves_metadata(dialect, opening, closing, name):
    expected = opening + name.replace(closing, closing * 2) + closing
    quoted = quote_identifier(name, dialect)
    assert quoted == expected
    assert identifier_lookup_name(quoted) == name


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (" users ", "users"),
        ('"users"', "users"),
        ("[users]", "users"),
        ("`users`", "users"),
        ('"user', "user"),
        ("[user", "user"),
        ("`user", "user"),
        ('" a ', " a "),
        ("[a]]", "a]"),
        ('"a""', 'a"'),
        ("`a``", "a`"),
        ("[a]]]", "a]"),
        ('"a"""', 'a"'),
        ("`a```", "a`"),
        ('""', ""),
        ('"""', '"'),
        ('""""', '"'),
        ('"a.b"', "a.b"),
    ],
)
def test_identifier_lookup_decodes_complete_and_partial_source(source, expected):
    assert identifier_lookup_name(source) == expected


@pytest.mark.parametrize(
    ("prefix", "expected"),
    [
        ("public.users.u", ("public", "users", "u")),
        ('"public"."users".', ('"public"', '"users"', "")),
        ("[my.schema].[my.table].[col.prefix", ("[my.schema]", "[my.table]", "[col.prefix")),
        ('"schema.with.dot"."a""b".', ('"schema.with.dot"', '"a""b"', "")),
        ("`my``schema`.`my table`.`my.col`", ("`my``schema`", "`my table`", "`my.col`")),
        ('"unfinished.with.dot', ('"unfinished.with.dot',)),
        ("", ("",)),
    ],
)
def test_split_prefix_preserves_source_and_literal_dots(prefix, expected):
    assert split_identifier_prefix(prefix) == expected


@pytest.mark.parametrize(
    ("before", "after", "prefix", "component", "suffix"),
    [
        ("SELECT u", " FROM users", "u", "u", ""),
        ("SELECT public.", "", "public.", "", ""),
        ('SELECT "my schema"."my table".', "", '"my schema"."my table".', "", ""),
        ("SELECT [dbo].[my.table].[user", "] FROM users", "[dbo].[my.table].[user", "[user", "]"),
        ('SELECT "a""b"."us', 'ers" FROM users', '"a""b"."us', '"us', 'ers"'),
        ("SELECT `a``b`.`us", "ers` FROM users", "`a``b`.`us", "`us", "ers`"),
        ('SELECT "orders."', "", '"orders."', '"orders."', ""),
        ("SELECT u", "sers, id FROM users", "u", "u", "sers"),
        ("SELECT ", "FROM users", "", "", ""),
        ("SELECT id+", "", "", "", ""),
        ('SELECT " a ', "", '" a ', '" a ', ""),
        ("SELECT 'literal.with.dot', u", "", "u", "u", ""),
        ('SELECT "😀 schema".u', "", '"😀 schema".u', "u", ""),
    ],
)
def test_completion_span_preserves_qualifier_and_includes_existing_suffix(before, after, prefix, component, suffix):
    sql = before + after
    cursor = len(before)
    expected = IdentifierCompletion(prefix, cursor - len(component), cursor + len(suffix))
    context = identifier_completion(sql, cursor)
    assert context == expected
    assert sql[context.start : context.end] == component + suffix
    assert sql[: context.start] + "[completed]" + sql[context.end :] == (
        before[: cursor - len(component)] + "[completed]" + after[len(suffix) :]
    )


@pytest.mark.parametrize(
    "before",
    ["SELECT 'u", "SELECT 'escaped''u", "SELECT -- users.", "SELECT /* users.", "SELECT 'u'", "SELECT /* u */"],
)
def test_completion_is_unavailable_in_literals_and_comments(before):
    assert identifier_completion(before + " more", len(before)) is None


@pytest.mark.parametrize("before", ["SELECT 'x', ", "SELECT -- x\n", "SELECT /* x */ "])
def test_completion_resumes_after_literals_and_comments(before):
    assert identifier_completion(before + "u", len(before) + 1) == IdentifierCompletion(
        "u", len(before), len(before) + 1
    )


@pytest.mark.parametrize("position", [-1, 10])
def test_completion_rejects_out_of_range_cursor(position):
    with pytest.raises(ValueError, match="cursor index"):
        identifier_completion("SELECT", position)
