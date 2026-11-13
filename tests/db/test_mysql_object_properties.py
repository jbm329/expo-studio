from __future__ import annotations

from dataclasses import replace
from unittest.mock import MagicMock

import pandas as pd
import pytest
import sqlglot

from expo_jbm329.db.core.interfaces import (
    DriverProtocol,
    ObjectPropertiesDialectProtocol,
    ObjectPropertiesDiscoveryDialectProtocol,
)
from expo_jbm329.db.core.models import ConnectionConfig, SqlError, SqlResult
from expo_jbm329.db.core.object_properties import MetadataState, SchemaObjectIdentity, SchemaObjectKind
from expo_jbm329.db.dialects.mysql import MySqlDialect
from expo_jbm329.db.object_properties import load_object_properties
from expo_jbm329.db.service import DbService

CATALOG_COLUMNS = {
    "TABLES": "TABLE_CATALOG TABLE_SCHEMA TABLE_NAME TABLE_TYPE TABLE_COMMENT CREATE_TIME",
    "COLUMNS": (
        "TABLE_SCHEMA TABLE_NAME COLUMN_NAME ORDINAL_POSITION COLUMN_TYPE IS_NULLABLE "
        "COLUMN_DEFAULT COLUMN_COMMENT EXTRA DATA_TYPE GENERATION_EXPRESSION"
    ),
    "TABLE_CONSTRAINTS": "CONSTRAINT_SCHEMA TABLE_SCHEMA TABLE_NAME CONSTRAINT_NAME CONSTRAINT_TYPE",
    "KEY_COLUMN_USAGE": (
        "CONSTRAINT_SCHEMA TABLE_SCHEMA TABLE_NAME CONSTRAINT_NAME COLUMN_NAME ORDINAL_POSITION "
        "REFERENCED_TABLE_SCHEMA REFERENCED_TABLE_NAME REFERENCED_COLUMN_NAME"
    ),
    "CHECK_CONSTRAINTS": "CONSTRAINT_SCHEMA CONSTRAINT_NAME CHECK_CLAUSE",
    "STATISTICS": "INDEX_SCHEMA TABLE_SCHEMA TABLE_NAME INDEX_NAME COLUMN_NAME SEQ_IN_INDEX SUB_PART EXPRESSION",
}


def capabilities(version="8.0.36", *, checks=True, generated=True, table_checks=False, expressions=False):
    rows = [
        {"server_version": version, "table_name": table, "column_name": column}
        for table, columns in CATALOG_COLUMNS.items()
        for column in columns.split()
        if (checks or table != "CHECK_CONSTRAINTS")
        and (generated or column != "GENERATION_EXPRESSION")
        and (expressions or column != "EXPRESSION")
    ]
    if table_checks:
        rows.append({"server_version": version, "table_name": "CHECK_CONSTRAINTS", "column_name": "TABLE_NAME"})
    return pd.DataFrame(rows)


@pytest.fixture
def identity():
    return SchemaObjectIdentity("sales", "Orders", SchemaObjectKind.TABLE, "def")


def column(number=1, **overrides):
    return {
        "object_id": 1,
        "column_id": number,
        "column_name": f"column_{number}",
        "ordinal_position": number,
        "data_type": "decimal(18,4) unsigned",
        "nullable": 0,
        "description": "Column\n<comment>",
        "default_present": 0,
        "default_definition": None,
        "identity_present": 0,
        "identity_definition": None,
        "generated_present": 0,
        "generated_definition": None,
    } | overrides


def constraint(name="PRIMARY", **overrides):
    row = {
        "object_id": 1,
        "constraint_id": name,
        "constraint_name": name,
        "constraint_kind": "primary_key",
        "column_position": 1,
        "column_name": "column_1",
        "definition": None,
        "referenced_schema": None,
        "referenced_object": None,
        "referenced_column": None,
    } | overrides
    row["key_part"] = overrides.get(
        "key_part",
        f"`{row['column_name']}`" if row["constraint_kind"] in ("primary_key", "unique") else None,
    )
    return row


def results(*, columns=None, constraints=None):
    header = pd.DataFrame([
        {
            "catalog_name": "def",
            "schema_name": "sales",
            "object_name": "Orders",
            "object_id": 1,
            "modify_date": None,
            "description": "Object\n<comment>",
        }
    ])
    cols = pd.DataFrame([column()] if columns is None else columns)
    keys = pd.DataFrame(constraints or [])
    return [SqlResult(ok=True, data=frame.copy()) for frame in (header, cols, keys, header, cols, keys)]


def load(identity, execute, caps=None):
    queries = MySqlDialect().sql_discovered_object_properties(identity, capabilities() if caps is None else caps)
    return load_object_properties(identity, queries, execute)


@pytest.mark.parametrize("kind", list(SchemaObjectKind))
@pytest.mark.parametrize(
    "version,checks,table_checks",
    [
        ("8.0.36", True, False),
        ("5.7.44", False, False),
        ("11.4.2-MariaDB", True, True),
    ],
)
def test_queries_are_read_only_scoped_selects_with_sql_mode_independent_literals(kind, version, checks, table_checks):
    identity = SchemaObjectIdentity("sch'ema\\", "Örders'; DROP TABLE x;--", kind, "def")
    dialect = MySqlDialect()
    queries = dialect.sql_discovered_object_properties(
        identity, capabilities(version, checks=checks, table_checks=table_checks)
    )
    assert isinstance(dialect, ObjectPropertiesDialectProtocol)
    assert isinstance(dialect, ObjectPropertiesDiscoveryDialectProtocol)
    assert queries.properties is None and queries.description_property is None
    for sql in (queries.object, queries.columns, queries.constraints, dialect.sql_object_properties_capabilities()):
        parsed = sqlglot.parse(sql, read="mysql")
        assert len(parsed) == 1
        assert isinstance(parsed[0], (sqlglot.exp.Select, sqlglot.exp.Union))
        assert all(table.db.upper() == "INFORMATION_SCHEMA" for table in parsed[0].find_all(sqlglot.exp.Table))
    for sql in (queries.object, queries.columns, queries.constraints):
        assert identity.name not in sql
        assert f"_utf8mb4 X'{identity.name.encode().hex()}'" in sql
        assert f"_utf8mb4 X'{identity.schema.encode().hex()}'" in sql
        assert "t.TABLE_CATALOG =" in sql
        expected = "'BASE TABLE'" if kind == SchemaObjectKind.TABLE else "'VIEW'"
        assert f"t.TABLE_TYPE = {expected}" in sql
    assert "t.TABLE_CATALOG =" not in dialect.sql_object_properties(replace(identity, catalog=None)).object
    assert (
        queries.object
        != dialect.sql_discovered_object_properties(
            replace(identity, schema="other"),
            capabilities(version, checks=checks, table_checks=table_checks),
        ).object
    )
    assert ("INFORMATION_SCHEMA.CHECK_CONSTRAINTS AS cc" in queries.constraints) is checks
    if checks:
        assert ("cc.TABLE_NAME = t.TABLE_NAME" in queries.constraints) is table_checks
    assert "UPDATE_TIME" not in queries.object
    assert "AUTO_INCREMENT AS" not in queries.object


@pytest.mark.parametrize(
    "caps, expected",
    [
        (capabilities(), "QUOTE(c.COLUMN_DEFAULT)"),
        (capabilities("11.4.2-MariaDB", table_checks=True), "c.COLUMN_DEFAULT AS default_definition"),
        (capabilities("5.5.5-10.2.7-MariaDB", table_checks=True), "c.COLUMN_DEFAULT AS default_definition"),
        (capabilities("10.2.6-MariaDB", table_checks=True), "NULL AS default_definition"),
    ],
)
def test_default_representation_is_not_guessed_across_engines(identity, caps, expected):
    queries = MySqlDialect().sql_discovered_object_properties(identity, caps)
    assert expected in queries.columns
    assert "c.COLUMN_TYPE AS data_type" in queries.columns
    if "QUOTE(" in expected:
        assert "DEFAULT_GENERATED" in queries.columns
        assert "^CURRENT_TIMESTAMP([(][0-9]*[)])?$" in queries.columns
        assert "c.DATA_TYPE = 'bit'" in queries.columns
        assert "FIND_IN_SET('NO_BACKSLASH_ESCAPES', @@sql_mode)" in queries.columns
        assert "REPLACE(c.COLUMN_DEFAULT, CHAR(39)" in queries.columns


def test_missing_generated_expression_is_unavailable_not_a_failed_query(identity):
    queries = MySqlDialect().sql_discovered_object_properties(identity, capabilities(generated=False))
    assert "c.GENERATION_EXPRESSION" not in queries.columns
    assert "NULL AS generated_definition" in queries.columns
    execute = MagicMock(side_effect=results(columns=[column(generated_present=1)]))
    snapshot = load(identity, execute, capabilities(generated=False))
    assert snapshot.columns[0].generated.state == MetadataState.UNAVAILABLE


@pytest.mark.parametrize("change", ["empty", "required", "checks", "maria-table", "version", "null", "fields"])
def test_invalid_or_incomplete_capabilities_fail_explicitly(identity, change):
    caps = capabilities()
    if change == "empty":
        caps = caps.iloc[:0]
    elif change == "required":
        caps = caps[caps.column_name != "COLUMN_TYPE"]
    elif change == "checks":
        caps = caps[caps.column_name != "CHECK_CLAUSE"]
    elif change == "maria-table":
        caps = capabilities("11.4.2-MariaDB")
    elif change == "version":
        caps.server_version = "unknown"
    elif change == "fields":
        caps = pd.DataFrame()
    else:
        caps.loc[0, "column_name"] = None
    with pytest.raises(ValueError):
        MySqlDialect().sql_discovered_object_properties(identity, caps)


def test_comments_full_types_expressions_and_no_synthetic_properties(identity):
    execute = MagicMock(
        side_effect=results(
            columns=[
                column(default_present=1, default_definition="'O''Brien'"),
                column(2, data_type="enum('small','large')", identity_present=1, identity_definition="AUTO_INCREMENT"),
                column(3, data_type="varchar(50)", nullable=1, generated_present=1, generated_definition="concat(a,b)"),
            ]
        )
    )
    snapshot = load(identity, execute)
    assert snapshot.description.value == "Object\n<comment>"
    assert snapshot.properties.state == MetadataState.UNSUPPORTED
    assert snapshot.columns[0].description.value == "Column\n<comment>"
    assert snapshot.columns[0].data_type.value == "decimal(18,4) unsigned"
    assert snapshot.columns[0].default.value == "'O''Brien'"
    assert snapshot.columns[1].identity.value == "AUTO_INCREMENT"
    assert snapshot.columns[2].generated.value == "concat(a,b)"
    assert snapshot.columns[2].nullable.value is True
    assert all(col.properties.state == MetadataState.UNSUPPORTED for col in snapshot.columns)
    assert execute.call_count == 6


def test_view_comments_are_unsupported_not_inherited(identity):
    snapshot = load(replace(identity, kind=SchemaObjectKind.VIEW), MagicMock(side_effect=results()))
    assert snapshot.description.state == MetadataState.UNSUPPORTED
    assert snapshot.columns[0].description.state == MetadataState.UNSUPPORTED
    assert snapshot.constraints.state == MetadataState.NOT_APPLICABLE
    assert snapshot.check_constraints_state == MetadataState.NOT_APPLICABLE


def test_composite_keys_named_constraints_and_check_without_column_inference(identity):
    rows = [
        constraint(column_position=2, column_name="column_2"),
        constraint(),
        constraint("uq", constraint_kind="unique"),
        constraint("uq", constraint_kind="unique", column_position=2, column_name="column_2"),
        constraint(
            "fk",
            constraint_kind="foreign_key",
            referenced_schema="other",
            referenced_object="Items",
            referenced_column="tenant",
        ),
        constraint(
            "fk",
            constraint_kind="foreign_key",
            referenced_schema="other",
            referenced_object="Items",
            referenced_column="id",
            column_position=2,
            column_name="column_2",
        ),
        constraint("ck", constraint_kind="check", column_name=None, definition="a > 0"),
    ]
    snapshot = load(identity, MagicMock(side_effect=results(columns=[column(), column(2)], constraints=rows)))
    pk, unique, fk, check = snapshot.constraints.value
    assert pk.columns == unique.columns == fk.columns == ("column_1", "column_2")
    assert fk.referenced_object == SchemaObjectIdentity("other", "Items", SchemaObjectKind.TABLE, "def")
    assert fk.referenced_columns == ("tenant", "id")
    assert check.columns == () and check.definition.value == "a > 0"
    assert pk.definition.value == "PRIMARY KEY (`column_1`, `column_2`)"


def test_native_expression_and_prefix_key_parts_are_not_lost(identity):
    rows = [
        constraint("uq", constraint_kind="unique", key_part="`column_1`(10)"),
        constraint("uq", constraint_kind="unique", column_position=2, column_name=None, key_part="(abs(`column_2`))"),
        constraint("expr", constraint_kind="unique", column_name=None, key_part="(lower(`column_2`))"),
    ]
    snapshot = load(identity, MagicMock(side_effect=results(constraints=rows)), capabilities(expressions=True))
    mixed, expression = snapshot.constraints.value
    assert mixed.columns == ("column_1",)
    assert mixed.definition.value == "UNIQUE (`column_1`(10), (abs(`column_2`)))"
    assert expression.columns == ()
    assert expression.definition.value == "UNIQUE ((lower(`column_2`)))"
    dialect = MySqlDialect()
    query = dialect.sql_discovered_object_properties(identity, capabilities(expressions=True)).constraints
    assert "s.EXPRESSION" in query
    assert "s.SUB_PART" in query
    assert "s.SEQ_IN_INDEX" in query
    assert "tc.CONSTRAINT_TYPE = 'FOREIGN KEY'" in query
    assert "s.EXPRESSION" not in dialect.sql_discovered_object_properties(identity, capabilities()).constraints
    assert isinstance(sqlglot.parse_one(query, read="mysql"), sqlglot.exp.Union)


def test_missing_key_part_is_not_misrepresented_as_a_smaller_key(identity):
    rows = [
        constraint("uq", constraint_kind="unique"),
        constraint("uq", constraint_kind="unique", column_position=2, column_name=None, key_part=None),
    ]
    with pytest.raises(ValueError, match="catalog text is missing"):
        load(identity, MagicMock(side_effect=results(constraints=rows)))


def test_check_coverage_absence_is_explicit(identity):
    snapshot = load(identity, MagicMock(side_effect=results()), capabilities("5.7.44", checks=False))
    assert snapshot.check_constraints_state == MetadataState.UNSUPPORTED
    assert snapshot.constraints.value == ()


def test_same_constraint_name_in_different_kinds_does_not_merge(identity):
    rows = [constraint(), constraint(constraint_kind="check", column_name=None, definition="a > 0")]
    snapshot = load(identity, MagicMock(side_effect=results(constraints=rows)))
    assert len(snapshot.constraints.value) == 2
    assert snapshot.constraints.value[1].columns == ()


def test_present_legacy_default_is_unavailable_not_a_guessed_expression(identity):
    snapshot = load(
        identity,
        MagicMock(side_effect=results(columns=[column(default_present=1)])),
        capabilities("10.2.6-MariaDB", table_checks=True),
    )
    assert snapshot.columns[0].default.state == MetadataState.UNAVAILABLE


def test_empty_column_catalog_fails_explicitly(identity):
    with pytest.raises(RuntimeError, match="Object columns"):
        load(identity, MagicMock(side_effect=results(columns=[])))


@pytest.mark.parametrize("stage", range(6))
def test_query_failure_never_returns_partial_metadata(identity, stage):
    frames = results()
    frames[stage] = SqlResult(ok=False, error=SqlError("permission", None, "Denied", "Ask administrator"))
    execute = MagicMock(side_effect=frames)
    with pytest.raises(RuntimeError, match="Denied\n\nAsk administrator"):
        load(identity, execute)
    assert execute.call_count == stage + 1


@pytest.mark.parametrize("stage", [3, 4, 5])
def test_rereads_detect_header_column_and_constraint_changes(identity, stage):
    frames = results()
    frames[stage].data["new_metadata"] = "changed"
    with pytest.raises(RuntimeError, match="object changed"):
        load(identity, MagicMock(side_effect=frames))


def test_missing_object_does_not_return_empty_success(identity):
    frames = results()
    frames[0] = SqlResult(ok=True, data=pd.DataFrame())
    with pytest.raises(RuntimeError, match="does not exist or is not visible"):
        load(identity, MagicMock(side_effect=frames))


@pytest.mark.parametrize(
    "engine, caps",
    [
        ("mysql", capabilities()),
        ("mariadb", capabilities("11.4.2-MariaDB", table_checks=True)),
    ],
)
def test_service_discovers_through_existing_executor_with_correlation(identity, engine, caps):
    driver = MagicMock(spec=DriverProtocol)
    driver.execute_df.side_effect = [caps, *(result.data for result in results())]
    dialect = MySqlDialect()
    service = DbService(driver, dialect)
    connection = ConnectionConfig("MySQL", engine, "pymysql")
    assert service.get_object_properties(connection, identity, corr_id="properties").identity == identity
    assert driver.execute_df.call_count == 7
    assert driver.execute_df.call_args_list[0].args[1] == dialect.sql_object_properties_capabilities()
    for call in driver.execute_df.call_args_list:
        assert call.args[0] is connection
        assert call.kwargs["corr_id"] == "properties"
        assert " LIMIT " not in call.args[1]


@pytest.mark.parametrize(
    "result, message",
    [
        (SqlResult(ok=False, error=SqlError("permission", None, "Denied", "Ask administrator")), "Denied\n\nAsk"),
        (SqlResult(ok=False), "did not complete"),
        (SqlResult(ok=True), "no result set"),
    ],
)
def test_discovery_errors_are_not_used_as_capability_defaults(identity, result, message):
    service = DbService(MagicMock(spec=DriverProtocol), MySqlDialect())
    service.execute_sql = MagicMock(return_value=result)
    with pytest.raises(RuntimeError, match=message):
        service.get_object_properties(ConnectionConfig("MySQL", "mysql", "pymysql"), identity)
    service.execute_sql.assert_called_once()


def test_invalid_discovery_does_not_execute_object_queries(identity):
    driver = MagicMock(spec=DriverProtocol)
    driver.execute_df.return_value = capabilities().iloc[:0]
    service = DbService(driver, MySqlDialect())
    with pytest.raises(ValueError, match="capabilities are unavailable"):
        service.get_object_properties(ConnectionConfig("MySQL", "mysql", "pymysql"), identity)
    driver.execute_df.assert_called_once()
