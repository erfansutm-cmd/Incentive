import datetime
import decimal
import os

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from sqlalchemy import text

from .database import engine, quote_table

# Table holding the per-city plan mapping:
#   id | city_id | incentive_type_id | business_entity | created_at | deactivated_at
# Configured the same way as the other tables: "table" or "schema/table".
TABLE_NAME = os.getenv("DB_CITY_PLAN_MAPPING_TABLE", "incentive/incentive_city_plan_mapping")
TABLE_SQL = quote_table(TABLE_NAME)  # quoted, may be "schema/table"

CITY_ID_COLUMN = "city_id"
DEACTIVATED_COLUMN = "deactivated_at"

router = APIRouter(prefix="/api/city-plan-mappings", tags=["city-plan-mappings"])


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
def list_mappings(
    city_id: str = Query(default="", description="Match rows on this city_id"),
    include_deactivated: bool = Query(
        default=False,
        description="When false (default) only rows with deactivated_at IS NULL are returned.",
    ),
):
    """List incentive_city_plan_mapping rows for one city.

    The Cities UI calls this when a city row is expanded: it shows the active
    mappings (``deactivated_at IS NULL``) first and reveals the deactivated
    ones behind a "Show deactivated" button (``include_deactivated=true``).
    """
    city_id = (city_id or "").strip()
    if not city_id:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "Query parameter 'city_id' is required."},
        )

    try:
        cols = _columns()
    except Exception as exc:
        status, msg = _failure(exc)
        return JSONResponse(status_code=status, content={"status": "error", "message": msg})

    fields = {c["Field"] for c in cols}
    if CITY_ID_COLUMN not in fields:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": f"Table '{TABLE_NAME}' has no '{CITY_ID_COLUMN}' column.",
            },
        )
    has_deactivated = DEACTIVATED_COLUMN in fields

    pk = _primary_key(cols)
    if pk:
        order = f" ORDER BY `{pk}`"
    elif "id" in fields:
        order = " ORDER BY `id`"
    else:
        order = ""

    where = f"WHERE `{CITY_ID_COLUMN}` = :city_id"
    if has_deactivated and not include_deactivated:
        where += f" AND `{DEACTIVATED_COLUMN}` IS NULL"

    try:
        with engine.connect() as conn:
            # Counts always cover both active and deactivated rows, so the UI
            # can label the "Show deactivated (N)" button even when only the
            # active rows are fetched.
            if has_deactivated:
                counts = conn.execute(
                    text(
                        f"SELECT COUNT(*) AS total, "
                        f"COALESCE(SUM(CASE WHEN `{DEACTIVATED_COLUMN}` IS NULL "
                        f"THEN 1 ELSE 0 END), 0) AS active "
                        f"FROM {TABLE_SQL} WHERE `{CITY_ID_COLUMN}` = :city_id"
                    ),
                    {"city_id": city_id},
                ).first()
                total = int(counts._mapping["total"] or 0)
                active_count = int(counts._mapping["active"] or 0)
                deactivated_count = total - active_count
            else:
                counts = conn.execute(
                    text(
                        f"SELECT COUNT(*) AS total FROM {TABLE_SQL} "
                        f"WHERE `{CITY_ID_COLUMN}` = :city_id"
                    ),
                    {"city_id": city_id},
                ).first()
                total = int(counts._mapping["total"] or 0)
                active_count = total
                deactivated_count = 0

            rows = conn.execute(
                text(f"SELECT * FROM {TABLE_SQL} {where}{order}"),
                {"city_id": city_id},
            )
            data = [{k: _jsonable(v) for k, v in r._mapping.items()} for r in rows]
    except Exception as exc:
        status, msg = _failure(exc)
        return JSONResponse(status_code=status, content={"status": "error", "message": msg})

    return {
        "city_id": city_id,
        "include_deactivated": include_deactivated,
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
        "active_count": active_count,
        "deactivated_count": deactivated_count,
        "total": total,
    }


REQUIRED_COLUMNS = ("city_id", "incentive_type_id", "business_entity")


@router.post("")
async def add_mapping(payload: dict):
    """Insert a new plan (active by default: deactivated_at = NULL)."""
    try:
        cols = _columns()
    except Exception as exc:
        status, msg = _failure(exc)
        return JSONResponse(status_code=status, content={"status": "error", "message": msg})

    fields = {c["Field"] for c in cols}
    missing = [c for c in REQUIRED_COLUMNS if c not in fields]
    if missing:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": f"Table '{TABLE_NAME}' has no column(s): {', '.join(missing)}.",
            },
        )

    data = {}
    for c in REQUIRED_COLUMNS:
        v = (payload or {}).get(c)
        if isinstance(v, str):
            v = v.strip()
        if v in (None, ""):
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": f"'{c}' is required."},
            )
        data[c] = v

    names, values, params = [], [], {}
    for c, v in data.items():
        names.append(f"`{c}`")
        values.append(f":{c}")
        params[c] = v
    # Managed columns: created_at = now, deactivated_at = NULL (active by default).
    if "created_at" in fields:
        names.append("`created_at`")
        values.append("NOW()")
    if DEACTIVATED_COLUMN in fields:
        names.append(f"`{DEACTIVATED_COLUMN}`")
        values.append("NULL")

    sql = text(f"INSERT INTO {TABLE_SQL} ({', '.join(names)}) VALUES ({', '.join(values)})")
    try:
        with engine.begin() as conn:
            conn.execute(sql, params)
    except Exception as exc:
        status, msg = _failure(exc)
        return JSONResponse(status_code=status, content={"status": "error", "message": msg})

    return {"status": "ok", "message": "Plan added successfully."}


@router.post("/{mapping_id}/deactivate")
async def deactivate_mapping(mapping_id: str):
    """Deactivate a plan by setting `deactivated_at` to NOW()."""
    try:
        cols = _columns()
    except Exception as exc:
        status, msg = _failure(exc)
        return JSONResponse(status_code=status, content={"status": "error", "message": msg})

    fields = {c["Field"] for c in cols}
    if DEACTIVATED_COLUMN not in fields:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": f"Table '{TABLE_NAME}' has no '{DEACTIVATED_COLUMN}' column.",
            },
        )
    pk = _primary_key(cols) or ("id" if "id" in fields else None)
    if not pk:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": f"Table '{TABLE_NAME}' has no primary key.",
            },
        )

    read_sql = text(f"SELECT `{DEACTIVATED_COLUMN}` FROM {TABLE_SQL} WHERE `{pk}` = :pk_value")
    try:
        with engine.connect() as conn:
            row = conn.execute(read_sql, {"pk_value": mapping_id}).first()
    except Exception as exc:
        status, msg = _failure(exc)
        return JSONResponse(status_code=status, content={"status": "error", "message": msg})

    if row is None:
        return JSONResponse(
            status_code=404,
            content={"status": "error", "message": "Plan not found."},
        )
    if row._mapping[DEACTIVATED_COLUMN] is not None:
        return {"status": "ok", "message": "Plan is already deactivated.", "active": False}

    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    f"UPDATE {TABLE_SQL} SET `{DEACTIVATED_COLUMN}` = NOW() "
                    f"WHERE `{pk}` = :pk_value"
                ),
                {"pk_value": mapping_id},
            )
    except Exception as exc:
        status, msg = _failure(exc)
        return JSONResponse(status_code=status, content={"status": "error", "message": msg})

    return {"status": "ok", "message": "Plan deactivated successfully.", "active": False}
