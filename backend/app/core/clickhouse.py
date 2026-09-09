"""ClickHouse database connection module.

This module provides functions to connect to ClickHouse database and execute queries.
Currently not used in the main application flow, but available for future usage.
"""

import os
from clickhouse_driver import connect


def get_clickhouse_connection():
    """Get a ClickHouse database connection.

    This function reads ClickHouse connection parameters from environment variables
    and returns a connection object. The connection is not used by default currently,
    but can be used in the future by importing and calling this function.

    Environment variables (all optional, with sensible defaults):
        CLICKHOUSE_HOST: ClickHouse server host (default: empty)
        CLICKHOUSE_PORT: ClickHouse server port (default: 8123)
        CLICKHOUSE_DB: Default database name (default: empty)
        CLICKHOUSE_USER: ClickHouse user (default: empty)
        CLICKHOUSE_PASSWORD: ClickHouse password (default: empty)

    Returns:
        A ClickHouse connection object, or None if connection fails or
        required parameters are not configured.

    Note:
        This function is intended for future usage. Currently, the environment
        variables are set with empty/default values so the function will
        return None unless explicitly configured.
    """
    host = os.getenv("CLICKHOUSE_HOST", "")
    port = int(os.getenv("CLICKHOUSE_PORT", "8123"))
    database = os.getenv("CLICKHOUSE_DB", "")
    user = os.getenv("CLICKHOUSE_USER", "")
    password = os.getenv("CLICKHOUSE_PASSWORD", "")

    # Return None if host is not configured (not used for now)
    if not host:
        return None

    try:
        connection = connect(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password,
        )
        return connection
    except Exception as e:
        # Log the error but don't crash - this function is for future usage
        print(f"ClickHouse connection failed: {e}")
        return None


def execute_query(sql, parameters=None):
    """Execute a ClickHouse query and return the results.
    
    Args:
        sql: SQL query string
        parameters: Optional dictionary of parameters to bind
        
    Returns:
        List of dictionaries representing the query results, or None if connection not configured
    """
    connection = get_clickhouse_connection()
    if connection is None:
        return None
    
    try:
        # Clickhouse_driver returns rows as tuples, we'll convert to dicts
        rows = connection.execute(sql, parameters or {})
        # Get column names from the connection
        # Note: clickhouse-driver may not directly provide column names,
        # so we return rows as-is or convert based on available info
        if rows:
            # Return rows as list of tuples or dicts if column names available
            return [dict(zip([f'col_{i}' for i in range(len(rows[0]))], row)) for row in rows]
        return []
    except Exception as e:
        print(f"ClickHouse query execution failed: {e}")
        return None
    finally:
        try:
            connection.close()
        except Exception:
            pass


def get_clickhouse():
    """FastAPI dependency that yields a ClickHouse session (for future use).

    Returns:
        A context manager yielding a ClickHouse connection, or None if not configured.
    """
    connection = get_clickhouse_connection()
    if connection is None:
        return None

    try:
        yield connection
    finally:
        try:
            connection.close()
        except Exception:
            pass