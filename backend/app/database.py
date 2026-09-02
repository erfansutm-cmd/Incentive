import os

from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import declarative_base, sessionmaker

# MySQL connection settings — read from environment variables
# (set in docker-compose.yml, which reads them from the root .env file).
DB_USER = os.getenv("DB_USER", "erfan.mohamadi")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_HOST = os.getenv("DB_HOST", "172.21.41.75")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_NAME = os.getenv("DB_NAME", "")  # optional: empty = no default schema selected

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
    one (``other_schema.business_entities``) so tables can live in another
    database on the same server. Backticks inside a part are escaped by
    doubling them; anything else is rejected.
    """
    parts = [p.strip().strip("`") for p in str(name).split(".")]
    parts = [p for p in parts if p]
    if not parts or len(parts) > 2:
        raise ValueError(f"Invalid table name: {name!r} (expected 'table' or 'schema.table')")
    return ".".join(f"`{p.replace('`', '``')}`" for p in parts)


def get_db():
    """FastAPI dependency that yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
