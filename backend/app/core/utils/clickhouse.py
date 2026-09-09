"""ClickHouse database connection module.

This module provides functions to connect to ClickHouse database and execute queries.
Currently not used in the main application flow, but available for future usage.
"""

from clickhouse_driver import connect

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
    connection = get_clickhouse_connection()
    if connection is None:
        return None
    
    try:
        # If db and table are provided, build a SELECT query automatically
        if db and table:
            # Build a SELECT query with the specified database and table
            sql = f"SELECT * FROM {db}.{table}"
            # Execute the query
            rows = connection.execute(sql, parameters or {})
            # Return rows as list of tuples
            return [row for row in rows]
        elif sql is None:
            # Default: basic connectivity test
            sql = "SELECT 1 as test"
            rows = connection.execute(sql, parameters or {})
            if rows:
                return [dict(zip([f'col_{i}' for i in range(len(rows[0]))], row)) for row in rows]
            return []
        else:
            # Use raw SQL provided
            rows = connection.execute(sql, parameters or {})
            if rows:
                # Return rows as list of dicts with generic column names
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