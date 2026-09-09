import os

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME

# URL.create() takes care of escaping special characters in the password.
DATABASE_URL = URL.create(
    drivername="mysql+pymysql",
    username=DB_USER,
    password=DB_PASSWORD,
    host=DB_HOST,
    port=DB_PORT,
    database=DB_NAME or None,
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=3600)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()


def quote_table(name):
    """Return a safely-quoted MySQL table reference.

    Accepts a plain table name (``business_entities``) or a schema-qualified
    one in ``schema/table`` form (``other_schema/business_entities``), so a
    table can live in another database on the same server. Backticks inside a
    part are escaped by doubling them; anything else is rejected.
    """
    text_name = str(name).strip()
    if "." in text_name:
        raise ValueError(
            f"Invalid table name: {name!r} — use 'schema/table', not 'schema.table'"
        )
    parts = [p.strip().strip("`") for p in text_name.split("/")]
    parts = [p for p in parts if p]
    if not parts or len(parts) > 2:
        raise ValueError(f"Invalid table name: {name!r} (expected 'table' or 'schema/table')")
    return ".".join(f"`{p.replace('`', '``')}`" for p in parts)


def get_db():
    """FastAPI dependency that yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def execute_query(sql, params=None):
    """Execute a MySQL query and return the results.
    
    Args:
        sql: SQL query string
        params: Optional dictionary of parameters to bind
        
    Returns:
        List of dictionaries representing the query results, or None if no rows returned
    """
    with SessionLocal() as session:
        result = session.execute(text(sql), params or {})
        if result.returns_rows:
            columns = result.keys()
            rows = result.fetchall()
            return [dict(zip(columns, row)) for row in rows]
        else:
            return None