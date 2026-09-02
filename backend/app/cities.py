import datetime
import decimal
import os

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from .database import engine

TABLE_NAME = os.getenv("DB_CITIES_TABLE", "cities")

router = APIRouter(prefix="/api/cities", tags=["cities"])


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


def _failure(exc):
    """Map a database exception to a (status_code, message) pair."""
    orig = getattr(exc, "orig", None)
    args = getattr(orig, "args", ()) if orig is not None else ()
    if isinstance(args, tuple) and len(args) >= 2 and isinstance(args[0], int):
        code, msg = args[0], args[1]
        if code == 1146:  # ER_NO_SUCH_TABLE
            return 404, f"Table '{TABLE_NAME}' does not exist in the database."
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
        rows = conn.execute(text(f"SHOW COLUMNS FROM `{TABLE_NAME}`"))
        return [dict(r._mapping) for r in rows]


def _primary_key(cols):
    for c in cols:
        if c.get("Key") == "PRI":
            return c["Field"]
    return None


def _clean_payload(payload, cols):
    """Keep only real columns (whitelist) and treat empty strings as NULL."""
    allowed = {c["Field"] for c in cols}
    data = {}
    for key, value in payload.items():
        if key not in allowed:
            continue
        data[key] = None if value in (None, "") else value
    return data


@router.get("")
def list_cities():
    try:
        cols = _columns()
        with engine.connect() as conn:
            rows = conn.execute(text(f"SELECT * FROM `{TABLE_NAME}`"))
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


@router.post("")
async def add_city(payload: dict):
    try:
        cols = _columns()
    except Exception as exc:
        status, msg = _failure(exc)
        return JSONResponse(status_code=status, content={"status": "error", "message": msg})

    pk = _primary_key(cols)
    data = _clean_payload(payload, cols)
    # Never insert the auto-increment primary key.
    if pk and any(
        c["Field"] == pk and "auto_increment" in (c.get("Extra") or "") for c in cols
    ):
        data.pop(pk, None)

    if not data:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "No valid fields to insert."},
        )

    names = ", ".join(f"`{c}`" for c in data)
    placeholders = ", ".join(f":{c}" for c in data)
    sql = text(f"INSERT INTO `{TABLE_NAME}` ({names}) VALUES ({placeholders})")
    try:
        with engine.begin() as conn:
            conn.execute(sql, data)
    except Exception as exc:
        status, msg = _failure(exc)
        return JSONResponse(status_code=status, content={"status": "error", "message": msg})

    return {"status": "ok", "message": "City added successfully."}


@router.put("/{city_id}")
async def update_city(city_id: str, payload: dict):
    try:
        cols = _columns()
    except Exception as exc:
        status, msg = _failure(exc)
        return JSONResponse(status_code=status, content={"status": "error", "message": msg})

    pk = _primary_key(cols)
    if not pk:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": f"Table '{TABLE_NAME}' has no primary key; cannot edit rows."},
        )

    data = _clean_payload(payload, cols)
    data.pop(pk, None)
    if not data:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "No valid fields to update."},
        )

    set_clause = ", ".join(f"`{c}` = :{c}" for c in data)
    params = dict(data)
    params["pk_value"] = city_id
    sql = text(f"UPDATE `{TABLE_NAME}` SET {set_clause} WHERE `{pk}` = :pk_value")
    try:
        with engine.begin() as conn:
            result = conn.execute(sql, params)
    except Exception as exc:
        status, msg = _failure(exc)
        return JSONResponse(status_code=status, content={"status": "error", "message": msg})

    if result.rowcount == 0:
        return JSONResponse(
            status_code=404,
            content={"status": "error", "message": "City not found (nothing updated)."},
        )
    return {"status": "ok", "message": "City updated successfully."}


@router.delete("/{city_id}")
async def delete_city(city_id: str):
    try:
        cols = _columns()
    except Exception as exc:
        status, msg = _failure(exc)
        return JSONResponse(status_code=status, content={"status": "error", "message": msg})

    pk = _primary_key(cols)
    if not pk:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": f"Table '{TABLE_NAME}' has no primary key; cannot delete rows."},
        )

    sql = text(f"DELETE FROM `{TABLE_NAME}` WHERE `{pk}` = :pk_value")
    try:
        with engine.begin() as conn:
            result = conn.execute(sql, {"pk_value": city_id})
    except Exception as exc:
        status, msg = _failure(exc)
        return JSONResponse(status_code=status, content={"status": "error", "message": msg})

    if result.rowcount == 0:
        return JSONResponse(
            status_code=404,
            content={"status": "error", "message": "City not found."},
        )
    return {"status": "ok", "message": "City deleted successfully."}
