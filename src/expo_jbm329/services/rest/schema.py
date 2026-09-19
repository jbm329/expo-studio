"""Schema-aware validation helpers for REST responses."""

from __future__ import annotations

from typing import TYPE_CHECKING

from expo_jbm329.services.rest.normalizer import normalize_json_to_df

if TYPE_CHECKING:
    from collections.abc import Sequence


class RestSchemaValidationError(ValueError):
    """Raised when a REST response fails schema validation."""


def validate_response_columns(
    payload: object,
    *,
    response_path: str | None = None,
    required_columns: Sequence[str] | None = None,
) -> list[str]:
    """Validate that a REST payload normalizes to a table and contains required columns.

    Args:
        payload: Parsed JSON payload.
        response_path: Optional path to the records container.
        required_columns: Column names that must be present in the normalized table.

    Returns:
        Column names in the normalized table.

    Raises:
        RestSchemaValidationError: If the payload cannot be normalized or required
            fields are missing.
    """
    df = normalize_json_to_df(payload, response_path=response_path)
    columns = list(df.columns)

    if required_columns:
        missing = [column for column in required_columns if column not in columns]
        if missing:
            raise RestSchemaValidationError("Response is missing required columns: " + ", ".join(missing))

    return columns


def build_response_preview(
    payload: object,
    *,
    response_path: str | None = None,
    limit: int = 5,
) -> dict[str, object]:
    """Build a compact preview of a normalized REST response.

    Args:
        payload: Parsed JSON payload.
        response_path: Optional path to the records container.
        limit: Maximum number of rows to include in sample output.

    Returns:
        A dictionary containing the normalized row count, columns, and sample rows.
    """
    if limit < 1:
        limit = 1

    df = normalize_json_to_df(payload, response_path=response_path)
    sample = df.head(limit).to_dict(orient="records")

    return {
        "row_count": len(df),
        "columns": list(df.columns),
        "sample": sample,
        "empty": bool(df.empty),
    }
