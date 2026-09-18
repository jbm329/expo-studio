"""Helpers for browsing SCB tables and their variable/value metadata."""

from __future__ import annotations

from dataclasses import dataclass, field

import httpx


@dataclass(frozen=True)
class ScbTableSummary:
    """Summary metadata for a browsable SCB table."""

    table_id: str
    label: str
    description: str = ""
    first_period: str | None = None
    last_period: str | None = None


@dataclass(frozen=True)
class ScbVariableValue:
    """Single selectable value in an SCB variable."""

    code: str
    label: str


@dataclass(frozen=True)
class ScbVariable:
    """A single SCB variable and its available values."""

    name: str
    label: str
    display_name: str
    values: tuple[ScbVariableValue, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ScbTableMetadata:
    """Full metadata for a selected SCB table."""

    table_id: str
    label: str
    description: str = ""
    variables: tuple[ScbVariable, ...] = field(default_factory=tuple)


class ScbBrowserError(RuntimeError):
    """Raised when SCB metadata cannot be loaded or parsed."""


def fetch_scb_tables(*, lang: str = "sv", timeout: float = 30.0) -> list[ScbTableSummary]:
    """Fetch a list of SCB tables from the public PxWeb table index."""
    url = "https://statistikdatabasen.scb.se/api/v2/tables"
    page_number = 1
    page_size = 200
    summaries: list[ScbTableSummary] = []

    try:
        with httpx.Client(timeout=httpx.Timeout(timeout)) as client:
            while True:
                response = client.get(
                    url,
                    params={
                        "lang": lang,
                        "pageNumber": page_number,
                        "pageSize": page_size,
                    },
                )
                if response.status_code != 200:
                    msg = f"SCB table index request failed: HTTP {response.status_code}"
                    raise ScbBrowserError(msg)

                try:
                    payload = response.json()
                except ValueError as exc:
                    msg = "SCB table index response is not valid JSON"
                    raise ScbBrowserError(msg) from exc

                tables = payload.get("tables")
                if not isinstance(tables, list):
                    msg = "SCB table index response does not contain a tables list"
                    raise ScbBrowserError(msg)

                summaries.extend(
                    ScbTableSummary(
                        table_id=str(item.get("id", "")),
                        label=str(item.get("label") or item.get("id") or ""),
                        description=str(item.get("description") or ""),
                        first_period=item.get("firstPeriod"),
                        last_period=item.get("lastPeriod"),
                    )
                    for item in tables
                    if str(item.get("id", "")).strip()
                )

                page = payload.get("page")
                if not isinstance(page, dict):
                    break

                total_pages = int(page.get("totalPages", page_number))
                if page_number >= total_pages:
                    break
                page_number += 1
    except httpx.RequestError as exc:
        msg_0 = f"Could not load SCB table index: {exc}"
        raise ScbBrowserError(msg_0) from exc

    return summaries


def fetch_scb_table_metadata(*, table_id: str, lang: str = "sv", timeout: float = 30.0) -> ScbTableMetadata:
    """Fetch SCB variable/value metadata for a given table identifier."""
    cleaned = str(table_id).strip()
    if not cleaned:
        msg = "SCB table id must not be empty"
        raise ScbBrowserError(msg)

    url = f"https://statistikdatabasen.scb.se/api/v2/tables/{cleaned}/metadata"
    params = {"lang": lang}
    try:
        with httpx.Client(timeout=httpx.Timeout(timeout)) as client:
            response = client.get(url, params=params)
    except httpx.RequestError as exc:
        msg_0 = f"Could not load SCB metadata for {cleaned}: {exc}"
        raise ScbBrowserError(msg_0) from exc

    if response.status_code != 200:
        msg_0 = f"SCB metadata request failed for {cleaned}: HTTP {response.status_code}"
        raise ScbBrowserError(msg_0)

    try:
        payload = response.json()
    except ValueError as exc:
        msg_0 = f"SCB metadata for {cleaned} is not valid JSON"
        raise ScbBrowserError(msg_0) from exc

    label = str(payload.get("label") or cleaned)
    description = str(payload.get("description") or "")
    dimension = payload.get("dimension")
    if not isinstance(dimension, dict):
        msg_0 = f"SCB metadata for {cleaned} does not contain a dimension map"
        raise ScbBrowserError(msg_0)

    variables: list[ScbVariable] = []
    for name, config in dimension.items():
        if not isinstance(config, dict):
            continue
        category = config.get("category")
        if not isinstance(category, dict):
            continue
        raw_values = category.get("label")
        if not isinstance(raw_values, dict):
            continue

        value_items: list[ScbVariableValue] = []
        for code, label_value in raw_values.items():
            code_text = str(code)
            value_items.append(ScbVariableValue(code=code_text, label=str(label_value)))

        raw_label = str(config.get("label") or name)
        variables.append(
            ScbVariable(
                name=str(name),
                label=raw_label,
                display_name=_build_variable_display_name(name=str(name), label=raw_label),
                values=tuple(value_items),
            )
        )

    return ScbTableMetadata(
        table_id=cleaned,
        label=label,
        description=description,
        variables=tuple(variables),
    )


def build_scb_selection_map(
    metadata: ScbTableMetadata,
    *,
    selected_codes: dict[str, list[str]],
) -> list[tuple[str, tuple[str, ...]]]:
    """Return variable/value selections in a builder-friendly form."""
    selections: list[tuple[str, tuple[str, ...]]] = []
    for variable in metadata.variables:
        codes = [str(item) for item in selected_codes.get(variable.name, []) if str(item).strip()]
        if not codes:
            continue
        selections.append((variable.name, tuple(codes)))
    return selections


def _build_variable_display_name(*, name: str, label: str) -> str:
    """Return a friendly variable name for UI display."""
    cleaned_name = str(name).strip()
    cleaned_label = str(label).strip()
    if not cleaned_name:
        return cleaned_label
    if not cleaned_label:
        return cleaned_name
    if cleaned_name.casefold() == cleaned_label.casefold():
        return cleaned_label
    return cleaned_label
