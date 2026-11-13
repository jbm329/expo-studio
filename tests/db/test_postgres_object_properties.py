from __future__ import annotations

from dataclasses import replace
from unittest.mock import MagicMock

import pandas as pd
import pytest
import sqlglot

from expo_jbm329.db.core.interfaces import DriverProtocol, ObjectPropertiesDialectProtocol
from expo_jbm329.db.core.models import ConnectionConfig, SqlError, SqlResult
from expo_jbm329.db.core.object_properties import ConstraintKind, MetadataState, SchemaObjectIdentity, SchemaObjectKind
from expo_jbm329.db.dialects.postgres import PostgresDialect
from expo_jbm329.db.object_properties import load_object_properties
from expo_jbm329.db.service import DbService


@pytest.fixture
def identity():
    return SchemaObjectIdentity("sales", "Orders", SchemaObjectKind.TABLE, "Example")


def column(number=1, **overrides):
    return {
        "object_id": 42,
        "column_id": number,
        "column_name": f"column_{number}",
        "ordinal_position": number,
        "data_type": "numeric(18,4)",
        "nullable": False,
        "description": None,
        "default_present": False,
        "default_definition": None,
        "identity_present": False,
        "identity_definition": None,
        "generated_present": False,
        "generated_definition": None,
    } | overrides


def constraint(number=1, **overrides):
    return {
        "object_id": 42,
        "constraint_id": number,
        "constraint_name": "constraint",
        "constraint_kind": "primary_key",
        "column_position": 1,
        "column_name": "column_1",
        "definition": "PRIMARY KEY (column_1, column_2)",
        "referenced_schema": None,
        "referenced_object": None,
        "referenced_column": None,
    } | overrides


def executor(columns=None, constraints=None, comment="Object\n<b>comment</b>"):
    header = pd.DataFrame([
        {
            "catalog_name": "Example",
            "schema_name": "sales",
            "object_name": "Orders",
            "object_id": 42,
            "modify_date": "100|101|102|103|104",
            "description": comment,
        }
    ])
    frames = [
        header,
        pd.DataFrame([column()] if columns is None else columns),
        pd.DataFrame(constraints or []),
        header.copy(),
    ]
    return MagicMock(side_effect=[SqlResult(ok=True, data=frame) for frame in frames])


def load(identity, execute):
    return load_object_properties(identity, PostgresDialect().sql_object_properties(identity), execute)


@pytest.mark.parametrize("kind", list(SchemaObjectKind))
def test_queries_are_scoped_read_only_postgres_catalog_selects(kind):
    identity = SchemaObjectIdentity("sch'ema\\", "Örders'; DROP TABLE x;--", kind, "Cat'alog")
    queries = PostgresDialect().sql_object_properties(identity)
    assert queries.properties is None and queries.description_property is None
    for sql in (queries.object, queries.columns, queries.constraints):
        parsed = sqlglot.parse(sql, read="postgres")
        assert len(parsed) == 1
        assert isinstance(parsed[0], sqlglot.exp.Select)
        assert "n.nspname = E'sch''ema\\\\'" in sql
        assert "c.relname = E'Örders''; DROP TABLE x;--'" in sql
        assert "pg_catalog.current_database() = E'Cat''alog'" in sql
        assert "('r', 'p')" in sql if kind == SchemaObjectKind.TABLE else "('v')" in sql
        assert all(table.db == "pg_catalog" for table in parsed[0].find_all(sqlglot.exp.Table) if table.db)
    assert "format_type(a.atttypid, a.atttypmod)" in queries.columns
    assert "a.attnotnull OR COALESCE(t.typnotnull, false)" in queries.columns
    assert "NOT a.attisdropped" in queries.columns
    assert "a.attnum > 0" in queries.columns
    assert "WITH ORDINALITY" in queries.constraints
    assert "k.confkey[key.position::integer]" in queries.constraints
    assert "pg_catalog.col_description(o.oid, a.attnum)" in queries.columns
    assert "to_jsonb(a)->>'attidentity'" in queries.columns
    assert "to_jsonb(a)->>'attgenerated'" in queries.columns
    assert "pg_catalog.pg_get_expr(ad.adbin, ad.adrelid)" in queries.columns


def test_optional_capability_uses_distinct_schema_and_catalog_scope(identity):
    dialect = PostgresDialect()
    assert isinstance(dialect, ObjectPropertiesDialectProtocol)
    sql = dialect.sql_object_properties(identity).object
    assert sql != dialect.sql_object_properties(replace(identity, schema="other")).object
    assert "current_database() =" not in dialect.sql_object_properties(replace(identity, catalog=None)).object
    for catalog in ("pg_attribute", "pg_description", "pg_constraint", "pg_attrdef"):
        assert catalog in sql


def test_native_comments_not_synthesized_as_extended_properties(identity):
    execute = executor(
        columns=[
            column(3, description="Column\n<comment>", nullable=True),
            column(1, description=None),
        ]
    )
    result = load(identity, execute)
    assert result.description.value == "Object\n<b>comment</b>"
    assert result.properties.state == MetadataState.UNSUPPORTED
    assert [col.ordinal_position for col in result.columns] == [1, 3]
    assert result.columns[0].description.state == MetadataState.ABSENT
    assert result.columns[1].description.value == "Column\n<comment>"
    assert all(col.properties.state == MetadataState.UNSUPPORTED for col in result.columns)
    assert result.columns[0].nullable.value is False
    assert result.columns[1].nullable.value is True
    assert execute.call_count == 4


@pytest.mark.parametrize("comment", [None, pd.NA, float("nan"), ""])
def test_null_and_empty_comments_are_distinct(identity, comment):
    result = load(identity, executor(comment=comment, columns=[column(description=comment)]))
    expected = MetadataState.AVAILABLE if isinstance(comment, str) else MetadataState.ABSENT
    assert result.description.state == expected
    assert result.columns[0].description.state == expected


@pytest.mark.parametrize(
    "data_type",
    [
        "character varying(50)",
        "numeric(18,4)",
        "timestamp(3) with time zone",
        "integer[]",
        '"Custom"."Status"',
        '"Custom"."PositiveAmount"',
        "text",
    ],
)
def test_formatted_types_remain_unchanged(identity, data_type):
    result = load(identity, executor(columns=[column(data_type=data_type)]))
    assert result.columns[0].data_type.value == data_type


def test_defaults_identity_and_generated_expression_metadata(identity):
    result = load(
        identity,
        executor(
            columns=[
                column(default_present=True, default_definition="nextval('orders_id_seq'::regclass)"),
                column(2, identity_present=True, identity_definition="GENERATED ALWAYS AS IDENTITY"),
                column(3, generated_present=True, generated_definition="(subtotal + tax)"),
                column(4, default_present=True, default_definition=None),
            ]
        ),
    )
    assert result.columns[0].default.value == "nextval('orders_id_seq'::regclass)"
    assert result.columns[1].identity.value == "GENERATED ALWAYS AS IDENTITY"
    assert result.columns[1].default.state == MetadataState.ABSENT
    assert result.columns[2].generated.value == "(subtotal + tax)"
    assert result.columns[3].default.state == MetadataState.UNAVAILABLE


def test_composite_constraints_preserve_definitions_and_fk_pair_order(identity):
    rows = [
        constraint(column_position=2, column_name="column_2"),
        constraint(),
        constraint(2, constraint_kind="unique", definition="UNIQUE (column_1, column_2)"),
        constraint(
            2,
            constraint_kind="unique",
            definition="UNIQUE (column_1, column_2)",
            column_position=2,
            column_name="column_2",
        ),
        constraint(
            3,
            constraint_kind="foreign_key",
            referenced_schema="other",
            referenced_object="Items",
            referenced_column="tenant",
            definition="FOREIGN KEY (column_1, column_2) REFERENCES other.Items",
        ),
        constraint(
            3,
            constraint_kind="foreign_key",
            referenced_schema="other",
            referenced_object="Items",
            referenced_column="id",
            column_position=2,
            column_name="column_2",
        ),
        constraint(4, constraint_kind="check", column_name=None, definition="CHECK (true)"),
    ]
    result = load(identity, executor(columns=[column(), column(2)], constraints=rows))
    pk, unique, fk, check = result.constraints.value
    assert pk.columns == unique.columns == fk.columns == ("column_1", "column_2")
    assert pk.definition.value == "PRIMARY KEY (column_1, column_2)"
    assert fk.kind == ConstraintKind.FOREIGN_KEY
    assert fk.referenced_object == SchemaObjectIdentity("other", "Items", SchemaObjectKind.TABLE, "Example")
    assert fk.referenced_columns == ("tenant", "id")
    assert check.columns == () and check.definition.value == "CHECK (true)"


@pytest.mark.parametrize("value", [True, 123, b"comment"])
def test_invalid_comment_values_are_not_silently_stringified(identity, value):
    with pytest.raises(TypeError, match="Catalog text"):
        load(identity, executor(comment=value))


def test_constraint_rows_from_replaced_object_are_rejected(identity):
    with pytest.raises(RuntimeError, match="object changed"):
        load(identity, executor(constraints=[constraint(object_id=43)]))


def test_view_comments_and_zero_column_objects(identity):
    result = load(replace(identity, kind=SchemaObjectKind.VIEW), executor())
    assert result.description.value == "Object\n<b>comment</b>"
    assert result.constraints.state == MetadataState.NOT_APPLICABLE
    result = load(identity, executor(columns=[]))
    assert result.columns == ()


@pytest.mark.parametrize("stage", range(4))
def test_catalog_failures_never_return_partial_success(identity, stage):
    execute = executor()
    results = list(execute.side_effect)
    results[stage] = SqlResult(ok=False, error=SqlError("permission", None, "Permission denied.", None))
    execute.side_effect = results
    with pytest.raises(RuntimeError, match="Permission denied"):
        load(identity, execute)
    assert execute.call_count == stage + 1


def test_missing_object_and_changed_catalog_version_are_explicit(identity):
    execute = executor()
    results = list(execute.side_effect)
    results[0] = SqlResult(ok=True, data=pd.DataFrame())
    execute.side_effect = results
    with pytest.raises(RuntimeError, match="does not exist or is not visible"):
        load(identity, execute)
    execute = executor()
    results = list(execute.side_effect)
    results[-1].data["modify_date"] = "changed"
    execute.side_effect = results
    with pytest.raises(RuntimeError, match="object changed"):
        load(identity, execute)


def test_service_uses_existing_driver_and_correlation_without_limits(identity):
    execute = executor()
    driver = MagicMock(spec=DriverProtocol)
    driver.execute_df.side_effect = [result.data for result in execute.side_effect]
    service = DbService(driver, PostgresDialect())
    connection = ConnectionConfig("Postgres", "postgresql", "psycopg")
    result = service.get_object_properties(connection, identity, corr_id="postgres-properties")
    assert result.identity == identity
    assert driver.execute_df.call_count == 4
    for call in driver.execute_df.call_args_list:
        assert call.args[0] is connection
        assert call.kwargs["corr_id"] == "postgres-properties"
        assert " LIMIT " not in call.args[1]
