import pytest
from expo_jbm329.db.dialects.mssql import MssqlDialect
from expo_jbm329.db.dialects.mysql import MySqlDialect
from expo_jbm329.db.dialects.sqlite import SqliteDialect

def test_mssql_dialect():
    dialect = MssqlDialect()
    assert dialect.name == "mssql"
    
    # Limit
    sql = "SELECT * FROM t"
    limited = dialect.apply_limit(sql, 10)
    assert "TOP 10" in limited
    
    # Quoting
    assert dialect.quote_ident("table") == "[table]"
    
    # Qualify
    assert dialect.qualify("dbo", "table") == "[dbo].[table]"
    
    # Metadata SQL
    assert "information_schema.tables" in dialect.sql_list_tables().lower()
    assert "information_schema.views" in dialect.sql_list_views().lower()
    assert "information_schema.columns" in dialect.sql_list_columns("dbo", "t").lower()

def test_mysql_dialect():
    dialect = MySqlDialect()
    assert dialect.name == "mysql"
    
    # Limit
    sql = "SELECT * FROM t"
    limited = dialect.apply_limit(sql, 10)
    assert "LIMIT 10" in limited
    
    # Quoting
    assert dialect.quote_ident("table") == "`table`"
    
    # Qualify
    assert dialect.qualify("db", "table") == "`db`.`table`"
    
    # Metadata SQL
    assert "information_schema.tables" in dialect.sql_list_tables().lower()
    assert "table_type='base table'" in dialect.sql_list_tables().lower()

def test_sqlite_dialect():
    dialect = SqliteDialect()
    assert dialect.name == "sqlite"
    
    # Limit
    sql = "SELECT * FROM t"
    limited = dialect.apply_limit(sql, 10)
    assert "LIMIT 10" in limited
    
    # Quoting
    assert dialect.quote_ident("table") == '"table"'
    
    # Qualify (SQLite dialect ignores schema in qualify)
    assert dialect.qualify("main", "table") == '"table"'
    
    # Metadata SQL
    assert "sqlite_master" in dialect.sql_list_tables().lower()
    assert "type='table'" in dialect.sql_list_tables().lower()
