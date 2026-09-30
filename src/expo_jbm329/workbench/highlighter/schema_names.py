"""Extract schema names used for schema-aware SQL highlighting."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping


def collect_schema_highlight_names(by_schema: Mapping[str, object]) -> tuple[frozenset[str], frozenset[str]]:
    """Collect object and column names from a ``{schema: {table: [columns]}}`` mapping.

    Args:
        by_schema: Schema mapping as produced for autocomplete (``schema_dict["by_schema"]``).
            Malformed entries are ignored.

    Returns:
        A tuple ``(objects, columns)`` where ``objects`` contains schema, table
        and view names and ``columns`` contains column names.
    """
    objects: set[str] = set()
    columns: set[str] = set()
    for schema, tables in by_schema.items():
        if schema:
            objects.add(schema)
        if not isinstance(tables, dict):
            continue
        for table, table_columns in tables.items():  # pyright: ignore[reportUnknownVariableType]
            if isinstance(table, str) and table:
                objects.add(table)
            if not isinstance(table_columns, (list, tuple, set, frozenset)):
                continue
            columns.update(col for col in table_columns if isinstance(col, str) and col)  # pyright: ignore[reportUnknownVariableType]
    return frozenset(objects), frozenset(columns)
