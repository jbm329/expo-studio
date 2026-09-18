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

    msg = "Unsupported JSON structure"
    raise RestNormalizeError(msg)


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
        msg = f"Unsupported JSON root type: {type(payload).__name__}"
        raise RestNormalizeError(msg)

    current = payload

    for part in response_path.split("."):
        # dict access
        if isinstance(current, dict):
            if part not in current:
                msg = f"Invalid response_path '{response_path}': '{part}' not found"
                raise RestNormalizeError(msg)
            current = current[part]
            continue

        # list index access
        if isinstance(current, list):
            try:
                idx = int(part)
            except ValueError as err:
                msg = f"Invalid response_path '{response_path}': '{part}' is not a valid list index"
                raise RestNormalizeError(msg) from err

            try:
                current = current[idx]
            except IndexError as err:
                msg = f"Invalid response_path '{response_path}': list index {idx} out of range"
                raise RestNormalizeError(msg) from err
            continue

        msg = f"Invalid response_path '{response_path}': cannot traverse object of type {type(current).__name__}"
        raise RestNormalizeError(msg)

    if not isinstance(current, (list, dict)):
        msg = f"Extracted object at '{response_path}' is not list or dict (got {type(current).__name__})"
        raise RestNormalizeError(msg)

    return current


def _normalize_jsonstat2(payload: dict) -> pd.DataFrame:
    """Normalize JSON-stat v2 dataset into a flat DataFrame.

    This handles PxWebApi v2 responses with outputFormat=json-stat2.
    """
    ids = payload.get("id")
    values = payload.get("value")
    dimensions = payload.get("dimension")

    if not isinstance(ids, list):
        msg = "JSON-stat v2: missing 'id' array"
        raise RestNormalizeError(msg)
    if not isinstance(values, list):
        msg = "JSON-stat v2: missing 'value' array"
        raise RestNormalizeError(msg)
    if not isinstance(dimensions, dict):
        msg = "JSON-stat v2: missing 'dimension' object"
        raise RestNormalizeError(msg)

    # Build ordered dimension value lists. Prefer the user-facing labels provided by
    # the SCB/PxWeb API over the raw technical keys when they are present.
    dim_names: list[str] = []
    display_dim_names: list[str] = []
    dim_values: list[list[str]] = []
    dim_labels_by_code: dict[str, dict[str, str]] = {}

    seen_names: set[str] = set()
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
        label_map = category.get("label")
        labels: dict[str, str] = {}
        if isinstance(label_map, dict):
            labels = {str(code): str(text) for code, text in label_map.items()}

        # index: code -> position
        codes = sorted(index.keys(), key=lambda k: index[k])
        display_name = _display_dimension_name(dim_id, dim)
        unique_name = display_name
        counter = 2
        while unique_name in seen_names:
            unique_name = f"{display_name}_{counter}"
            counter += 1
        seen_names.add(unique_name)

        dim_names.append(dim_id)
        display_dim_names.append(unique_name)
        dim_values.append(codes)
        dim_labels_by_code[dim_id] = labels

    if not dim_names or not dim_values:
        msg = "JSON-stat v2: no dimensions found"
        raise RestNormalizeError(msg)

    records: list[dict] = []

    for coords, val in zip(
        itertools.product(*dim_values),
        values,
        strict=True,
    ):
        rec = {}
        for raw_dim_name, display_name, code in zip(dim_names, display_dim_names, coords, strict=True):
            label = dim_labels_by_code.get(raw_dim_name, {}).get(code)
            rec[display_name] = label if label is not None else code
        rec["Value"] = val
        records.append(rec)

    return pd.DataFrame(records)


def _display_dimension_name(dim_id: str, dim_config: dict[str, Any]) -> str:
    """Return the user-visible name for a JSON-stat dimension."""
    raw_name = str(dim_id).strip()
    label = str(dim_config.get("label") or "").strip()
    if label and label.casefold() != raw_name.casefold():
        return label
    return raw_name
