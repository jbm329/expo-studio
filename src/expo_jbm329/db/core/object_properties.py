"""Qt-free contracts for read-only database object metadata.

An absent value is distinct from metadata that is unsupported or could not be
retrieved. Availability describes catalog visibility, not proof that the user
can see every property held by the database.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class MetadataState(StrEnum):
    """Availability of an individual metadata field or collection."""

    AVAILABLE = "available"
    ABSENT = "absent"
    NOT_APPLICABLE = "not_applicable"
    UNSUPPORTED = "unsupported"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class MetadataValue[T]:
    """A metadata value with explicit availability.

    Attributes:
        state: Whether the catalog supplied a value and, if not, why.
        value: Retrieved value, including valid false or empty values.
    """

    state: MetadataState
    value: T | None = None

    def __post_init__(self) -> None:
        """Reject contradictory availability and value combinations."""
        if (self.state == MetadataState.AVAILABLE) != (self.value is not None):
            message = "Only available metadata must contain a non-None value."
            raise ValueError(message)


class SchemaObjectKind(StrEnum):
    """Schema object kinds supported by the Properties feature."""

    TABLE = "table"
    VIEW = "view"


@dataclass(frozen=True)
class SchemaObjectIdentity:
    """Identity within a connection's catalog.

    Attributes:
        schema: Schema name; empty only for engines without a schema namespace.
        name: Unquoted object name.
        kind: Table or view, as discovered in the schema browser.
        catalog: Catalog name when supplied by the provider.
    """

    schema: str
    name: str
    kind: SchemaObjectKind
    catalog: str | None = None

    def __post_init__(self) -> None:
        """Reject an empty object name without altering quoted-name whitespace."""
        if not self.name:
            message = "Schema object name must not be empty."
            raise ValueError(message)


@dataclass(frozen=True)
class NamedProperty:
    """Named object or column property, owned by its containing metadata value.

    Attributes:
        name: Original catalog property name, without translation.
        value: Plain-text representation or explicit absence for SQL NULL.
    """

    name: str
    value: MetadataValue[str]


class ConstraintKind(StrEnum):
    """Declared constraints, independent of display labels."""

    PRIMARY_KEY = "primary_key"
    FOREIGN_KEY = "foreign_key"
    UNIQUE = "unique"
    CHECK = "check"


@dataclass(frozen=True)
class ObjectConstraint:
    """A whole constraint, preserving composite column order.

    Attributes:
        name: Catalog name, or None for an unnamed constraint.
        kind: Declared constraint kind.
        columns: Participating columns in constraint order, not separate keys.
            Empty when a table-level CHECK has no known column mapping.
        definition: Catalog expression or definition, when available.
        referenced_object: Foreign-key target, otherwise None.
        referenced_columns: Foreign-key targets paired by position with columns.
    """

    name: str | None
    kind: ConstraintKind
    columns: tuple[str, ...]
    definition: MetadataValue[str]
    referenced_object: SchemaObjectIdentity | None = None
    referenced_columns: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Reject malformed foreign-key mappings and empty key constraints."""
        if self.kind != ConstraintKind.CHECK and not self.columns:
            message = "Key constraints must contain at least one column."
            raise ValueError(message)
        if self.kind == ConstraintKind.FOREIGN_KEY:
            if self.referenced_object is None or len(self.columns) != len(self.referenced_columns):
                message = "Foreign keys require a target and one target column per source column."
                raise ValueError(message)
        elif self.referenced_object is not None or self.referenced_columns:
            message = "Only foreign keys may contain a referenced object or columns."
            raise ValueError(message)


@dataclass(frozen=True)
class ColumnProperties:
    """Column metadata in database ordinal order.

    Attributes:
        name: Original column name.
        ordinal_position: One-based position in the database object.
        data_type: Complete declared type, including available size/precision.
        nullable: Catalog nullability, without inferring from underlying tables.
        default: Default SQL expression, not an evaluated Python value.
        description: Native comment or conventional description.
        properties: All named properties in this column's scope.
        identity: Identity specification, where supported.
        generated: Generated/computed expression, where supported.
    """

    name: str
    ordinal_position: int
    data_type: MetadataValue[str]
    nullable: MetadataValue[bool]
    default: MetadataValue[str]
    description: MetadataValue[str]
    properties: MetadataValue[tuple[NamedProperty, ...]]
    identity: MetadataValue[str]
    generated: MetadataValue[str]

    def __post_init__(self) -> None:
        """Reject invalid column identity and ordinal position."""
        if not self.name or self.ordinal_position < 1:
            message = "Column metadata requires a name and a positive ordinal position."
            raise ValueError(message)


@dataclass(frozen=True)
class ObjectProperties:
    """A read-only catalog snapshot, without connection credentials or UI state.

    Attributes:
        identity: Catalog identity of the inspected object.
        description: Native comment or conventional description.
        properties: All named properties in the object's scope.
        columns: Columns in database order.
        constraints: Whole constraints, never flattened into independent keys.
            Unsupported constraint details retain their own availability state.
    """

    identity: SchemaObjectIdentity
    description: MetadataValue[str]
    properties: MetadataValue[tuple[NamedProperty, ...]]
    columns: tuple[ColumnProperties, ...]
    constraints: MetadataValue[tuple[ObjectConstraint, ...]]


class ObjectPropertiesNotSupportedError(NotImplementedError):
    """Raised when the selected engine has no object-properties provider."""


@dataclass(frozen=True)
class ObjectPropertiesQueries:
    """Catalog queries returning the common object-properties row shapes.

    Object rows contain ``catalog_name``, ``schema_name``, ``object_name``,
    ``object_id`` and ``modify_date``. Column rows contain ``object_id``,
    ``column_id``, ``column_name``, ``ordinal_position``, ``data_type``,
    ``nullable`` and the ``default``, ``identity`` and ``generated`` pairs
    of ``<prefix>_present``/``<prefix>_definition`` fields.

    Constraint rows contain ``object_id``, ``constraint_id``,
    ``constraint_name``, ``constraint_kind`` (a ConstraintKind value),
    ``column_position``, ``column_name``, ``definition`` and nullable
    ``referenced_schema``, ``referenced_object`` and ``referenced_column``.
    Property rows contain ``object_id``, ``column_id`` (zero for the object),
    ``property_name`` and nullable plain-text ``property_value``.

    Attributes:
        object: Identity/version query, also repeated to detect concurrent DDL.
        columns: Ordered columns with complete types and expression visibility.
        constraints: One row per constraint column, grouped by constraint ID.
        properties: Named object/column properties with plain-text values.
            None when native named properties are unsupported.
        description_property: Named property used as the description. None
            selects native ``description`` fields in object and column rows.
        allows_zero_columns: Whether the engine permits objects without columns.
    """

    object: str
    columns: str
    constraints: str
    properties: str | None
    description_property: str | None = "MS_Description"
    allows_zero_columns: bool = False
