import datetime
import decimal
import json
import os

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from ..core.database import engine, quote_table

TABLE_NAME = os.getenv("DB_BUSINESS_ENTITIES_TABLE", "business_entities")
TABLE_SQL = quote_table(TABLE_NAME)

router = APIRouter(prefix="/api/business-entities", tags=["business_entities"])


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


# Columns that should always be treated as JSON arrays even if their
# MySQL type is not JSON (e.g. TEXT/VARCHAR storing "[1,2]" or legacy data).
ARRAY_COLUMNS = {
    "include_customer_id",
    "exclude_customer_id",
    "include_delivery_category",
    "exclude_delivery_category",
    "main_customer_id",
}
CUSTOMER_ID_COLUMNS = {
    "include_customer_id",
    "exclude_customer_id",
    "main_customer_id",
}


def _is_json_column(col):
    """True when a SHOW COLUMNS row describes a MySQL JSON column or a known array column."""
    field = col.get("Field") or ""
    if field in ARRAY_COLUMNS:
        return True
    return "json" in (col.get("Type") or "").lower()


def _column_meta(col):
    """Public metadata for one column."""
    return {
        "name": col["Field"],
        "type": col["Type"],
        "nullable": col.get("Null") == "YES",
        "key": col.get("Key") or "",
        "default": _jsonable(col.get("Default")),
        "extra": col.get("Extra") or "",
        "json_array": _is_json_column(col),
    }


def _to_array(value):
    """Coerce a stored JSON value into a plain list (JSON or comma string).

    Handles a few real-world quirks seen in this table:
    - Proper JSON arrays: \"[2, 11653225]\" -> [2, 11653225]
    - Double-encoded JSON: '\"[2, 11653225]\"' -> [2, 11653225]
    - Single numbers: \"15300196\" / 15300196 -> [15300196]
    - Comma strings and bracket-wrapped strings as fallback.
    """
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")

    if isinstance(value, (int, float)):
        return [value]

    if isinstance(value, str):
        v = value.strip()
        if v in ("", "null", "NULL"):
            return []

        # Try up to 3 levels of JSON decoding to unwind double-encoded values
        # e.g. "\"[2, 11653225]\"" -> "[2, 11653225]" -> [2, 11653225]
        cur = v
        for _ in range(3):
            try:
                parsed = json.loads(cur)
            except (ValueError, TypeError):
                break

            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, (int, float)):
                return [parsed]
            if isinstance(parsed, str):
                s = parsed.strip()
                if s in ("", "null", "NULL"):
                    return []
                # If the string itself is a JSON array, loop again to decode it
                # If it's a plain number string, convert it
                if s.startswith("[") and s.endswith("]"):
                    cur = s
                    continue
                # numeric string like "15300196"
                if s.lstrip("-").isdigit():
                    try:
                        return [int(s)]
                    except ValueError:
                        pass
                # Check if it's a comma list inside a string
                cur = s
                continue
            # dict or other -> wrap
            if parsed is not None:
                return [parsed]
            break

        # Fallback: strip surrounding brackets/quotes and split by comma
        # Handles: "[2, 11653225]", "2, 11653225", "\"2\"", etc.
        tmp = cur
        # Remove outer brackets if present
        if tmp.startswith("[") and tmp.endswith("]"):
            tmp = tmp[1:-1]
        tmp = tmp.strip()
        if not tmp:
            return []

        parts = [p.strip().strip('"').strip("'").strip() for p in tmp.split(",")]
        parts = [p for p in parts if p not in ("", "null", "NULL")]

        out = []
        for p in parts:
            # Try to preserve numbers as numbers
            try:
                if p.lstrip("-").isdigit():
                    out.append(int(p))
                    continue
                # float?
                fv = float(p)
                # if it's integer-like, keep int version? keep float
                out.append(fv)
                continue
            except ValueError:
                pass
            out.append(p)
        return out

    return [value]


def _row_data(mapping, json_cols):
    """Serialize a DB row for the client, expanding JSON columns to arrays."""
    data = {}
    for k, v in mapping.items():
        if k in json_cols:
            data[k] = _to_array(v)
        else:
            data[k] = _jsonable(v)
    return data


def _clean_payload(payload, cols):
    """Keep only real columns (whitelist), expand lists for JSON columns.

    Plain-empty values become NULL. Values meant for a JSON column are
    serialized to a JSON string if they arrive as a list (or comma string).
    """
    json_cols = {c["Field"] for c in cols if _is_json_column(c)}
    allowed = {c["Field"] for c in cols} - {"updated_at", "deactivated_at"}
    data = {}
    for key, value in payload.items():
        if key not in allowed:
            continue
        if value in (None, ""):
            data[key] = None
        elif key in json_cols:
            data[key] = json.dumps(_to_array(value))
        else:
            data[key] = value
    return data


@router.get("")
def list_business_entities():
    try:
        cols = _columns()
        json_cols = {c["Field"] for c in cols if _is_json_column(c)}
        pk = _primary_key(cols)
        order = f" ORDER BY `{pk}`" if pk else ""
        with engine.connect() as conn:
            rows = conn.execute(text(f"SELECT * FROM {TABLE_SQL}{order}"))
            data = [_row_data(r._mapping, json_cols) for r in rows]
    except Exception as exc:
        status, msg = _failure(exc)
        return JSONResponse(status_code=status, content={"status": "error", "message": msg})

    return {
        "columns": [_column_meta(c) for c in cols],
        "rows": data,
    }


@router.post("")
async def add_business_entity(payload: dict):
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

    # Set the audit timestamp on creation too, independent of DB defaults.
    if any(c["Field"] == "updated_at" for c in cols):
        names.append("`updated_at`")
        values.append("CURRENT_TIMESTAMP")

    sql = text(f"INSERT INTO {TABLE_SQL} ({', '.join(names)}) VALUES ({', '.join(values)})")
    try:
        with engine.begin() as conn:
            conn.execute(sql, params)
    except Exception as exc:
        status, msg = _failure(exc)
        return JSONResponse(status_code=status, content={"status": "error", "message": msg})

    return {"status": "ok", "message": "Business entity added successfully."}


@router.put("/{entity_id}")
async def update_business_entity(entity_id: str, payload: dict):
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
    if any(c["Field"] == "updated_at" for c in cols):
        set_clause += ", `updated_at` = CURRENT_TIMESTAMP"
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


@router.post("/{entity_id}/deactivate")
async def deactivate_business_entity(entity_id: str):
    try:
        cols = _columns()
        pk = _primary_key(cols)
        fields = {c["Field"] for c in cols}
        if not pk or "deactivated_at" not in fields:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "Table requires a primary key and deactivated_at to deactivate entities."},
            )
        assignments = "`deactivated_at` = CURRENT_TIMESTAMP"
        if "updated_at" in fields:
            assignments += ", `updated_at` = CURRENT_TIMESTAMP"
        with engine.begin() as conn:
            result = conn.execute(
                text(f"UPDATE {TABLE_SQL} SET {assignments} "
                     f"WHERE `{pk}` = :pk_value AND `deactivated_at` IS NULL"),
                {"pk_value": entity_id},
            )
        if result.rowcount == 0:
            return JSONResponse(
                status_code=404,
                content={"status": "error", "message": "Business entity not found or already deactivated."},
            )
    except Exception as exc:
        status, msg = _failure(exc)
        return JSONResponse(status_code=status, content={"status": "error", "message": msg})
    return {"status": "ok", "message": "Business entity deactivated successfully."}
