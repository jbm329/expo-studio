from __future__ import annotations

from dataclasses import replace
from unittest.mock import patch

import duckdb
import pytest
import sqlglot
from sqlalchemy.exc import DBAPIError

from expo_jbm329.db import base
from expo_jbm329.db.core.models import ConnectionConfig
from expo_jbm329.db.core.object_properties import ConstraintKind, MetadataState, SchemaObjectIdentity, SchemaObjectKind
from expo_jbm329.db.dialects.duckdb import DuckDbDialect
from expo_jbm329.db.drivers.sa_duckdb import SqlAlchemyDuckDbDriver
from expo_jbm329.db.service import DbService


@pytest.fixture
def database(tmp_path):
    path = tmp_path / "properties café.duckdb"
    with duckdb.connect(str(path)) as connection:
        connection.execute("""
            CREATE SCHEMA sales;
            CREATE SCHEMA "it's";
            CREATE TABLE main.child (other_column INTEGER);
            CREATE TABLE sales.parent (tenant INTEGER, id INTEGER, PRIMARY KEY (tenant, id));
            CREATE SEQUENCE sales.ids;
            CREATE TABLE sales.child (
                tenant INTEGER NOT NULL,
                id INTEGER DEFAULT nextval('sales.ids'),
                label VARCHAR DEFAULT 'O''Brien',
                amount DECIMAL(18,4) DEFAULT 1.25,
                computed AS (amount * 2),
                tags VARCHAR[],
                payload STRUCT(x INTEGER, y VARCHAR),
                UNIQUE (tenant, id),
                FOREIGN KEY (tenant, id) REFERENCES sales.parent(tenant, id),
                CHECK (amount > 0),
                CHECK (true)
            );
            COMMENT ON TABLE sales.child IS 'Object <b>comment</b>
second line';
            COMMENT ON COLUMN sales.child.amount IS 'Amount <comment>';
            CREATE VIEW sales.child_view AS SELECT tenant, amount FROM sales.child;
            COMMENT ON VIEW sales.child_view IS 'View comment';
            COMMENT ON COLUMN sales.child_view.amount IS 'View column comment';
            CREATE UNIQUE INDEX separate_index ON sales.child(label);
            CREATE TABLE "it's"."o'x" ("a""b" INTEGER);
        """)
    driver = SqlAlchemyDuckDbDriver()
    service = DbService(driver, DuckDbDialect())
    config = ConnectionConfig("DuckDB", "duckdb", "duckdb", database=str(path))
    yield service, config, path
    driver.dispose()


def load(database, name="child", *, schema="sales", kind=SchemaObjectKind.TABLE, catalog=None):
    service, config, _ = database
    return service.get_object_properties(
        config, SchemaObjectIdentity(schema, name, kind, catalog), corr_id="duckdb-properties"
    )


def test_real_read_only_file_comments_types_defaults_and_generated_metadata(database):
    result = load(database)
    assert result.identity.schema == "sales" and result.identity.name == "child"
    assert result.description.value == "Object <b>comment</b>\nsecond line"
    assert result.properties.state == MetadataState.UNSUPPORTED
    assert [col.name for col in result.columns] == ["tenant", "id", "label", "amount", "computed", "tags", "payload"]
    assert [col.ordinal_position for col in result.columns] == list(range(1, 8))
    assert result.columns[0].nullable.value is False
    assert result.columns[1].nullable.value is True
    assert result.columns[0].description.state == MetadataState.ABSENT
    assert result.columns[2].default.value == "'O''Brien'"
    assert result.columns[3].data_type.value == "DECIMAL(18,4)"
    assert result.columns[3].description.value == "Amount <comment>"
    assert result.columns[5].data_type.value == "VARCHAR[]"
    assert result.columns[6].data_type.value == "STRUCT(x INTEGER, y VARCHAR)"
    assert "nextval" in result.columns[1].default.value
    assert result.columns[4].default.state == MetadataState.ABSENT
    assert "amount * 2" in result.columns[4].generated.value
    assert result.columns[0].generated.state == MetadataState.NOT_APPLICABLE
    assert all(col.identity.state == col.properties.state == MetadataState.UNSUPPORTED for col in result.columns)
    assert load(database).identity == result.identity


def test_whole_constraints_keep_native_definitions_and_fk_pair_order(database):
    result = load(database)
    keys = result.constraints.value
    unique = next(key for key in keys if key.kind == ConstraintKind.UNIQUE)
    fk = next(key for key in keys if key.kind == ConstraintKind.FOREIGN_KEY)
    checks = [key for key in keys if key.kind == ConstraintKind.CHECK]
    assert unique.columns == fk.columns == ("tenant", "id")
    assert unique.definition.value == "UNIQUE(tenant, id)"
    assert fk.referenced_object == SchemaObjectIdentity(
        "sales", "parent", SchemaObjectKind.TABLE, result.identity.catalog
    )
    assert fk.referenced_columns == ("tenant", "id")
    assert fk.definition.value.startswith("FOREIGN KEY")
    assert len(checks) == 2
    assert checks[0].columns == ("amount",)
    assert checks[1].columns == ()
    assert all(key.name and key.definition.state == MetadataState.AVAILABLE for key in keys)
    assert len(keys) == 4
    pk = load(database, "parent").constraints.value[0]
    assert pk.kind == ConstraintKind.PRIMARY_KEY and pk.columns == ("tenant", "id")
    assert all(col.nullable.value is False for col in load(database, "parent").columns)


def test_view_has_its_own_comments_not_inherited_constraints(database):
    result = load(database, "child_view", kind=SchemaObjectKind.VIEW)
    assert result.description.value == "View comment"
    assert result.columns[1].description.value == "View column comment"
    assert result.constraints.state == result.check_constraints_state == MetadataState.NOT_APPLICABLE
    assert result.columns[0].description.state == MetadataState.ABSENT


def test_same_names_in_different_schemas_and_quoted_names(database):
    assert [col.name for col in load(database, schema="main").columns] == ["other_column"]
    result = load(database, "o'x", schema="it's")
    assert result.columns[0].name == 'a"b'


@pytest.mark.parametrize("name", ["Örders'\"; DROP TABLE parent;--", "100%\\name", "has space"])
def test_unusual_identifiers_are_scoped_literals(database, name):
    _, _, path = database
    dialect = DuckDbDialect()
    with duckdb.connect(str(path)) as connection:
        connection.execute(f"CREATE TABLE sales.{dialect.quote_ident(name)} (id INTEGER)")
    assert load(database, name).identity.name == name
    assert load(database, "parent").columns


@pytest.mark.parametrize(
    "name,kind,catalog",
    [
        ("missing", SchemaObjectKind.TABLE, None),
        ("child", SchemaObjectKind.VIEW, None),
        ("child_view", SchemaObjectKind.TABLE, None),
        ("child", SchemaObjectKind.TABLE, "other"),
    ],
)
def test_missing_wrong_kind_or_catalog_is_explicit(database, name, kind, catalog):
    with pytest.raises(RuntimeError, match="does not exist or is not visible"):
        load(database, name, kind=kind, catalog=catalog)


def test_no_user_rows_or_statistics_are_read_and_driver_stays_read_only(database):
    service, config, _ = database
    with patch.object(service.driver, "execute_df", wraps=service.driver.execute_df) as execute:
        result = load(database)
    assert execute.call_count == 6
    for call in execute.call_args_list:
        assert call.args[0] is config
        assert call.kwargs["corr_id"] == "duckdb-properties"
        assert " LIMIT " not in call.args[1]
        assert "estimated_size" not in call.args[1]
        assert "FROM sales.child" not in call.args[1]
    with pytest.raises(DBAPIError, match="read-only"):
        service.driver.execute_df(config, "CREATE TABLE forbidden (x INTEGER)")
    assert load(database, catalog=result.identity.catalog).identity == result.identity


@pytest.mark.parametrize("stage", range(6))
def test_metadata_query_failures_never_return_partial_success(database, stage):
    service, _, _ = database
    execute = service.driver.execute_df
    calls = 0

    def failing_execute(*args, **kwargs):
        nonlocal calls
        current = calls
        calls += 1
        if current == stage:
            message = "catalog query denied"
            raise RuntimeError(message)
        return execute(*args, **kwargs)

    with (
        patch.object(service.driver, "execute_df", side_effect=failing_execute),
        pytest.raises(RuntimeError),
    ):
        load(database)
    assert calls == stage + 1


@pytest.mark.parametrize(
    "change",
    [
        "COMMENT ON COLUMN sales.child.amount IS 'changed'",
        "COMMENT ON TABLE sales.child IS 'changed'",
        "ALTER TABLE sales.child ADD COLUMN changed INTEGER",
    ],
)
def test_catalog_change_is_detected(database, change):
    service, _, path = database
    execute = service.driver.execute_df
    calls = 0

    def changing_execute(*args, **kwargs):
        nonlocal calls
        frame = execute(*args, **kwargs)
        calls += 1
        if calls == 3:
            with duckdb.connect(str(path)) as connection:
                connection.execute(change)
        return frame

    with (
        patch.object(service.driver, "execute_df", side_effect=changing_execute),
        pytest.raises(RuntimeError, match="object changed"),
    ):
        load(database)


@pytest.mark.parametrize("kind", list(SchemaObjectKind))
def test_queries_parse_as_read_only_duckdb_catalog_selects(kind):
    identity = SchemaObjectIdentity("sch'ema", "Örders'; DROP TABLE x;--", kind, "catalog")
    queries = DuckDbDialect().sql_object_properties(identity)
    for sql in (queries.object, queries.columns, queries.constraints):
        expressions = sqlglot.parse(sql, read="duckdb")
        assert len(expressions) == 1 and isinstance(expressions[0], sqlglot.exp.Select)
        assert "schema_name = 'sch''ema'" in sql
        assert "database_name = current_database()" in sql
        assert "database_name = 'catalog'" in sql
    assert queries.properties is None and queries.description_property is None
    assert queries.verify_catalog_rows
    assert queries.object != DuckDbDialect().sql_object_properties(replace(identity, schema="other")).object


def test_facade_uses_registered_read_only_provider(database):
    _, config, path = database
    with patch(
        "expo_jbm329.db.base.read_connections",
        return_value={config.name: {"db_type": "duckdb", "database": str(path)}},
    ):
        try:
            result = base.get_object_properties(
                config.name,
                SchemaObjectIdentity("sales", "child", SchemaObjectKind.TABLE),
                corr_id="duckdb-facade",
            )
            assert result.description.value == "Object <b>comment</b>\nsecond line"
            assert result.columns[3].data_type.value == "DECIMAL(18,4)"
        finally:
            base.close_connection(config.name)


def test_reversed_fk_mapping_enum_type_and_empty_comments(database):
    _, _, path = database
    with duckdb.connect(str(path)) as connection:
        connection.execute("""
            CREATE TYPE sales.size AS ENUM ('small', 'large');
            CREATE TABLE sales.reverse_parent (tenant INTEGER, id INTEGER, PRIMARY KEY (id, tenant));
            CREATE TABLE sales.reversed (
                a INTEGER, b INTEGER, category sales.size,
                FOREIGN KEY (a, b) REFERENCES sales.reverse_parent(id, tenant)
            );
            COMMENT ON TABLE sales.reversed IS '';
            COMMENT ON COLUMN sales.reversed.category IS '';
        """)
    result = load(database, "reversed")
    fk = result.constraints.value[0]
    assert fk.columns == ("a", "b")
    assert fk.referenced_columns == ("id", "tenant")
    assert result.columns[2].data_type.value == "ENUM('small', 'large')"
    assert result.description.state == MetadataState.AVAILABLE and result.description.value == ""
    assert result.columns[2].description.value == ""
