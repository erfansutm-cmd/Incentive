import datetime
import decimal
import json
import os

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from .database import engine, quote_table

TABLE_NAME = os.getenv("DB_BUSINESS_ENTITIES_TABLE", "business_entities")
TABLE_SQL = quote_table(TABLE_NAME)  # quoted, may be "schema/table"

# Columns that store JSON arrays (customer id lists / delivery category lists).
# These are returned to the UI as real arrays and accepted back as arrays.
JSON_ARRAY_COLUMNS = {
    "include_customer_id",
    "exclude_customer_id",
    "include_delivery_category",
    "exclude_delivery_category",
}

router = APIRouter(prefix="/api/business-entities", tags=["business-entities"])


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


def _parse_json_array(value):
    """Normalize a JSON-array column value to a Python list (or None).

    MySQL JSON columns come back as raw JSON text through PyMySQL; TEXT/VARCHAR
    columns holding JSON do the same. Lists pass through untouched.
    """
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return list(value)
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8", errors="replace")
    if isinstance(value, str):
        text_value = value.strip()
        if not text_value:
            return None
        try:
            parsed = json.loads(text_value)
        except (ValueError, TypeError):
            return value  # not JSON — return as-is rather than crashing
        return parsed if isinstance(parsed, list) else value
    return value


def _dump_json_array(value):
    """Serialize a payload value for a JSON-array column to a JSON string."""
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return json.dumps(list(value), ensure_ascii=False)
    if isinstance(value, str):
        text_value = value.strip()
        if not text_value:
            return None
        try:
            parsed = json.loads(text_value)
        except (ValueError, TypeError):
            # not JSON — accept a plain comma-separated list of values
            parsed = [p.strip() for p in text_value.split(",") if p.strip()]
        return json.dumps(parsed if isinstance(parsed, list) else [parsed], ensure_ascii=False)
    # single scalar (e.g. one customer id)
    return json.dumps([value], ensure_ascii=False)


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
        rows = conn.execute(text(f"SHOW COLUMNS FROM {TABLE_SQL}"))
        return [dict(r._mapping) for r in rows]


def _primary_key(cols):
    for c in cols:
        if c.get("Key") == "PRI":
            return c["Field"]
    return None


def _clean_payload(payload, cols):
    """Keep only real columns (whitelist) and serialize JSON-array columns.

    Regular columns: empty strings become NULL (same as the cities endpoint).
    JSON-array columns: lists/tuples/scalars are serialized to JSON text.
    """
    allowed = {c["Field"] for c in cols}
    data = {}
    for key, value in payload.items():
        if key not in allowed:
            continue
        if key in JSON_ARRAY_COLUMNS:
            data[key] = _dump_json_array(value)
        else:
            data[key] = None if value in (None, "") else value
    return data


@router.get("")
def list_entities():
    try:
        cols = _columns()
        pk = _primary_key(cols)
        order = f" ORDER BY `{pk}`" if pk else ""
        with engine.connect() as conn:
            rows = conn.execute(text(f"SELECT * FROM {TABLE_SQL}{order}"))
            data = []
            for r in rows:
                row = {}
                for k, v in r._mapping.items():
                    if k in JSON_ARRAY_COLUMNS:
                        row[k] = _parse_json_array(v)
                    else:
                        row[k] = _jsonable(v)
                data.append(row)
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
                "json_array": c["Field"] in JSON_ARRAY_COLUMNS,
            }
            for c in cols
        ],
        "rows": data,
    }


@router.post("")
async def add_entity(payload: dict):
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

    if not any(v is not None for v in data.values()):
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "Please fill at least one field."},
        )

    names, values, params = [], [], {}
    for c in data:
        names.append(f"`{c}`")
        values.append(f":{c}")
        params[c] = data[c]

    sql = text(
        f"INSERT INTO {TABLE_SQL} ({', '.join(names)}) VALUES ({', '.join(values)})"
    )
    try:
        with engine.begin() as conn:
            conn.execute(sql, params)
    except Exception as exc:
        status, msg = _failure(exc)
        return JSONResponse(status_code=status, content={"status": "error", "message": msg})

    return {"status": "ok", "message": "Business entity added successfully."}


@router.put("/{entity_id}")
async def update_entity(entity_id: str, payload: dict):
    try:
        cols = _columns()
    except Exception as exc:
        status, msg = _failure(exc)
        return JSONResponse(status_code=status, content={"status": "error", "message": msg})

    pk = _primary_key(cols)
    if not pk:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": f"Table '{TABLE_NAME}' has no primary key; cannot edit rows.",
            },
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
    params["pk_value"] = entity_id
    sql = text(f"UPDATE {TABLE_SQL} SET {set_clause} WHERE `{pk}` = :pk_value")
    try:
        with engine.begin() as conn:
            result = conn.execute(sql, params)
    except Exception as exc:
        status, msg = _failure(exc)
        return JSONResponse(status_code=status, content={"status": "error", "message": msg})

    if result.rowcount == 0:
        return JSONResponse(
            status_code=404,
            content={"status": "error", "message": "Business entity not found (nothing updated)."},
        )
    return {"status": "ok", "message": "Business entity updated successfully."}


@router.delete("/{entity_id}")
async def delete_entity(entity_id: str):
    try:
        cols = _columns()
    except Exception as exc:
        status, msg = _failure(exc)
        return JSONResponse(status_code=status, content={"status": "error", "message": msg})

    pk = _primary_key(cols)
    if not pk:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": f"Table '{TABLE_NAME}' has no primary key; cannot delete rows.",
            },
        )

    sql = text(f"DELETE FROM {TABLE_SQL} WHERE `{pk}` = :pk_value")
    try:
        with engine.begin() as conn:
            result = conn.execute(sql, {"pk_value": entity_id})
    except Exception as exc:
        status, msg = _failure(exc)
        return JSONResponse(status_code=status, content={"status": "error", "message": msg})

    if result.rowcount == 0:
        return JSONResponse(
            status_code=404,
            content={"status": "error", "message": "Business entity not found."},
        )
    return {"status": "ok", "message": "Business entity deleted successfully."}
