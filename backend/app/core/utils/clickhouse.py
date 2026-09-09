"""ClickHouse database connection module (HTTP / clickhouse-connect).

This module provides functions to connect to ClickHouse database via HTTP(S)
and execute queries for performance score calculations.
"""

import clickhouse_connect

from app.core.config import (
    CLICKHOUSE_DB,
    CLICKHOUSE_HOST,
    CLICKHOUSE_PASSWORD,
    CLICKHOUSE_PORT,
    CLICKHOUSE_USER,
)
from app.core.utils.logger import get_logger

logger = get_logger(__name__)


def get_clickhouse_client():
    """Get an HTTP-based ClickHouse client without binding a fixed database at connection time.

    Returns:
        A clickhouse_connect Client object, or None if host is missing or connection fails.
    """
    if not CLICKHOUSE_HOST:
        logger.error(
            "CLICKHOUSE_HOST is not set: ClickHouse queries cannot run and will return None. "
            "Set CLICKHOUSE_HOST (and CLICKHOUSE_PORT/USER/PASSWORD) in the environment."
        )
        return None

    try:
        port = int(CLICKHOUSE_PORT)
    except (TypeError, ValueError):
        logger.error("ClickHouse client creation failed: invalid port %r", CLICKHOUSE_PORT)
        return None

    try:
        client = clickhouse_connect.get_client(
            host=CLICKHOUSE_HOST,
            port=port,
            username=CLICKHOUSE_USER,
            password=CLICKHOUSE_PASSWORD,
        )
        return client
    except Exception:
        logger.exception(
            "ClickHouse HTTP client creation failed (host=%r, port=%r, user=%r)",
            CLICKHOUSE_HOST,
            port,
            CLICKHOUSE_USER,
        )
        return None


def execute_query(sql=None, parameters=None, db=None, table=None):
    """Execute a ClickHouse query, specifying the target database at query runtime via settings.

    Args:
        sql: Custom SQL query string.
        parameters: Optional dictionary of parameters to bind.
        db: Optional target database name for this specific query run.
        table: Optional table name for automatic query mode.

    Returns:
        List of dictionaries representing the query results, or None on failure/unconfigured.
    """
    client = get_clickhouse_client()
    if client is None:
        return None

    target_db = db or CLICKHOUSE_DB or "default"

    try:
        if db and table:
            sql = f"SELECT * FROM {db}.{table}"
        elif sql is None:
            sql = "SELECT 1 as test"

        # Pass database via query settings dictionary
        result = client.query(
            sql,
            parameters=parameters or {},
            settings={"database": target_db},
        )

        # Consume generator into a Python list of dictionaries
        rows = list(result.named_results())

        logger.debug(
            "ClickHouse HTTP query on %s:%s (db=%s) returned %d rows",
            CLICKHOUSE_HOST,
            CLICKHOUSE_PORT,
            target_db,
            len(rows),
        )
        return rows
    except Exception:
        logger.exception(
            "ClickHouse HTTP query failed on %s:%s (database=%r, user=%r). SQL:\n%s",
            CLICKHOUSE_HOST,
            CLICKHOUSE_PORT,
            target_db,
            CLICKHOUSE_USER,
            sql,
        )
        return None
    finally:
        try:
            client.close()
        except Exception:
            pass


def get_clickhouse_connection():
    """Legacy helper returning a client instance for DB API compatibility."""
    return get_clickhouse_client()


def get_clickhouse():
    """FastAPI dependency yielding a ClickHouse HTTP client context."""
    client = get_clickhouse_client()
    if client is None:
        return None

    try:
        yield client
    finally:
        try:
            client.close()
        except Exception:
            pass