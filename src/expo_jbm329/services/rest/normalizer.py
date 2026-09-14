"""REST data source normalization helpers."""
from __future__ import annotations

import itertools
from typing import Any

import pandas as pd


class RestNormalizeError(RuntimeError):
    """Raised when REST response normalization fails."""


def normalize_json_to_df(
    payload: Any,
    *,
    response_path: str | None = None,
) -> pd.DataFrame:
    """Normalize a JSON payload into a pandas DataFrame.

    Args:
        payload: Parsed JSON payload (dict / list).
        response_path: Optional dot-separated path to the list of records
            within the JSON payload (e.g. "data.items").

    Returns:
        pandas.DataFrame

    Raises:
        RestNormalizeError: If the payload cannot be normalized.
    """
    # ------------------------------------------------------------
    # JSON-stat v2 (PxWebApi v2, Eurostat, SSB, SCB)
    # ------------------------------------------------------------
    if (
        isinstance(payload, dict)
        and payload.get("class") == "dataset"
        and isinstance(payload.get("dimension"), dict)
        and "value" in payload
    ):
        return _normalize_jsonstat2(payload)

    # ------------------------------------------------------------
    # Generic APIs
    # ------------------------------------------------------------
    data = _extract_records(payload, response_path)

    # dict-of-lists (Open-Meteo, stats APIs)
    if isinstance(data, dict) and all(isinstance(v, list) for v in data.values()):
        return pd.DataFrame(data)

    # list-of-dict (REST records)
    if isinstance(data, list):
        return pd.json_normalize(data)

    # single dict
    if isinstance(data, dict):
        return pd.json_normalize(data)

    raise RestNormalizeError("Unsupported JSON structure")


# ---------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------

def _extract_records(payload: Any, response_path: str | None) -> Any:
    """Extract the record container from a JSON payload.

    If response_path is None:
        - list -> returned as-is
        - dict -> returned as-is (single-record case)

    If response_path is provided:
        - Navigate the payload using dot-notation.

    Args:
        payload: Parsed JSON payload.
        response_path: Dot-separated path.

    Returns:
        The extracted data suitable for pandas.json_normalize.
    """
    if response_path in (None, "", "None"):
        response_path = None

    if response_path is None:
        if isinstance(payload, (list, dict)):
            return payload
        raise RestNormalizeError(
            f"Unsupported JSON root type: {type(payload).__name__}"
        )

    current = payload

    for part in response_path.split("."):
        # dict access
        if isinstance(current, dict):
            if part not in current:
                raise RestNormalizeError(
                    f"Invalid response_path '{response_path}': '{part}' not found"
                )
            current = current[part]
            continue

        # list index access
        if isinstance(current, list):
            try:
                idx = int(part)
            except ValueError as err:
                raise RestNormalizeError(
                    f"Invalid response_path '{response_path}': '{part}' is not a valid list index"
                ) from err

            try:
                current = current[idx]
            except IndexError as err:
                raise RestNormalizeError(
                    f"Invalid response_path '{response_path}': list index {idx} out of range"
                ) from err
            continue

        raise RestNormalizeError(
            f"Invalid response_path '{response_path}': "
            f"cannot traverse object of type {type(current).__name__}"
        )

    if not isinstance(current, (list, dict)):
        raise RestNormalizeError(
            f"Extracted object at '{response_path}' is not list or dict "
            f"(got {type(current).__name__})"
        )

    return current


def _normalize_jsonstat2(payload: dict) -> pd.DataFrame:
    """Normalize JSON-stat v2 dataset into a flat DataFrame.

    This handles PxWebApi v2 responses with outputFormat=json-stat2.
    """
    ids = payload.get("id")
    values = payload.get("value")
    dimensions = payload.get("dimension")

    if not isinstance(ids, list):
        raise RestNormalizeError("JSON-stat v2: missing 'id' array")
    if not isinstance(values, list):
        raise RestNormalizeError("JSON-stat v2: missing 'value' array")
    if not isinstance(dimensions, dict):
        raise RestNormalizeError("JSON-stat v2: missing 'dimension' object")

    # Build ordered dimension value lists
    dim_names: list[str] = []
    dim_values: list[list[str]] = []

    for dim_id in ids:
        dim = dimensions.get(dim_id)
        if not isinstance(dim, dict):
            continue

        category = dim.get("category")
        if not isinstance(category, dict):
            continue

        index = category.get("index")
        if not isinstance(index, dict):
            continue

        # index: code -> position
        codes = sorted(index.keys(), key=lambda k: index[k])

        dim_names.append(dim_id)
        dim_values.append(codes)

    if not dim_names or not dim_values:
        raise RestNormalizeError("JSON-stat v2: no dimensions found")   

    records: list[dict] = []

    for coords, val in zip(
        itertools.product(*dim_values),
        values,
        strict=True,
    ):
        rec = dict(zip(dim_names, coords, strict=True))
        rec["Value"] = val
        records.append(rec)

    return pd.DataFrame(records)
