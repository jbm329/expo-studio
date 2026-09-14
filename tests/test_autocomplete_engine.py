import pytest
from expo_jbm329.gui.autocomplete.engine import SqlAutoCompleter

@pytest.fixture
def completer():
    c = SqlAutoCompleter()
    schema = {
        "public": {
            "users": ["id", "username", "email"],
            "orders": ["id", "user_id", "total"]
        },
        "archive": {
            "old_users": ["id", "username"]
        }
    }
    c.set_schema(schema)
    return c

def test_initial_empty():
    c = SqlAutoCompleter()
    assert c.get_suggestions("abc") == []
    assert c.get_all_objects() == []

def test_set_schema(completer):
    assert "public" in completer._schema
    completer.set_schema(None)
    assert completer._schema == {}

def test_get_suggestions_global(completer):
    # Should match columns, tables, and schemas
    # "u" matches "users", "username", "user_id"
    res = completer.get_suggestions("u")
    assert "users" in res
    assert "username" in res
    assert "user_id" in res
    # sorted: col_list + tables + schemas
    # columns: email, id, total, user_id, username
    # tables: old_users, orders, users
    # schemas: archive, public

def test_get_suggestions_schema_dot(completer):
    # "public." -> tables in public
    res = completer.get_suggestions("public.")
    assert sorted(res) == ["orders", "users"]

    # case insensitive
    res = completer.get_suggestions("PUBLIC.")
    assert sorted(res) == ["orders", "users"]

def test_get_suggestions_schema_table_prefix(completer):
    # "public.u" -> tables starting with u in public
    res = completer.get_suggestions("public.u")
    assert res == ["users"]

def test_get_suggestions_table_dot(completer):
    # "users." -> columns in users (resolves schema)
    res = completer.get_suggestions("users.")
    assert sorted(res) == ["email", "id", "username"]

    # "old_users." -> columns in old_users (resolves schema archive)
    res = completer.get_suggestions("old_users.")
    assert sorted(res) == ["id", "username"]

def test_get_suggestions_table_col_prefix(completer):
    # "users.u" -> columns starting with u in users
    res = completer.get_suggestions("users.u")
    assert res == ["username"]

def test_get_suggestions_schema_table_dot(completer):
    # "public.users." -> columns in users
    res = completer.get_suggestions("public.users.")
    assert sorted(res) == ["email", "id", "username"]

def test_get_suggestions_schema_table_col_prefix(completer):
    # "public.users.e" -> columns starting with e
    res = completer.get_suggestions("public.users.e")
    assert res == ["email"]

def test_get_global_suggestions(completer):
    res = completer.get_global_suggestions("id")
    assert res == ["id"] # only column matches exactly or starts with

    res = completer.get_global_suggestions("pub")
    assert res == ["public"]

def test_get_all_objects(completer):
    res = completer.get_all_objects()
    # Check if some expected items are there
    assert "username" in res
    assert "users" in res
    assert "public" in res
    assert "archive" in res

def test_resolve_schema_ci(completer):
    assert completer._resolve_schema_ci("PUBLIC") == "public"
    assert completer._resolve_schema_ci("None") is None

def test_find_schema_for_table(completer):
    assert completer._find_schema_for_table("USERS") == "public"
    assert completer._find_schema_for_table("OLD_USERS") == "archive"
    assert completer._find_schema_for_table("nonexistent") is None

def test_filter_starts_with():
    items = ["Apple", "banana", "Cherry"]
    assert SqlAutoCompleter._filter_starts_with(items, "a") == ["Apple"]
    assert SqlAutoCompleter._filter_starts_with(items, "B") == ["banana"]
    assert SqlAutoCompleter._filter_starts_with(items, "xyz") == []
