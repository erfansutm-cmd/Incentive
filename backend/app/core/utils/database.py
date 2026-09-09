import os

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER

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


def execute_query(sql=None, params=None, db=None, table=None):
    """Execute a MySQL query and return the results.
    
    This function supports two modes:
    
    1. Raw SQL mode: Provide custom SQL query string in `sql`.
       Use `params` for parameter binding.
       
    2. Automatic query mode: Provide `table` name (optionally with `db` database name).
       The function will build a SELECT * query automatically.
       
    If neither `sql` nor (`db` and `table`) are provided, a basic "SELECT 1" query is used
    for testing connectivity.
    
    Args:
        sql: SQL query string. If building automatic query, use "SELECT * FROM table_name"
        params: Optional dictionary of parameters to bind (for raw SQL mode)
        db: Optional database name for automatic query mode
        table: Optional table name for automatic query mode
        
    Returns:
        List of dictionaries representing the query results, or None if no rows returned
        
    Example:
        # Automatic mode - SELECT * from specific table in specific database
        results = execute_query(db="incentive", table="business_entities")
        
        # Raw SQL mode
        results = execute_query(sql="SELECT * FROM users WHERE id = %s", {"id": 1})
        
        # Automatic mode without database (uses current DB)
        results = execute_query(table="users")
        
        # Default connectivity test
        results = execute_query()
    """
    with SessionLocal() as session:
        # If db and table are provided, build a SELECT query automatically
        if db and table:
            # Build a SELECT query with the specified database and table
            # For MySQL, use db.table format with backtick-quoted parts
            db_backtick = f"`{db.replace('`', '``')}`"
            table_backtick = f"`{table.replace('`', '``')}`"
            sql = f"SELECT * FROM {db_backtick}.{table_backtick}"
            result = session.execute(text(sql), params or {})
        elif sql is None:
            # Default: basic connectivity test
            sql = "SELECT 1 as test"
            result = session.execute(text(sql), params or {})
        else:
            # Use raw SQL provided
            result = session.execute(text(sql), params or {})
        
        if result.returns_rows:
            columns = result.keys()
            rows = result.fetchall()
            return [dict(zip(columns, row)) for row in rows]
        else:
            return None