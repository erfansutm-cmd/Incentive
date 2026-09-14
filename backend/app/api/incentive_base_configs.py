import datetime
import decimal

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.utils.database import engine, quote_table
from app.core.config import DB_INCENTIVE_BASE_CONFIG_TABLE as TABLE_NAME

# Base allocation configs behind a plan:
#   id | plan_id | listing_id | allocator_id | rule_name | impact_ratio |
#   duration | districts | vendors | batch_size | clustering_method |
#   sensitivity_id | sensitivity_group
# A plan (incentive_city_plan_mapping row) owns one row per allocator; the
# rows are matched to their plan on `plan_id` = the plan's primary key, and
# their `impact_ratio` values are the share of the plan each allocator gets.
# Configured like the other tables: "table" or "schema/table".

TABLE_SQL = quote_table(TABLE_NAME)  # quoted, may be "schema/table"

PLAN_ID_COLUMN = "plan_id"
RATIO_COLUMN = "impact_ratio"
DEACTIVATED_COLUMN = "deactivated_at"

# The four columns the plan detail page shows up front; the rest of a row is
# revealed behind its dropdown. Reported back to the client so the UI and the
# API agree even when the schema differs.
SUMMARY_COLUMNS = ("listing_id", "allocator_id", "rule_name", "impact_ratio")

router = APIRouter(prefix="/api/incentive-base-configs", tags=["incentive-base-configs"])


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


def _column_meta(cols):
    return [
        {
            "name": c["Field"],
            "type": c["Type"],
            "nullable": c.get("Null") == "YES",
            "key": c.get("Key") or "",
            "default": _jsonable(c.get("Default")),
            "extra": c.get("Extra") or "",
        }
        for c in cols
    ]


@router.get("")
def list_base_configs(
    plan_id: str = Query(default="", description="Match rows on this plan_id"),
):
    """List the base configs (allocators) of one plan.

    The plan detail page (`/plans/:id`) calls this with the plan's id: it shows
    ``listing_id``, ``allocator_id``, ``rule_name`` and ``impact_ratio`` up
    front and reveals the remaining columns behind a per-row dropdown. Rows are
    grouped by ``listing_id`` with the biggest ``impact_ratio`` first, so a
    listing's dominant allocator leads.

    Like the other lookups, a ``deactivated_at`` column (when the table has one)
    hides deactivated rows; the plan's other columns are unaffected.
    """
    plan_id = (plan_id or "").strip()
    if not plan_id:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "Query parameter 'plan_id' is required."},
        )

    try:
        cols = _columns()
    except Exception as exc:
        status, msg = _failure(exc)
        return JSONResponse(status_code=status, content={"status": "error", "message": msg})

    fields = {c["Field"] for c in cols}
    if PLAN_ID_COLUMN not in fields:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": f"Table '{TABLE_NAME}' has no '{PLAN_ID_COLUMN}' column.",
            },
        )

    where = f"WHERE `{PLAN_ID_COLUMN}` = :plan_id"
    if DEACTIVATED_COLUMN in fields:
        where += f" AND `{DEACTIVATED_COLUMN}` IS NULL"

    # Order only by columns the table actually has; NULL ratios sort last.
    order_parts = [f"`{c}`" for c in ("listing_id",) if c in fields]
    if RATIO_COLUMN in fields:
        order_parts.append(f"`{RATIO_COLUMN}` DESC")
    pk = _primary_key(cols) or ("id" if "id" in fields else None)
    if pk:
        order_parts.append(f"`{pk}`")
    order = f" ORDER BY {', '.join(order_parts)}" if order_parts else ""

    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(f"SELECT * FROM {TABLE_SQL} {where}{order}"),
                {"plan_id": plan_id},
            )
            data = [{k: _jsonable(v) for k, v in r._mapping.items()} for r in rows]
    except Exception as exc:
        status, msg = _failure(exc)
        return JSONResponse(status_code=status, content={"status": "error", "message": msg})

    # Sum of the returned ratios: a plan's allocators normally add up to 1.
    ratio_sum = None
    if RATIO_COLUMN in fields:
        ratios = [
            row[RATIO_COLUMN]
            for row in data
            if isinstance(row.get(RATIO_COLUMN), (int, float))
            and not isinstance(row.get(RATIO_COLUMN), bool)
        ]
        if ratios:
            ratio_sum = round(sum(ratios), 6)

    return {
        "plan_id": plan_id,
        "columns": _column_meta(cols),
        "summary_columns": [c for c in SUMMARY_COLUMNS if c in fields],
        "rows": data,
        "total": len(data),
        "impact_ratio_sum": ratio_sum,
    }
