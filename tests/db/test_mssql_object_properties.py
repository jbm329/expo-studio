from __future__ import annotations

from dataclasses import replace
from unittest.mock import MagicMock

import pandas as pd
import pytest
import sqlglot

from expo_jbm329.db.core.interfaces import DriverProtocol, ObjectPropertiesDialectProtocol
from expo_jbm329.db.core.models import ConnectionConfig, SqlError, SqlResult
from expo_jbm329.db.core.object_properties import (
    ConstraintKind,
    MetadataState,
    SchemaObjectIdentity,
    SchemaObjectKind,
)
from expo_jbm329.db.dialects.ansi import AnsiDialect
from expo_jbm329.db.dialects.mssql import MssqlDialect
from expo_jbm329.db.object_properties import load_object_properties
from expo_jbm329.db.service import DbService


@pytest.fixture
def identity():
    return SchemaObjectIdentity("dbo", "Orders", SchemaObjectKind.TABLE, "Example")


@pytest.fixture
def header():
    return pd.DataFrame([
        {
            "catalog_name": "Example",
            "schema_name": "dbo",
            "object_name": "Orders",
            "object_id": 42,
            "modify_date": pd.Timestamp("2026-01-01"),
        }
    ])


def column(column_id=1, **overrides):
    values = {
        "object_id": 42,
        "column_id": column_id,
        "column_name": f"column_{column_id}",
        "ordinal_position": column_id,
        "data_type": "int",
        "nullable": False,
        "default_present": False,
        "default_definition": None,
        "identity_present": False,
        "identity_definition": None,
        "generated_present": False,
        "generated_definition": None,
    }
    return values | overrides


def constraint(constraint_id=10, **overrides):
    values = {
        "object_id": 42,
        "constraint_id": constraint_id,
        "constraint_name": "PK_Orders",
        "constraint_kind": "primary_key",
        "column_position": 1,
        "column_name": "column_1",
        "definition": None,
        "referenced_schema": None,
        "referenced_object": None,
        "referenced_column": None,
    }
    return values | overrides


def property_row(name="MS_Description", value="Object description", column_id=0):
    return {"object_id": 42, "column_id": column_id, "property_name": name, "property_value": value}


def executor(header, columns=None, constraints=None, properties=None, final=None):
    frames = [
        header,
        pd.DataFrame([column()] if columns is None else columns),
        pd.DataFrame([] if constraints is None else constraints),
        pd.DataFrame([] if properties is None else properties),
        header if final is None else final,
    ]
    return MagicMock(side_effect=[SqlResult(ok=True, data=frame) for frame in frames])


def load(identity, execute):
    return load_object_properties(identity, MssqlDialect().sql_object_properties(identity), execute)


@pytest.mark.parametrize("kind,sql_kind", [(SchemaObjectKind.TABLE, "U"), (SchemaObjectKind.VIEW, "V")])
def test_queries_are_read_only_scoped_selects_with_unicode_literals(kind, sql_kind):
    identity = SchemaObjectIdentity("Sch'ema];--", "Örder' ; DROP TABLE x;--", kind, "Cat'alog")
    queries = MssqlDialect().sql_object_properties(identity)
    for sql in (queries.object, queries.columns, queries.constraints, queries.properties):
        statements = sqlglot.parse(sql, read="tsql")
        assert len(statements) == 1
        assert isinstance(statements[0], (sqlglot.exp.Select, sqlglot.exp.Union))
        assert "s.name = N'Sch''ema];--'" in sql
        assert "o.name = N'Örder'' ; DROP TABLE x;--'" in sql
        assert "DB_NAME() = N'Cat''alog'" in sql
        assert f"o.type = N'{sql_kind}'" in sql
        assert all(table.db == "sys" for table in statements[0].find_all(sqlglot.exp.Table) if table.db)
    assert "ep.class = 1 AND ep.major_id = o.object_id" in queries.properties
    assert "ep.minor_id AS column_id" in queries.properties
    assert "CONVERT(nvarchar(max), ep.value)" in queries.properties
    assert "CONVERT(varbinary(8000), ep.value), 1" in queries.properties
    assert "ic.key_ordinal > 0" in queries.constraints


def test_query_capability_is_optional_and_catalog_can_be_omitted():
    assert isinstance(MssqlDialect(), ObjectPropertiesDialectProtocol)
    assert not isinstance(AnsiDialect(), ObjectPropertiesDialectProtocol)
    identity = SchemaObjectIdentity("dbo", "Orders", SchemaObjectKind.TABLE)
    assert "DB_NAME() =" not in MssqlDialect().sql_object_properties(identity).object
    other_schema = replace(identity, schema="other")
    assert (
        MssqlDialect().sql_object_properties(other_schema).object
        != MssqlDialect().sql_object_properties(identity).object
    )


def test_type_query_preserves_sql_server_type_details(identity):
    sql = MssqlDialect().sql_object_properties(identity).columns
    assert "c.max_length / 2" in sql
    assert "c.max_length = -1 THEN N'max'" in sql
    assert "c.precision" in sql and "c.scale" in sql
    assert "QUOTENAME(ts.name) + N'.' + QUOTENAME(t.name)" in sql
    assert "t.is_user_defined = 1 OR t.is_assembly_type = 1" in sql
    assert "c.xml_collection_id <> 0" in sql
    assert "N'DOCUMENT '" in sql and "N'CONTENT '" in sql


def test_all_properties_remain_in_their_scopes_and_columns_keep_ordinal_order(identity, header):
    execute = executor(
        header,
        columns=[column(4, nullable=True), column(1)],
        properties=[
            property_row(),
            property_row("Owner", "Analytics"),
            property_row(value="Column\n<description> & plain text", column_id=1),
            property_row("Custom", None, column_id=1),
            property_row("Binary", "0x0102", column_id=4),
        ],
    )
    result = load(identity, execute)
    assert result.identity == identity
    assert result.description.value == "Object description"
    assert [prop.name for prop in result.properties.value] == ["MS_Description", "Owner"]
    assert [col.ordinal_position for col in result.columns] == [1, 4]
    assert result.columns[0].description.value == "Column\n<description> & plain text"
    assert result.columns[0].properties.value[1].value.state == MetadataState.ABSENT
    assert result.columns[0].nullable.value is False
    assert result.columns[1].nullable.value is True
    assert result.columns[1].properties.value[0].value.value == "0x0102"
    assert result.constraints.value == ()
    assert execute.call_count == 5


@pytest.mark.parametrize("value", [None, float("nan"), pd.NA, pd.NaT])
def test_null_property_is_not_stringified(identity, header, value):
    result = load(identity, executor(header, properties=[property_row(value=value)]))
    assert result.description.state == MetadataState.ABSENT
    assert result.properties.value[0].value.value is None


@pytest.mark.parametrize(
    "data_type",
    [
        "nvarchar(50)",
        "varchar(max)",
        "decimal(18, 4)",
        "datetime2(7)",
        "float(53)",
        "[types].[Money]",
        "[types].[Point]",
        "xml(DOCUMENT [dbo].[OrderSchema])",
        "sysname",
    ],
)
def test_full_catalog_type_is_retained(identity, header, data_type):
    result = load(identity, executor(header, columns=[column(data_type=data_type)]))
    assert result.columns[0].data_type.value == data_type


def test_expressions_distinguish_absence_and_unavailable_definitions(identity, header):
    result = load(
        identity,
        executor(
            header,
            columns=[
                column(
                    1,
                    default_present=True,
                    default_definition="((0))",
                    identity_present=True,
                    identity_definition="IDENTITY(1, 5)",
                ),
                column(2, generated_present=True, generated_definition="([subtotal]+[tax])"),
                column(3, default_present=True, identity_present=True, generated_present=True, data_type=None),
            ],
        ),
    )
    assert result.columns[0].default.value == "((0))"
    assert result.columns[0].identity.value == "IDENTITY(1, 5)"
    assert result.columns[0].generated.state == MetadataState.NOT_APPLICABLE
    assert result.columns[1].default.state == MetadataState.ABSENT
    assert result.columns[1].generated.value == "([subtotal]+[tax])"
    assert result.columns[2].default.state == MetadataState.UNAVAILABLE
    assert result.columns[2].identity.state == MetadataState.UNAVAILABLE
    assert result.columns[2].generated.state == MetadataState.UNAVAILABLE
    assert result.columns[2].data_type.state == MetadataState.UNAVAILABLE


def test_constraints_preserve_composite_grouping_targets_and_checks(identity, header):
    rows = [
        constraint(column_position=2, column_name="column_2"),
        constraint(column_position=1),
        constraint(11, constraint_kind="unique", constraint_name="UQ_Orders"),
        constraint(
            11, constraint_kind="unique", constraint_name="UQ_Orders", column_position=2, column_name="column_2"
        ),
        constraint(
            12,
            constraint_kind="foreign_key",
            constraint_name="FK_Orders",
            referenced_schema="sales",
            referenced_object="Items",
            referenced_column="tenant",
        ),
        constraint(
            12,
            constraint_kind="foreign_key",
            constraint_name="FK_Orders",
            column_position=2,
            column_name="column_2",
            referenced_schema="sales",
            referenced_object="Items",
            referenced_column="id",
        ),
        constraint(13, constraint_kind="check", constraint_name="CK_Orders", column_name=None, definition="[a] >= [b]"),
        constraint(14, constraint_kind="check", constraint_name="CK_Hidden", definition=None),
    ]
    result = load(identity, executor(header, columns=[column(), column(2)], constraints=rows))
    pk, unique, fk, check, hidden_check = result.constraints.value
    assert pk.kind == ConstraintKind.PRIMARY_KEY
    assert unique.kind == ConstraintKind.UNIQUE
    assert pk.columns == unique.columns == fk.columns == ("column_1", "column_2")
    assert fk.referenced_object == SchemaObjectIdentity("sales", "Items", SchemaObjectKind.TABLE, "Example")
    assert fk.referenced_columns == ("tenant", "id")
    assert check.columns == () and check.definition.value == "[a] >= [b]"
    assert hidden_check.definition.state == MetadataState.UNAVAILABLE


def test_views_do_not_inherit_underlying_constraints(identity, header):
    result = load(replace(identity, kind=SchemaObjectKind.VIEW), executor(header, properties=[property_row()]))
    assert result.identity.kind == SchemaObjectKind.VIEW
    assert result.description.value == "Object description"
    assert result.constraints.state == MetadataState.NOT_APPLICABLE


@pytest.mark.parametrize("stage", range(5))
def test_query_errors_propagate_instead_of_partial_success(identity, header, stage):
    execute = executor(header)
    results = list(execute.side_effect)
    results[stage] = SqlResult(ok=False, error=SqlError("permission", 229, "Permission denied.", "Check permissions."))
    execute.side_effect = results
    with pytest.raises(RuntimeError, match=r"Permission denied\.\n\nCheck permissions\."):
        load(identity, execute)
    assert execute.call_count == stage + 1


@pytest.mark.parametrize("result", [SqlResult(ok=True), SqlResult(ok=False), SqlResult(ok=False, cancelled=True)])
def test_missing_result_or_incomplete_execution_fails(identity, result):
    with pytest.raises(RuntimeError, match="no result set|did not complete"):
        load(identity, MagicMock(return_value=result))


def test_missing_or_hidden_object_is_explicit(identity, header):
    execute = executor(header.iloc[:0])
    with pytest.raises(RuntimeError, match="does not exist or is not visible"):
        load(identity, execute)
    assert execute.call_count == 1


@pytest.mark.parametrize("change", ["drop", "replace", "alter"])
def test_concurrent_ddl_invalidates_snapshot(identity, header, change):
    final = header.copy()
    if change == "drop":
        final = final.iloc[:0]
    elif change == "replace":
        final["object_id"] = 43
    else:
        final["modify_date"] = pd.Timestamp("2026-02-01")
    with pytest.raises(RuntimeError, match="object changed"):
        load(identity, executor(header, final=final))


def test_drop_between_catalog_queries_is_not_empty_success(identity, header):
    with pytest.raises(RuntimeError, match="no longer available"):
        load(identity, executor(header, columns=[]))
    with pytest.raises(RuntimeError, match="object changed"):
        load(identity, executor(header, columns=[column(object_id=43)]))


def test_malformed_catalog_rows_fail_explicitly(identity, header):
    with pytest.raises(ValueError, match="unknown columns"):
        load(identity, executor(header, properties=[property_row(column_id=999)]))
    with pytest.raises(ValueError, match="Required catalog text"):
        load(
            identity,
            executor(
                header,
                constraints=[
                    constraint(
                        constraint_kind="foreign_key",
                        referenced_column="id",
                        referenced_object="Hidden",
                        referenced_schema=None,
                    )
                ],
            ),
        )
    with pytest.raises(ValueError, match="non-null boolean"):
        load(identity, executor(header, columns=[column(nullable=None)]))


@pytest.mark.parametrize("ordinal", [0.5, None, float("nan")])
def test_invalid_ordinals_are_not_silently_coerced(identity, header, ordinal):
    with pytest.raises(ValueError, match="must be an integer"):
        load(identity, executor(header, columns=[column(ordinal_position=ordinal)]))


def test_boolean_identifier_and_non_text_property_are_rejected(identity, header):
    with pytest.raises(TypeError, match="must not be a boolean"):
        load(identity, executor(header, columns=[column(column_id=True)]))
    with pytest.raises(TypeError, match="string or SQL NULL"):
        load(identity, executor(header, properties=[property_row(value=123)]))


def test_service_uses_safe_executor_with_correlation_and_without_row_limit(identity, header):
    driver = MagicMock(spec=DriverProtocol)
    conn = ConnectionConfig("SQLServer", "mssql", "odbc")
    service = DbService(driver, MssqlDialect())
    execute = executor(header)
    driver.execute_df.side_effect = [result.data for result in execute.side_effect]
    snapshot = service.get_object_properties(conn, identity, corr_id="properties-request")
    assert snapshot.identity == identity
    assert driver.execute_df.call_count == 5
    for call in driver.execute_df.call_args_list:
        assert call.args[0] is conn
        assert call.kwargs["corr_id"] == "properties-request"
        assert "TOP " not in call.args[1]


def test_service_classifies_denied_driver_query(identity):
    driver = MagicMock(spec=DriverProtocol)
    driver.execute_df.side_effect = RuntimeError("Driver failed")
    service = DbService(driver, MssqlDialect())
    service._classify_error = MagicMock(return_value=SqlError("permission", 229, "Permission denied.", None))
    with pytest.raises(RuntimeError, match="Permission denied"):
        service.get_object_properties(ConnectionConfig("SQLServer", "mssql", "odbc"), identity)
    assert service._classify_error.call_args.args[1] == "mssql"
