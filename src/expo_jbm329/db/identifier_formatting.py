"""Dialect-aware formatting of schema identifiers.

Builds SQL identifier text (tables, views and columns) from schema tree
metadata, e.g. for drag-and-drop into the SQL editor. The module is free of
UI dependencies so it can be tested in isolation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeGuard

if TYPE_CHECKING:
    from collections.abc import Iterable

    from expo_jbm329.db.core.interfaces import DialectProtocol


SchemaItemMeta = dict[str, str]

DEFAULT_MULTILINE_INDENT = "    "


def is_valid_schema_meta(meta: object) -> TypeGuard[SchemaItemMeta]:
    """Validate the structure of schema item metadata.

    Args:
        meta: The metadata to validate. Expected structures:
            - For tables/views: {"type": "table"|"view", "schema": str, "name": str}
            - For columns: {"type": "column", "schema": str, "table": str, "column": str}

    Returns:
        True if the metadata has a valid structure, False otherwise.
    """
    if not isinstance(meta, dict):
        return False
    item_type = meta.get("type")
    if item_type in {"table", "view"}:
        return all(isinstance(meta.get(k), str) for k in ("type", "schema", "name"))
    if item_type == "column":
        return all(isinstance(meta.get(k), str) for k in ("type", "schema", "table", "column"))
    return False


def build_identifier_text(
    metas: Iterable[object],
    dialect: DialectProtocol,
    *,
    prefer_multiline_for_same_table: bool = True,
    indent: str = DEFAULT_MULTILINE_INDENT,
) -> str:
    """Build dialect-quoted SQL identifier text from schema item metadata.

    Invalid metadata entries are ignored and duplicates are removed while
    preserving the original order.

    Args:
        metas: Metadata entries for tables, views and/or columns.
        dialect: Dialect used for identifier quoting and qualification.
        prefer_multiline_for_same_table: If True and all items are columns from
            the same table, format them as a comma-separated multiline list.
        indent: Indentation used for continuation lines of a multiline list.

    Returns:
        The formatted identifier text, or an empty string when no valid
        metadata was provided.
    """
    parts: list[str] = []
    seen: set[str] = set()
    types: set[str] = set()
    tables_for_columns: set[tuple[str, str]] = set()

    for meta in metas:
        if not is_valid_schema_meta(meta):
            continue

        item_type = meta["type"]
        types.add(item_type)

        if item_type == "column":
            text = dialect.qualify_column(meta["schema"], meta["table"], meta["column"])
            tables_for_columns.add((meta["schema"], meta["table"]))
        else:
            text = dialect.qualify(meta["schema"], meta["name"])

        if text not in seen:
            seen.add(text)
            parts.append(text)

    if not parts:
        return ""

    only_columns = types == {"column"}
    if only_columns and len(tables_for_columns) == 1 and prefer_multiline_for_same_table:
        # The first column continues the user's current line; later columns are indented.
        head, *tail = parts
        return ",\n".join([head, *(f"{indent}{part}" for part in tail)])

    # Mixed types or multiple tables are newline separated for clarity.
    return "\n".join(parts)
