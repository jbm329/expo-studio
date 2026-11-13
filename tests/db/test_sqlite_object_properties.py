from __future__ import annotations

import sqlite3
from unittest.mock import patch

import pytest
from sqlalchemy.exc import OperationalError

from expo_jbm329.db.core.models import ConnectionConfig
from expo_jbm329.db.core.object_properties import ConstraintKind, MetadataState, SchemaObjectIdentity, SchemaObjectKind
from expo_jbm329.db.dialects.sqlite import SqliteDialect
from expo_jbm329.db.drivers.sa_sqlite import SqlAlchemySqliteDriver
from expo_jbm329.db.service import DbService


@pytest.fixture
def database(tmp_path):
    path = tmp_path / "properties.db"
    with sqlite3.connect(path) as connection:
        connection.executescript("""
            CREATE TABLE parent (
                tenant INTEGER, item INTEGER,
                PRIMARY KEY (tenant, item)
            ) WITHOUT ROWID;
            CREATE TABLE child (
                id INTEGER PRIMARY KEY,
                tenant INTEGER NOT NULL,
                item INTEGER,
                label VARCHAR(50) DEFAULT 'O''Brien',
                amount DECIMAL(18,4) DEFAULT (1 + 2),
                total REAL GENERATED ALWAYS AS (amount * 2) STORED,
                virtual_total REAL GENERATED ALWAYS AS (amount * 3) VIRTUAL,
                untyped,
                CONSTRAINT uq UNIQUE (tenant, item),
                CONSTRAINT fk FOREIGN KEY (tenant, item) REFERENCES parent,
                CHECK (amount >= 0)
            );
            CREATE VIEW child_view AS SELECT id, label, amount FROM child;
            CREATE TABLE nullable_pk (id TEXT PRIMARY KEY, label TEXT);
            CREATE TABLE descending_pk (id INTEGER PRIMARY KEY DESC);
            CREATE TABLE strict_pk (id TEXT PRIMARY KEY) STRICT;
            CREATE UNIQUE INDEX separate_unique ON child(label);
        """)
    driver = SqlAlchemySqliteDriver()
    config = ConnectionConfig("SQLite", "sqlite", "sqlite", database=str(path))
    service = DbService(driver, SqliteDialect())
    yield service, config, path
    driver.dispose()


def load(database, name="child", *, kind=SchemaObjectKind.TABLE, schema="main", catalog=None):
    service, config, _ = database
    return service.get_object_properties(
        config, SchemaObjectIdentity(schema, name, kind, catalog), corr_id="sqlite-properties"
    )


def test_real_metadata_types_comments_defaults_and_generated_columns(database):
    result = load(database)
    assert result.identity == SchemaObjectIdentity("main", "child", SchemaObjectKind.TABLE, "main")
    assert result.description.state == MetadataState.UNSUPPORTED
    assert result.properties.state == MetadataState.UNSUPPORTED
    assert [col.name for col in result.columns] == [
        "id",
        "tenant",
        "item",
        "label",
        "amount",
        "total",
        "virtual_total",
        "untyped",
    ]
    assert [col.ordinal_position for col in result.columns] == list(range(1, 9))
    assert result.columns[3].data_type.value == "VARCHAR(50)"
    assert result.columns[4].data_type.value == "DECIMAL(18,4)"
    assert result.columns[7].data_type.value == ""
    assert result.columns[3].default.value == "'O''Brien'"
    assert result.columns[4].default.value == "1 + 2"
    assert result.columns[0].default.state == MetadataState.ABSENT
    assert result.columns[5].generated.state == result.columns[6].generated.state == MetadataState.UNAVAILABLE
    assert result.columns[0].generated.state == MetadataState.NOT_APPLICABLE
    assert all(col.identity.state == MetadataState.UNSUPPORTED for col in result.columns)
    assert all(col.description.state == col.properties.state == MetadataState.UNSUPPORTED for col in result.columns)
    assert result.check_constraints_state == MetadataState.UNAVAILABLE


def test_native_nullability_preserves_legacy_pk_exceptions(database):
    result = load(database)
    assert result.columns[0].nullable.value is False
    assert result.columns[1].nullable.value is False
    assert result.columns[2].nullable.value is True
    assert all(col.nullable.value is False for col in load(database, "parent").columns)
    assert load(database, "nullable_pk").columns[0].nullable.value is True
    assert load(database, "descending_pk").columns[0].nullable.value is True
    assert load(database, "strict_pk").columns[0].nullable.value is False


def test_composite_keys_and_implicit_foreign_target_mapping(database):
    result = load(database)
    constraints = {constraint.kind: constraint for constraint in result.constraints.value}
    pk = constraints[ConstraintKind.PRIMARY_KEY]
    unique = constraints[ConstraintKind.UNIQUE]
    fk = constraints[ConstraintKind.FOREIGN_KEY]
    assert pk.columns == ("id",)
    assert pk.name is None
    assert unique.columns == ("tenant", "item")
    assert unique.name.startswith("sqlite_autoindex_")
    assert fk.name is None
    assert fk.columns == fk.referenced_columns == ("tenant", "item")
    assert fk.referenced_object == SchemaObjectIdentity("main", "parent", SchemaObjectKind.TABLE, "main")
    assert pk.definition.state == fk.definition.state == MetadataState.NOT_APPLICABLE
    assert ConstraintKind.CHECK not in constraints
    assert len(result.constraints.value) == 3


def test_view_does_not_inherit_comments_or_constraints(database):
    result = load(database, "child_view", kind=SchemaObjectKind.VIEW)
    assert [col.name for col in result.columns] == ["id", "label", "amount"]
    assert result.constraints.state == MetadataState.NOT_APPLICABLE
    assert result.check_constraints_state == MetadataState.NOT_APPLICABLE
    assert result.description.state == MetadataState.UNSUPPORTED


@pytest.mark.parametrize("name", ["Örders'\"; DROP TABLE parent;--", "has space", "100%_table", "back\\slash"])
def test_unusual_identifiers_are_literal_safe(database, name):
    _, _, path = database
    quoted = SqliteDialect().quote_ident(name)
    with sqlite3.connect(path) as connection:
        connection.execute(f"CREATE TABLE {quoted} (\"strange'column\" TEXT DEFAULT '100%')")
    result = load(database, name)
    assert result.identity.name == name
    assert result.columns[0].name == "strange'column"
    assert result.columns[0].default.value == "'100%'"
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
def test_missing_wrong_kind_or_catalog_fails_explicitly(database, name, kind, catalog):
    with pytest.raises(RuntimeError, match="does not exist or is not visible"):
        load(database, name, kind=kind, catalog=catalog)


def test_empty_schema_resolves_main(database):
    assert load(database, schema="").identity.schema == "main"


def test_explicit_foreign_keys_and_same_target_column_order(database):
    _, _, path = database
    with sqlite3.connect(path) as connection:
        connection.executescript("""
            CREATE TABLE explicit_child (
                a INTEGER, b INTEGER,
                FOREIGN KEY(a, b) REFERENCES parent(item, tenant)
            );
        """)
    fk = load(database, "explicit_child").constraints.value[0]
    assert fk.columns == ("a", "b")
    assert fk.referenced_columns == ("item", "tenant")


def test_only_read_queries_use_existing_executor_with_correlation(database):
    service, config, path = database
    with patch.object(service.driver, "execute_df", wraps=service.driver.execute_df) as execute:
        load(database)
    assert execute.call_count == 6
    for call in execute.call_args_list:
        assert call.args[0] is config
        assert call.args[1].startswith("WITH target AS (SELECT")
        assert call.kwargs["corr_id"] == "sqlite-properties"
        assert " LIMIT " not in call.args[1]
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM child").fetchone()[0] == 0


def test_schema_ddl_change_is_detected(database):
    service, _, path = database
    execute = service.driver.execute_df
    calls = 0

    def changing_execute(*args, **kwargs):
        nonlocal calls
        result = execute(*args, **kwargs)
        calls += 1
        if calls == 3:
            with sqlite3.connect(path) as connection:
                connection.execute("ALTER TABLE child ADD COLUMN changed TEXT")
        return result

    with (
        patch.object(service.driver, "execute_df", side_effect=changing_execute),
        pytest.raises(RuntimeError, match="object changed"),
    ):
        load(database)


@pytest.mark.parametrize("schema", ["other", "Öther'\" db"])
def test_attached_schema_qualified_identity_is_not_confused_with_main(database, tmp_path, schema):
    service, config, _ = database
    attached = tmp_path / "attached.db"
    with sqlite3.connect(attached) as connection:
        connection.executescript("CREATE TABLE child (attached_only TEXT);")
    engine = service.driver._get_engine(config)
    with engine.connect() as connection:
        connection.exec_driver_sql(f"ATTACH DATABASE ? AS {SqliteDialect().quote_ident(schema)}", (str(attached),))
    assert [col.name for col in load(database, schema=schema).columns] == ["attached_only"]
    assert [col.name for col in load(database).columns][0] == "id"


def test_implicit_missing_parent_key_mapping_is_unavailable_not_fabricated(database):
    _, _, path = database
    with sqlite3.connect(path) as connection:
        connection.executescript("""
            CREATE TABLE orphan (a INTEGER REFERENCES missing_parent);
            CREATE TABLE no_key (id INTEGER);
            CREATE TABLE no_key_child (a INTEGER REFERENCES no_key);
        """)
    for name in ("orphan", "no_key_child"):
        fk = load(database, name).constraints.value[0]
        assert fk.columns == ("a",)
        assert fk.referenced_columns == ()
        assert fk.referenced_columns_state == MetadataState.UNAVAILABLE


def test_sql_comments_are_not_treated_as_descriptions_and_unique_keys_stay_grouped(database):
    _, _, path = database
    with sqlite3.connect(path) as connection:
        connection.executescript("""
            CREATE TABLE documented (
                a TEXT /* this is not a structured description */,
                b TEXT, c INTEGER,
                UNIQUE (b, a), UNIQUE (c)
            );
        """)
    result = load(database, "documented")
    assert result.columns[0].description.state == MetadataState.UNSUPPORTED
    assert [key.columns for key in result.constraints.value] == [("b", "a"), ("c",)]


def test_read_only_file_connection_can_load_properties(database):
    _, _, path = database
    driver = SqlAlchemySqliteDriver()
    config = ConnectionConfig(
        "read-only", "sqlite", "sqlite", database=path.as_uri(), extra={"uri": "true", "mode": "ro"}
    )
    service = DbService(driver, SqliteDialect())
    try:
        result = service.get_object_properties(config, SchemaObjectIdentity("main", "child", SchemaObjectKind.TABLE))
        assert result.columns[0].name == "id"
        with pytest.raises(OperationalError, match="readonly"):
            driver.execute_df(config, "CREATE TABLE forbidden (x)")
    finally:
        driver.dispose()


@pytest.mark.parametrize("stage", range(6))
def test_query_errors_do_not_become_partial_success(database, stage):
    service, _, _ = database
    execute = service.driver.execute_df
    calls = 0

    def failing_execute(*args, **kwargs):
        nonlocal calls
        current = calls
        calls += 1
        if current == stage:
            message = "catalog query denied"
            raise sqlite3.OperationalError(message)
        return execute(*args, **kwargs)

    with (
        patch.object(service.driver, "execute_df", side_effect=failing_execute),
        pytest.raises(RuntimeError),
    ):
        load(database)
    assert calls == stage + 1
