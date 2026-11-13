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
    if not _flag(row[f"{prefix}_present"]):
        return MetadataValue(MetadataState.NOT_APPLICABLE if prefix != "default" else MetadataState.ABSENT)
    return _optional_text(row[f"{prefix}_definition"], MetadataState.UNAVAILABLE)


def _description(properties: tuple[NamedProperty, ...], name: str) -> MetadataValue[str]:
    return next(
        (prop.value for prop in properties if prop.name == name),
        MetadataValue(MetadataState.ABSENT),
    )


def _constraints(rows: list[dict[str, object]], identity: SchemaObjectIdentity) -> tuple[ObjectConstraint, ...]:
    groups: dict[int, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        groups[_integer(row["constraint_id"])].append(row)
    constraints: list[ObjectConstraint] = []
    for group in groups.values():
        ordered = sorted(group, key=lambda row: _integer(row["column_position"]))
        first = ordered[0]
        kind = ConstraintKind(_required_text(first["constraint_kind"]))
        columns = tuple(name for row in ordered if (name := _text(row["column_name"])) is not None)
        target = None
        target_columns: tuple[str, ...] = ()
        if kind == ConstraintKind.FOREIGN_KEY:
            target = SchemaObjectIdentity(
                _required_text(first["referenced_schema"]),
                _required_text(first["referenced_object"]),
                SchemaObjectKind.TABLE,
                identity.catalog,
            )
            target_columns = tuple(_required_text(row["referenced_column"]) for row in ordered)
        constraints.append(
            ObjectConstraint(
                _text(first["constraint_name"]),
                kind,
                columns,
                _optional_text(first["definition"], MetadataState.UNAVAILABLE)
                if kind == ConstraintKind.CHECK or _text(first["definition"]) is not None
                else MetadataValue(MetadataState.NOT_APPLICABLE),
                target,
                target_columns,
            )
        )
    return tuple(constraints)


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
        result = execute(sql)
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
    columns = _rows(query(queries.columns))
    constraints = _rows(query(queries.constraints))
    properties = _rows(query(queries.properties)) if queries.properties is not None else []
    if not columns and not queries.allows_zero_columns:
        message = "Object columns are no longer available or are not visible."
        raise RuntimeError(message)
    if any(_integer(row["object_id"]) != object_id for row in (*columns, *constraints, *properties)):
        message = "The object changed while its properties were being loaded."
        raise RuntimeError(message)
    # Separate catalog queries are not a transactional DDL snapshot.
    final = query(queries.object)
    if not final.equals(initial):
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
                description=_description(column_properties, queries.description_property)
                if queries.description_property is not None
                else _optional_text(row["description"]),
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
        _description(object_properties, queries.description_property)
        if queries.description_property is not None
        else _optional_text(first["description"]),
        MetadataValue(MetadataState.AVAILABLE, object_properties)
        if queries.properties is not None
        else MetadataValue(MetadataState.UNSUPPORTED),
        tuple(output_columns),
        MetadataValue(MetadataState.NOT_APPLICABLE)
        if identity.kind == SchemaObjectKind.VIEW
        else MetadataValue(MetadataState.AVAILABLE, _constraints(constraints, resolved)),
    )
