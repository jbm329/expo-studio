"""Normalize catalog queries into read-only object-properties snapshots."""

from __future__ import annotations

import math
from collections import defaultdict
from numbers import Integral
from typing import TYPE_CHECKING

import pandas as pd

from expo_jbm329.db.core.object_properties import (
    ColumnProperties,
    ConstraintKind,
    MetadataState,
    MetadataValue,
    NamedProperty,
    ObjectConstraint,
    ObjectProperties,
    SchemaObjectIdentity,
    SchemaObjectKind,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from expo_jbm329.db.core.models import SqlResult
    from expo_jbm329.db.core.object_properties import ObjectPropertiesQueries


def _rows(frame: pd.DataFrame) -> list[dict[str, object]]:
    names = [str(name) for name in frame.columns]
    return [dict(zip(names, values, strict=True)) for values in frame.itertuples(index=False, name=None)]


def _text(value: object) -> str | None:
    if value is None or value is pd.NA or value is pd.NaT or (isinstance(value, float) and math.isnan(value)):
        return None
    if not isinstance(value, str):
        message = "Catalog text must be a string or SQL NULL."
        raise TypeError(message)
    return value


def _required_text(value: object) -> str:
    result = _text(value)
    if result is None or not result:
        message = "Required catalog text is missing."
        raise ValueError(message)
    return result


def _integer(value: object) -> int:
    if isinstance(value, bool):
        message = "Catalog ordinal or identifier must not be a boolean."
        raise TypeError(message)
    if isinstance(value, Integral):
        return int(value)
    if isinstance(value, float) and math.isfinite(value) and value.is_integer():
        return int(value)
    message = "Catalog ordinal or identifier must be an integer."
    raise ValueError(message)


def _flag(value: object) -> bool:
    if isinstance(value, (bool, Integral)) and value in (0, 1):
        return bool(value)
    message = "Catalog flag must be a non-null boolean."
    raise ValueError(message)


def _optional_text(value: object, missing: MetadataState = MetadataState.ABSENT) -> MetadataValue[str]:
    text = _text(value)
    return MetadataValue(missing) if text is None else MetadataValue(MetadataState.AVAILABLE, text)


def _expression(row: dict[str, object], prefix: str) -> MetadataValue[str]:
    state = row.get(f"{prefix}_state")
    if state is not None:
        return MetadataValue(MetadataState(_required_text(state)))
    if not _flag(row[f"{prefix}_present"]):
        return MetadataValue(MetadataState.NOT_APPLICABLE if prefix != "default" else MetadataState.ABSENT)
    return _optional_text(row[f"{prefix}_definition"], MetadataState.UNAVAILABLE)


def _description(
    properties: tuple[NamedProperty, ...],
    name: str | None,
    row: dict[str, object],
    state: MetadataState | None,
) -> MetadataValue[str]:
    if state is not None:
        return MetadataValue(state)
    if name is None:
        return _optional_text(row["description"])
    return next(
        (prop.value for prop in properties if prop.name == name),
        MetadataValue(MetadataState.ABSENT),
    )


def _constraints(rows: list[dict[str, object]], identity: SchemaObjectIdentity) -> tuple[ObjectConstraint, ...]:
    groups: dict[tuple[str, str | int], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        identifier = row["constraint_id"]
        key = _required_text(identifier) if isinstance(identifier, str) else _integer(identifier)
        groups[(_required_text(row["constraint_kind"]), key)].append(row)
    constraints: list[ObjectConstraint] = []
    for group in groups.values():
        ordered = sorted(group, key=lambda row: _integer(row["column_position"]))
        first = ordered[0]
        kind = ConstraintKind(_required_text(first["constraint_kind"]))
        columns = tuple(name for row in ordered if (name := _text(row["column_name"])) is not None)
        target = None
        target_columns: tuple[str, ...] = ()
        target_columns_state = MetadataState.AVAILABLE
        if kind == ConstraintKind.FOREIGN_KEY:
            target = SchemaObjectIdentity(
                _required_text(first["referenced_schema"]),
                _required_text(first["referenced_object"]),
                SchemaObjectKind.TABLE,
                identity.catalog,
            )
            if any(_text(row.get("referenced_columns_state")) == MetadataState.UNAVAILABLE for row in ordered):
                target_columns_state = MetadataState.UNAVAILABLE
            else:
                target_columns = tuple(_required_text(row["referenced_column"]) for row in ordered)
        definition = (
            _optional_text(first["definition"], MetadataState.UNAVAILABLE)
            if kind == ConstraintKind.CHECK or _text(first["definition"]) is not None
            else MetadataValue[str](MetadataState.NOT_APPLICABLE)
        )
        if kind in (ConstraintKind.PRIMARY_KEY, ConstraintKind.UNIQUE) and "key_part" in first:
            parts = ", ".join(_required_text(row["key_part"]) for row in ordered)
            keyword = "PRIMARY KEY" if kind == ConstraintKind.PRIMARY_KEY else "UNIQUE"
            definition = MetadataValue(MetadataState.AVAILABLE, f"{keyword} ({parts})")
        constraints.append(
            ObjectConstraint(
                _text(first["constraint_name"]),
                kind,
                columns,
                definition,
                target,
                target_columns,
                target_columns_state,
            )
        )
    return tuple(constraints)


def require_catalog_data(result: SqlResult) -> pd.DataFrame:
    """Require a successful catalog result without hiding retrieval failures.

    Args:
        result: Catalog query result from the existing service executor.

    Returns:
        Retrieved metadata, including a valid empty result set.

    Raises:
        RuntimeError: The query failed or returned no result set.
    """
    if not result.ok:
        if result.error is not None:
            message = result.error.message
            if result.error.hint is not None:
                message += "\n\n" + result.error.hint
        else:
            message = "Object properties retrieval did not complete."
        raise RuntimeError(message)
    if result.data is None:
        message = "Object properties query returned no result set."
        raise RuntimeError(message)
    return result.data


def load_object_properties(
    identity: SchemaObjectIdentity,
    queries: ObjectPropertiesQueries,
    execute: Callable[[str], SqlResult],
) -> ObjectProperties:
    """Execute catalog queries and normalize their documented row shapes.

    Args:
        identity: Requested object kind and namespace.
        queries: Dialect-built, scoped catalog queries.
        execute: Service executor retaining connection and correlation context.

    Returns:
        A snapshot of metadata visible to the database user.

    Raises:
        RuntimeError: Retrieval failed, the object is missing/not visible, or
            concurrent DDL invalidated the snapshot.
        ValueError: Catalog rows contradict the expected typed result contract.
        TypeError: A text field contains an unexpected non-text catalog value.
    """

    def query(sql: str) -> pd.DataFrame:
        return require_catalog_data(execute(sql))

    initial = query(queries.object)
    header = _rows(initial)
    if len(header) != 1:
        message = "The object does not exist or is not visible in the selected database."
        raise RuntimeError(message)
    first = header[0]
    object_id = _integer(first["object_id"])
    resolved = SchemaObjectIdentity(
        _required_text(first["schema_name"]),
        _required_text(first["object_name"]),
        identity.kind,
        _required_text(first["catalog_name"]),
    )
    column_frame = query(queries.columns)
    constraint_frame = query(queries.constraints)
    columns = _rows(column_frame)
    constraints = _rows(constraint_frame)
    properties = _rows(query(queries.properties)) if queries.properties is not None else []
    if not columns and not queries.allows_zero_columns:
        message = "Object columns are no longer available or are not visible."
        raise RuntimeError(message)
    if any(_integer(row["object_id"]) != object_id for row in (*columns, *constraints, *properties)):
        message = "The object changed while its properties were being loaded."
        raise RuntimeError(message)
    # Separate catalog queries are not a transactional DDL snapshot.
    final = query(queries.object)
    changed = not final.equals(initial)
    if queries.verify_catalog_rows:
        changed = not query(queries.columns).equals(column_frame) or changed
        changed = not query(queries.constraints).equals(constraint_frame) or changed
    if changed:
        message = "The object changed while its properties were being loaded. Retry the request."
        raise RuntimeError(message)

    by_column: dict[int, list[NamedProperty]] = defaultdict(list)
    for row in properties:
        by_column[_integer(row["column_id"])].append(
            NamedProperty(_required_text(row["property_name"]), _optional_text(row["property_value"]))
        )
    object_properties = tuple(by_column.pop(0, ()))
    output_columns: list[ColumnProperties] = []
    for row in sorted(columns, key=lambda row: _integer(row["ordinal_position"])):
        column_properties = tuple(by_column.pop(_integer(row["column_id"]), ()))
        output_columns.append(
            ColumnProperties(
                name=_required_text(row["column_name"]),
                ordinal_position=_integer(row["ordinal_position"]),
                data_type=_optional_text(row["data_type"], MetadataState.UNAVAILABLE),
                nullable=MetadataValue(MetadataState.AVAILABLE, _flag(row["nullable"])),
                default=_expression(row, "default"),
                description=_description(
                    column_properties, queries.description_property, row, queries.column_description_state
                ),
                properties=MetadataValue(MetadataState.AVAILABLE, column_properties)
                if queries.properties is not None
                else MetadataValue(MetadataState.UNSUPPORTED),
                identity=_expression(row, "identity"),
                generated=_expression(row, "generated"),
            )
        )
    if by_column:
        message = "Catalog properties reference unknown columns."
        raise ValueError(message)
    return ObjectProperties(
        resolved,
        _description(object_properties, queries.description_property, first, queries.object_description_state),
        MetadataValue(MetadataState.AVAILABLE, object_properties)
        if queries.properties is not None
        else MetadataValue(MetadataState.UNSUPPORTED),
        tuple(output_columns),
        MetadataValue(MetadataState.NOT_APPLICABLE)
        if identity.kind == SchemaObjectKind.VIEW
        else MetadataValue(MetadataState.AVAILABLE, _constraints(constraints, resolved)),
        MetadataState.NOT_APPLICABLE if identity.kind == SchemaObjectKind.VIEW else queries.check_constraints_state,
    )
