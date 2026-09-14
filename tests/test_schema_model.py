from expo_jbm329.services.schema_model import build_schema_dict

def test_build_schema_dict_empty():
    assert build_schema_dict({}) == {"tables": {}, "by_schema": {}}

def test_build_schema_dict_with_data():
    cache = {
        "tables": [{"schema": "dbo", "name": "Users"}],
        "views": [{"schema": "dbo", "name": "ActiveUsers"}],
        "columns": {
            ("dbo", "Users"): [{"COLUMN_NAME": "id"}, {"name": "email"}],
            ("dbo", "ActiveUsers"): [{"ColumnName": "id"}]
        }
    }
    res = build_schema_dict(cache)
    
    assert "dbo.Users" in res["tables"]
    assert res["tables"]["dbo.Users"] == ["id", "email"]
    assert res["tables"]["dbo.ActiveUsers"] == ["id"]
    
    assert "dbo" in res["by_schema"]
    assert "Users" in res["by_schema"]["dbo"]
    assert res["by_schema"]["dbo"]["Users"] == ["id", "email"]

def test_build_schema_dict_missing_info():
    cache = {
        "tables": [{"schema": "dbo"}], # missing name
        "columns": {}
    }
    res = build_schema_dict(cache)
    assert res["tables"] == {}
