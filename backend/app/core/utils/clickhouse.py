"""ClickHouse database connection module.

This module provides functions to connect to ClickHouse database and execute queries.
It is used by the performance score calculation.
"""

from clickhouse_driver import Client, connect

from app.core.config import (
    CLICKHOUSE_DB,
    CLICKHOUSE_HOST,
    CLICKHOUSE_PASSWORD,
    CLICKHOUSE_PORT,
    CLICKHOUSE_USER,
)


def get_clickhouse_connection():
    """Get a ClickHouse database connection.

    This function uses ClickHouse connection parameters imported from config.py
    and returns a connection object. The connection is not used by default currently,
    but can be used in the future by importing and calling this function.

    Returns:
        A ClickHouse connection object, or None if connection fails or
        required parameters are not configured.

    Note:
        This function is intended for future usage. Currently, the config
        variables are set with empty/default values so the function will
        return None unless explicitly configured.
    """
    host = CLICKHOUSE_HOST
    port = int(CLICKHOUSE_PORT)
    database = CLICKHOUSE_DB
    user = CLICKHOUSE_USER
    password = CLICKHOUSE_PASSWORD

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


def execute_query(sql=None, parameters=None, db=None, table=None):
    """Execute a ClickHouse query and return the results.
    
    This function supports two modes:
    
    1. Raw SQL mode: Provide custom SQL query string in `sql`.
       Use `parameters` for parameter binding.
       
    2. Automatic query mode: Provide `table` name (optionally with `db` database name).
       The function will build a SELECT query automatically.
       
    If neither `sql` nor (`db` and `table`) are provided, a basic "SELECT 1" query is used
    for testing connectivity.
    
    Args:
        sql: SQL query string. If building automatic query, use "SELECT * FROM table_name"
        parameters: Optional dictionary of parameters to bind (for raw SQL mode)
        db: Optional database name for automatic query mode
        table: Optional table name for automatic query mode
        
    Returns:
        List of dictionaries representing the query results, or None if connection not configured
        
    Example:
        # Automatic mode - SELECT * from specific table in specific database
        results = execute_query(db="default", table="my_table")
        
        # Raw SQL mode
        results = execute_query(sql="SELECT * FROM my_table WHERE id = %s", {"id": 1})
        
        # Automatic mode without database (uses default DB)
        results = execute_query(table="my_table")
        
        # Default connectivity test
        results = execute_query()
    """
    client = get_clickhouse_client()
    if client is None:
        return None

    try:
        # If db and table are provided, build a SELECT query automatically
        if db and table:
            # Build a SELECT query with the specified database and table
            sql = f"SELECT * FROM {db}.{table}"
        elif sql is None:
            # Default: basic connectivity test
            sql = "SELECT 1 as test"
        # with_column_types returns (rows, [(name, type), ...]) so callers
        # get real column names instead of positional aliases.
        rows, columns = client.execute(sql, parameters or {}, with_column_types=True)
        names = [col[0] for col in columns]
        return [dict(zip(names, row)) for row in rows]
    except Exception as e:
        print(f"ClickHouse query execution failed: {e}")
        return None
    finally:
        try:
            client.disconnect()
        except Exception:
            pass


def get_clickhouse_client():
    """Get a ClickHouse native-protocol client, or None if not configured.

    Returns:
        A clickhouse_driver Client object, or None if the host is not
        configured or the client cannot be created.
    """
    if not CLICKHOUSE_HOST:
        return None

    try:
        port = int(CLICKHOUSE_PORT)
    except (TypeError, ValueError):
        print(f"ClickHouse client creation failed: invalid port {CLICKHOUSE_PORT!r}")
        return None

    try:
        return Client(
            host=CLICKHOUSE_HOST,
            port=port,
            database=CLICKHOUSE_DB or "default",
            user=CLICKHOUSE_USER,
            password=CLICKHOUSE_PASSWORD,
        )
    except Exception as e:
        print(f"ClickHouse client creation failed: {e}")
        return None


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