from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from unittest.mock import MagicMock

import pytest

from expo_jbm329.db import base
from expo_jbm329.db.core.interfaces import DriverProtocol
from expo_jbm329.db.core.models import ConnectionConfig
from expo_jbm329.db.core.object_properties import (
    ColumnProperties,
    ConstraintKind,
    MetadataState,
    MetadataValue,
    NamedProperty,
    ObjectConstraint,
    ObjectProperties,
    ObjectPropertiesNotSupportedError,
    SchemaObjectIdentity,
    SchemaObjectKind,
)
from expo_jbm329.db.dialects.ansi import AnsiDialect
from expo_jbm329.db.service import DbService


@pytest.mark.parametrize("value", ["", False, 0, (), "Multiline\n<plain text>"])
def test_available_metadata_preserves_false_and_empty_values(value):
    metadata = MetadataValue(MetadataState.AVAILABLE, value)
    assert metadata.value == value
    assert metadata.state == MetadataState.AVAILABLE


@pytest.mark.parametrize("state", [state for state in MetadataState if state != MetadataState.AVAILABLE])
def test_missing_metadata_states_remain_distinct(state):
    metadata = MetadataValue[str](state)
    assert metadata.state == state
    assert metadata.value is None
    with pytest.raises(ValueError, match="non-None"):
        MetadataValue(state, "unexpected")


def test_available_metadata_requires_value():
    with pytest.raises(ValueError, match="non-None"):
        MetadataValue[str](MetadataState.AVAILABLE)


def make_column(name="item_id", ordinal_position=1, properties=()):
    return ColumnProperties(
        name=name,
        ordinal_position=ordinal_position,
        data_type=MetadataValue(MetadataState.AVAILABLE, "decimal(18, 4)"),
        nullable=MetadataValue(MetadataState.AVAILABLE, False),
        default=MetadataValue(MetadataState.ABSENT),
        description=MetadataValue(MetadataState.ABSENT),
        properties=MetadataValue(MetadataState.AVAILABLE, properties),
        identity=MetadataValue(MetadataState.NOT_APPLICABLE),
        generated=MetadataValue(MetadataState.UNSUPPORTED),
    )


def test_snapshot_preserves_property_scopes_order_and_nulls():
    identity = SchemaObjectIdentity("dbo", "Orders", SchemaObjectKind.TABLE, "Example")
    object_property = NamedProperty("MS_Description", MetadataValue(MetadataState.AVAILABLE, "Object"))
    column_property = NamedProperty("MS_Description", MetadataValue(MetadataState.AVAILABLE, "Column"))
    null_property = NamedProperty("Custom", MetadataValue(MetadataState.ABSENT))
    snapshot = ObjectProperties(
        identity=identity,
        description=object_property.value,
        properties=MetadataValue(MetadataState.AVAILABLE, (object_property,)),
        columns=(make_column(properties=(column_property, null_property)), make_column("tenant_id", 2)),
        constraints=MetadataValue(MetadataState.UNAVAILABLE),
    )
    assert snapshot.properties.value == (object_property,)
    assert snapshot.columns[0].properties.value == (column_property, null_property)
    assert [column.ordinal_position for column in snapshot.columns] == [1, 2]
    assert null_property.value.value is None
    assert snapshot.columns[0].nullable.value is False
    with pytest.raises(FrozenInstanceError):
        snapshot.identity = identity
    with pytest.raises(FrozenInstanceError):
        snapshot.columns[0].name = "changed"


@pytest.mark.parametrize("kind", [ConstraintKind.PRIMARY_KEY, ConstraintKind.UNIQUE])
def test_composite_key_is_a_single_ordered_constraint(kind):
    constraint = ObjectConstraint("key", kind, ("tenant_id", "item_id"), MetadataValue(MetadataState.ABSENT))
    assert constraint.columns == ("tenant_id", "item_id")
    assert constraint.referenced_object is None


def test_composite_foreign_key_preserves_target_mapping():
    target = SchemaObjectIdentity("other", "Items", SchemaObjectKind.TABLE, "Example")
    constraint = ObjectConstraint(
        "fk_items",
        ConstraintKind.FOREIGN_KEY,
        ("tenant_id", "item_id"),
        MetadataValue(MetadataState.ABSENT),
        target,
        ("tenant", "id"),
    )
    assert constraint.referenced_object == target
    assert tuple(zip(constraint.columns, constraint.referenced_columns, strict=True)) == (
        ("tenant_id", "tenant"),
        ("item_id", "id"),
    )
    with pytest.raises(ValueError, match="one target column"):
        replace(constraint, referenced_columns=("id",))
    with pytest.raises(ValueError, match="require a target"):
        replace(constraint, referenced_object=None)
    with pytest.raises(ValueError, match="Only foreign keys"):
        replace(constraint, kind=ConstraintKind.UNIQUE)
    unresolved = replace(constraint, referenced_columns=(), referenced_columns_state=MetadataState.UNAVAILABLE)
    assert unresolved.referenced_object == target
    with pytest.raises(ValueError, match="one target column"):
        replace(unresolved, referenced_columns_state=MetadataState.AVAILABLE)
    with pytest.raises(ValueError, match="one target column"):
        replace(unresolved, referenced_columns=("id",))
    with pytest.raises(ValueError, match="Only foreign keys"):
        replace(unresolved, kind=ConstraintKind.UNIQUE, referenced_object=None)


def test_check_can_preserve_definition_without_invented_column_mapping():
    constraint = ObjectConstraint(
        None, ConstraintKind.CHECK, (), MetadataValue(MetadataState.AVAILABLE, "total >= subtotal")
    )
    assert constraint.columns == ()
    assert constraint.definition.value == "total >= subtotal"
    with pytest.raises(ValueError, match="at least one column"):
        replace(constraint, kind=ConstraintKind.PRIMARY_KEY)


def test_expression_unique_key_requires_an_available_nonempty_definition():
    constraint = ObjectConstraint(
        "expression_key", ConstraintKind.UNIQUE, (), MetadataValue(MetadataState.AVAILABLE, "UNIQUE ((abs(amount)))")
    )
    assert constraint.columns == ()
    for definition in (MetadataValue(MetadataState.UNAVAILABLE), MetadataValue(MetadataState.AVAILABLE, "")):
        with pytest.raises(ValueError, match="at least one column"):
            replace(constraint, definition=definition)


def test_identity_and_column_validation():
    with pytest.raises(ValueError, match="name must not be empty"):
        SchemaObjectIdentity("dbo", "", SchemaObjectKind.VIEW)
    assert SchemaObjectIdentity("", " name ", SchemaObjectKind.VIEW).name == " name "
    with pytest.raises(ValueError, match="positive ordinal"):
        make_column(ordinal_position=0)
    with pytest.raises(ValueError, match="requires a name"):
        make_column(name="")


@pytest.mark.parametrize("dialect_type", [AnsiDialect])
@pytest.mark.parametrize("kind", list(SchemaObjectKind))
def test_unimplemented_provider_fails_explicitly_without_queries(dialect_type, kind, caplog):
    driver = MagicMock(spec=DriverProtocol)
    service = DbService(driver, dialect_type())
    conn = ConnectionConfig("Test", "sqlite", "sqlite")
    identity = SchemaObjectIdentity("main", "Object", kind)
    with pytest.raises(ObjectPropertiesNotSupportedError, match="not supported"):
        service.get_object_properties(conn, identity, corr_id="properties-test")
    driver.execute_df.assert_not_called()
    assert "properties-test" in caplog.text


def test_facade_delegates_to_existing_connection_service(monkeypatch):
    service = MagicMock(spec=DbService)
    conn = ConnectionConfig("Clicked", "sqlite", "sqlite")
    resolver = MagicMock(return_value=(service, conn))
    monkeypatch.setattr(base, "_get_service_with_config", resolver)
    identity = SchemaObjectIdentity("main", "View", SchemaObjectKind.VIEW)
    assert (
        base.get_object_properties("Clicked", identity, corr_id="request") is service.get_object_properties.return_value
    )
    resolver.assert_called_once_with("Clicked")
    service.get_object_properties.assert_called_once_with(conn, identity, corr_id="request")


def test_facade_preserves_explicit_unsupported_error(monkeypatch):
    driver = MagicMock(spec=DriverProtocol)
    service = DbService(driver, AnsiDialect())
    conn = ConnectionConfig("Other", "oracle", "odbc")
    monkeypatch.setattr(base, "_get_service_with_config", lambda _name: (service, conn))
    with pytest.raises(ObjectPropertiesNotSupportedError):
        base.get_object_properties("Other", SchemaObjectIdentity("", "Object", SchemaObjectKind.TABLE))
    driver.execute_df.assert_not_called()
