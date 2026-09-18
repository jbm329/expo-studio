from __future__ import annotations

from expo_jbm329.services.schema_model import build_schema_dict


def test_build_schema_dict_empty():
    assert build_schema_dict({}) == {"tables": {}, "by_schema": {}}


def test_build_schema_dict_uses_table_and_view_metadata():
    cache = {
        "tables": [{"schema": "dbo", "name": "Users"}],
        "views": [{"schema": "dbo", "name": "ActiveUsers"}],
        "columns": {
            ("dbo", "Users"): [
                {"COLUMN_NAME": "id"},
                {"name": "email"},
            ],
            ("dbo", "ActiveUsers"): [
                {"ColumnName": "id"},
            ],
        },
    }

    res = build_schema_dict(cache)

    assert res["tables"]["dbo.Users"] == ["id", "email"]
    assert res["tables"]["dbo.ActiveUsers"] == ["id"]
    assert res["by_schema"]["dbo"]["Users"] == ["id", "email"]
    assert res["by_schema"]["dbo"]["ActiveUsers"] == ["id"]


def test_build_schema_dict_skips_invalid_rows():
    cache = {
        "tables": [{"schema": "dbo"}, {"name": "Users"}],
        "views": [],
        "columns": {},
    }

    res = build_schema_dict(cache)

    assert res == {"tables": {}, "by_schema": {}}
