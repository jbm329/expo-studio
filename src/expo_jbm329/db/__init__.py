# src/expo_jbm329/db/__init__.py
"""Public DB API for the app.

Re-exports the stable surface from db.base (legacy-free facade over the new service layer).
"""

from .base import (
    build_select_columns_auto,
    build_select_star,
    close_all_connections,
    close_connection,
    configure_timeouts,
    execute_sql_safe,
    fetch_df,
    get_db_name,
    list_all_columns_map,
    list_columns,
    list_tables,
    list_views,
)

__all__ = [
    "build_select_columns_auto",
    "build_select_star",
    "close_all_connections",
    "close_connection",
    "configure_timeouts",
    "execute_sql_safe",
    "fetch_df",
    "get_db_name",
    "list_all_columns_map",
    "list_columns",
    "list_tables",
    "list_views",
]
