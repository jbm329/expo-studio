"""Utilities for transforming schema metadata into consumer-friendly formats.

This module provides the build_schema_dict function, which converts cached
schema information into a format suitable for autocompletion and UI display.
"""

from __future__ import annotations


def build_schema_dict(cache: dict[str, object]) -> dict[str, object]:
    """Build an autocomplete-friendly schema dictionary from the cache structure.

    Args:
        cache: A dictionary containing cached schema information with keys
            "tables", "views", and "columns".

    Returns:
        A dictionary containing "tables" (flat map) and "by_schema" (nested map)
        for autocompletion and UI display.
    """
    if not cache:
        return {"tables": {}, "by_schema": {}}

    raw_tables = cache.get("tables", [])
    tables_list = raw_tables if isinstance(raw_tables, list) else []
    raw_views = cache.get("views", [])
    views_list = raw_views if isinstance(raw_views, list) else []
    raw_columns = cache.get("columns", {})
    columns_map: dict[tuple[str, str], list[dict[str, object]]] = raw_columns if isinstance(raw_columns, dict) else {}

    def _col_names_for(schema: str, table: str) -> list[str]:
        """Extract a list of column names for (schema, table) from columns_map.

        Supports common key variations in column dicts.
        """
        col_dicts = columns_map.get((schema, table), []) or []
        names: list[str] = []
        for c in col_dicts:
            # Primary expected key
            name = c.get("COLUMN_NAME")
            if not name:
                # Fallback keys sometimes seen from various drivers/adapters
                name = c.get("column_name") or c.get("name") or c.get("COLUMN") or c.get("ColumnName")
            if name:
                names.append(str(name))
        return names

    # ---------------- Flat view (preferred by autocomplete) ----------------
    flat_tables: dict[str, list[str]] = {}

    # ---------------- Nested view (for optional consumers) -----------------
    by_schema: dict[str, dict[str, list[str]]] = {}

    # Register tables
    for r in tables_list:
        s = r.get("schema")
        t = r.get("name")
        if not s or not t:
            continue
        cols = _col_names_for(s, t)

        # nested
        by_schema.setdefault(s, {})
        by_schema[s][t] = cols

        # flat
        flat_tables[f"{s}.{t}"] = cols

    # Register views
    for r in views_list:
        s = r.get("schema")
        t = r.get("name")
        if not s or not t:
            continue
        cols = _col_names_for(s, t)

        # nested
        by_schema.setdefault(s, {})
        by_schema[s][t] = cols

        # flat
        flat_tables[f"{s}.{t}"] = cols

    return {
        "tables": flat_tables,  # <- primary map for autocomplete: "schema.table" -> [cols]
        "by_schema": by_schema,  # <- secondary nested map (optional consumers)
    }
