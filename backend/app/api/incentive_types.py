import datetime
import decimal
import os

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from ..core.database import engine, quote_table

# Lookup table for plan-mapping types:
#   id | name | created_at
# Used by the Cities slide-down panel to map incentive_type_id -> name and to
# fill the "Add plan" type dropdown. Configured like the other tables:
# "table" or "schema/table".
TABLE_NAME = os.getenv("DB_INCENTIVE_TYPE_TABLE", "mafsho/incentive_type")
TABLE_SQL = quote_table(TABLE_NAME)  # quoted, may be "schema/table"

router = APIRouter(prefix="/api/incentive-types", tags=["incentive-types"])


def _jsonable(value):
    """Convert a DB value into a JSON-serializable Python type."""
    if value is None:
        return None
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, (dict, list, int, float, str, bool)):
        return value
    return str(value)


def _failure(exc, table=None):
    """Map a database exception to a (status_code, message) pair."""
    table = table or TABLE_NAME
    orig = getattr(exc, "orig", None)
    args = getattr(orig, "args", ()) if orig is not None else ()
    if isinstance(args, tuple) and len(args) >= 2 and isinstance(args[0], int):
        code, msg = args[0], args[1]
        if code == 1146:  # ER_NO_SUCH_TABLE
            return 404, f"Table '{table}' does not exist in the database."
        if code == 2003:  # can't connect
            return 503, f"Cannot connect to the database: {msg}"
        if code in (1045, 1044):  # access denied
            return 503, f"Database access denied: {msg}"
        if code == 1049:  # unknown database
            return 503, f"Unknown database: {msg}"
        return 400, msg
    return 500, str(exc)


def _columns():
    """Return the table's columns from SHOW COLUMNS."""
    with engine.connect() as conn:
        rows = conn.execute(text(f"SHOW COLUMNS FROM {TABLE_SQL}"))
        return [dict(r._mapping) for r in rows]


def _primary_key(cols):
    for c in cols:
        if c.get("Key") == "PRI":
            return c["Field"]
    return None


@router.get("")
def list_types():
    """List all incentive types (id, name, created_at) ordered by id."""
    try:
        cols = _columns()
        pk = _primary_key(cols)
        if pk:
            order = f" ORDER BY `{pk}`"
        elif "id" in {c["Field"] for c in cols}:
            order = " ORDER BY `id`"
        else:
            order = ""
        with engine.connect() as conn:
            rows = conn.execute(text(f"SELECT * FROM {TABLE_SQL}{order}"))
            data = [{k: _jsonable(v) for k, v in r._mapping.items()} for r in rows]
    except Exception as exc:
        status, msg = _failure(exc)
        return JSONResponse(status_code=status, content={"status": "error", "message": msg})

    return {
        "columns": [
            {
                "name": c["Field"],
                "type": c["Type"],
                "nullable": c.get("Null") == "YES",
                "key": c.get("Key") or "",
                "default": _jsonable(c.get("Default")),
                "extra": c.get("Extra") or "",
            }
            for c in cols
        ],
        "rows": data,
    }
