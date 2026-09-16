import pytest

from expo_jbm329.services.rest.schema import (
    RestSchemaValidationError,
    build_response_preview,
    validate_response_columns,
)


def test_validate_response_columns_rejects_missing_columns():
    payload = {"items": [{"id": 1, "name": "Alpha"}, {"id": 2, "name": "Beta"}]}

    with pytest.raises(RestSchemaValidationError, match="missing"):
        validate_response_columns(payload, response_path="items", required_columns=("id", "status"))


def test_build_response_preview_handles_nested_response_path():
    payload = {"data": {"items": [{"id": 1, "name": "Alpha"}, {"id": 2, "name": "Beta"}]}}

    preview = build_response_preview(payload, response_path="data.items", limit=1)

    assert preview["row_count"] == 2
    assert preview["columns"] == ["id", "name"]
    assert preview["sample"][0]["id"] == 1
