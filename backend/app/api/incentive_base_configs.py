import datetime
import decimal

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.utils.database import engine, quote_table
from app.core.config import (
    DB_INCENTIVE_BASE_CONFIG_TABLE as TABLE_NAME,
    DB_INCENTIVE_BASE_CONFIG_LOG_TABLE as LOG_TABLE_NAME,
)

# Base allocation configs behind a plan:
#   id | plan_id | listing_id | allocator_id | rule_name | impact_ratio |
#   duration | districts | vendors | batch_size | clustering_method |
#   sensitivity_id | sensitivity_group | created_at | updated_at | deactivated_at
# A plan (incentive_city_plan_mapping row) owns one row per allocator; the
# rows are matched to their plan on `plan_id` = the plan's primary key, and
# their `impact_ratio` values are the share of the plan each allocator gets.
#
# Every write through this API first copies the row as it was *before* the
# change into the log table:
#   log_id | config_id | <the same columns as above> | changed_at
# so the previous version of a config is always recoverable. Both tables are
# configured like the others: "table" or "schema/table".

TABLE_SQL = quote_table(TABLE_NAME)  # quoted, may be "schema/table"
LOG_TABLE_SQL = quote_table(LOG_TABLE_NAME)

PLAN_ID_COLUMN = "plan_id"
RATIO_COLUMN = "impact_ratio"
DEACTIVATED_COLUMN = "deactivated_at"
UPDATED_COLUMN = "updated_at"
CREATED_COLUMN = "created_at"
LOG_PK_COLUMN = "log_id"
CONFIG_ID_COLUMN = "config_id"
CHANGED_AT_COLUMN = "changed_at"

# The columns the plan detail page shows up front for each allocator; the rest
# of a row is revealed behind its dropdown. ``listing_id`` is not among them:
# it is shared by the whole plan and shown once above the table. Reported back
# to the client so the UI and the API agree even when the schema differs.
SUMMARY_COLUMNS = ("allocator_id", "rule_name", "impact_ratio")

# Columns shared by every allocator of a plan: they are read and written at
# plan level, never per row, so a plan cannot end up half-migrated.
PLAN_SHARED_COLUMNS = ("listing_id", "duration")

# Columns a per-allocator change may set; the plan-shared ones are not here.
ROW_COLUMNS = (
    "allocator_id", "rule_name", "impact_ratio", "districts", "vendors",
    "batch_size", "clustering_method", "sensitivity_id", "sensitivity_group",
)

# Columns the client cannot set through PUT: the key, the lifecycle timestamps
# (managed here) and the plan link, which would move the row to another plan.
NOT_UPDATABLE = frozenset(
    {CREATED_COLUMN, UPDATED_COLUMN, DEACTIVATED_COLUMN, PLAN_ID_COLUMN}
)

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


def _log_columns():
    """Return the log table's columns from SHOW COLUMNS."""
    with engine.connect() as conn:
        rows = conn.execute(text(f"SHOW COLUMNS FROM {LOG_TABLE_SQL}"))
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


def _as_decimal(value):
    """Return value as a Decimal when it reads as a number, else None."""
    if isinstance(value, (int, float, decimal.Decimal)) and not isinstance(value, bool):
        return decimal.Decimal(str(value))
    try:
        return decimal.Decimal(str(value).strip())
    except (AttributeError, TypeError, ValueError, decimal.InvalidOperation):
        return None


def _equal(left, right):
    """Compare a stored value with an incoming one (0.4 == '0.4' == 0.4000)."""
    if left is None or right is None:
        return left is None and right is None
    if isinstance(left, bool) or isinstance(right, bool):
        return left == right
    # A decimal column read back as 0.4 still equals the submitted "0.4000".
    left_number, right_number = _as_decimal(left), _as_decimal(right)
    if left_number is not None and right_number is not None:
        return left_number == right_number
    return str(left) == str(right)


def _fetch_config(conn, cols, config_id):
    """Return (raw_row, pk_column) for one config, or (None, pk) when missing."""
    fields = {c["Field"] for c in cols}
    pk = _primary_key(cols) or ("id" if "id" in fields else None)
    if not pk:
        raise ValueError(f"Table '{TABLE_NAME}' has no primary key.")
    row = conn.execute(
        text(f"SELECT * FROM {TABLE_SQL} WHERE `{pk}` = :pk_value"),
        {"pk_value": config_id},
    ).first()
    return (dict(row._mapping) if row is not None else None), pk


def _insert_log(conn, log_cols, previous, config_id):
    """Copy a config row, as it was before a change, into the log table.

    Only columns the log table really has are written; ``log_id`` is left to
    auto-increment and ``changed_at`` is stamped with NOW(). Returns the new
    ``log_id`` when the driver reports one.
    """
    log_fields = [c["Field"] for c in log_cols]
    if CONFIG_ID_COLUMN not in log_fields:
        raise ValueError(f"Table '{LOG_TABLE_NAME}' has no '{CONFIG_ID_COLUMN}' column.")

    data = {
        name: previous[name]
        for name in log_fields
        if name in previous and name not in (LOG_PK_COLUMN, CONFIG_ID_COLUMN, CHANGED_AT_COLUMN)
    }
    data[CONFIG_ID_COLUMN] = config_id

    names = [f"`{name}`" for name in data]
    values = [f":{name}" for name in data]
    params = dict(data)
    if CHANGED_AT_COLUMN in log_fields:
        names.append(f"`{CHANGED_AT_COLUMN}`")
        values.append("NOW()")

    result = conn.execute(
        text(f"INSERT INTO {LOG_TABLE_SQL} ({', '.join(names)}) VALUES ({', '.join(values)})"),
        params,
    )
    return getattr(result, "lastrowid", None)


def _insert_config(conn, cols, data):
    """Insert a new config row; returns its new primary key value.

    ``created_at`` is stamped with NOW() and the row starts active
    (``deactivated_at`` NULL). Only columns the table really has are written.
    """
    fields = {c["Field"] for c in cols}
    pk = _primary_key(cols)
    values = {
        name: value
        for name, value in data.items()
        if name in fields and name != pk
    }
    names = [f"`{name}`" for name in values]
    binds = [f":{name}" for name in values]
    params = dict(values)
    for name, literal in (
        (CREATED_COLUMN, "NOW()"), (UPDATED_COLUMN, "NULL"), (DEACTIVATED_COLUMN, "NULL"),
    ):
        if name in fields:
            names.append(f"`{name}`")
            binds.append(literal)

    result = conn.execute(
        text(f"INSERT INTO {TABLE_SQL} ({', '.join(names)}) VALUES ({', '.join(binds)})"),
        params,
    )
    return getattr(result, "lastrowid", None)


def _active_plan_rows(conn, cols, plan_id):
    """Return the plan's active rows (raw values), ordered like the listing."""
    fields = {c["Field"] for c in cols}
    pk = _primary_key(cols) or ("id" if "id" in fields else None)
    where = f"WHERE `{PLAN_ID_COLUMN}` = :plan_id"
    if DEACTIVATED_COLUMN in fields:
        where += f" AND `{DEACTIVATED_COLUMN}` IS NULL"
    order = f" ORDER BY `{pk}`" if pk else ""
    rows = conn.execute(
        text(f"SELECT * FROM {TABLE_SQL} {where}{order}"), {"plan_id": plan_id}
    )
    return [dict(r._mapping) for r in rows], pk


def _shared_conflicts(payload, shared, fields):
    """Plan-shared columns whose submitted value differs from the plan's."""
    conflicts = []
    for name in PLAN_SHARED_COLUMNS:
        if name not in fields:
            continue
        submitted = (payload or {}).get(name)
        if submitted in (None, ""):
            continue
        if not _equal(shared.get(name), submitted):
            conflicts.append(
                {
                    "column": name,
                    "plan": _jsonable(shared.get(name)),
                    "submitted": _jsonable(submitted),
                }
            )
    return conflicts


@router.post("")
async def add_config(payload: dict):
    """Add an allocator to a plan.

    ``listing_id`` and ``duration`` belong to the plan, not to the row: when
    the plan already has active allocators they are copied from them, and a
    payload asking for different ones is rejected with 409 (change them for
    the whole plan instead). The first allocator of a plan sets them.
    """
    try:
        cols = _columns()
    except Exception as exc:
        status, msg = _failure(exc)
        return JSONResponse(status_code=status, content={"status": "error", "message": msg})

    fields = {c["Field"] for c in cols}
    missing = [c for c in ("plan_id", "allocator_id", "rule_name", "impact_ratio") if c not in fields]
    if missing:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": f"Table '{TABLE_NAME}' has no column(s): {', '.join(missing)}.",
            },
        )

    data = {}
    for name in ("plan_id", "allocator_id", "rule_name", "impact_ratio"):
        value = (payload or {}).get(name)
        if isinstance(value, str):
            value = value.strip()
        if value in (None, ""):
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": f"'{name}' is required."},
            )
        data[name] = value

    # the remaining per-allocator columns are optional
    for name in ROW_COLUMNS:
        if name in data or name not in fields or name not in (payload or {}):
            continue
        value = payload[name]
        data[name] = None if value == "" else value

    try:
        with engine.connect() as conn:
            existing, _ = _active_plan_rows(conn, cols, data["plan_id"])
    except Exception as exc:
        status, msg = _failure(exc)
        return JSONResponse(status_code=status, content={"status": "error", "message": msg})

    inherited = {}
    if existing:
        shared = {name: existing[0].get(name) for name in PLAN_SHARED_COLUMNS}
        conflicts = _shared_conflicts(payload, shared, fields)
        if conflicts:
            return JSONResponse(
                status_code=409,
                content={
                    "status": "error",
                    "message": (
                        "listing_id and duration are shared by every allocator of the plan; "
                        "change them for all allocators at once."
                    ),
                    "conflicts": conflicts,
                },
            )
        for name in PLAN_SHARED_COLUMNS:
            if name in fields:
                data[name] = shared.get(name)
        inherited = {name: _jsonable(shared.get(name)) for name in PLAN_SHARED_COLUMNS}
    else:
        listing = (payload or {}).get("listing_id")
        if isinstance(listing, str):
            listing = listing.strip()
        if listing in (None, ""):
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "message": "'listing_id' is required for the first allocator of a plan.",
                },
            )
        if "listing_id" in fields:
            data["listing_id"] = listing
        if "duration" in fields:
            duration = (payload or {}).get("duration")
            data["duration"] = None if duration == "" else duration

    try:
        with engine.begin() as conn:
            new_id = _insert_config(conn, cols, data)
            pk = _primary_key(cols)
            row = None
            if new_id is not None and pk:
                found = conn.execute(
                    text(f"SELECT * FROM {TABLE_SQL} WHERE `{pk}` = :pk_value"),
                    {"pk_value": new_id},
                ).first()
                row = {k: _jsonable(v) for k, v in found._mapping.items()} if found else None
    except Exception as exc:
        status, msg = _failure(exc)
        return JSONResponse(status_code=status, content={"status": "error", "message": msg})

    return {
        "status": "ok",
        "message": "Allocator added successfully.",
        "id": _jsonable(new_id),
        "inherited": inherited,
        "row": row,
    }


@router.put("/plan/{plan_id}")
async def update_plan_shared(plan_id: str, payload: dict):
    """Change ``listing_id`` / ``duration`` for every allocator of a plan.

    Those two columns are the same on every row of a plan, so they are edited
    once, here: each affected row is logged (its values before the change) and
    updated inside one transaction. Rows that already hold the new values are
    left alone and not logged.
    """
    plan_id = (plan_id or "").strip()
    if not plan_id:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "A plan id is required."},
        )

    try:
        cols = _columns()
    except Exception as exc:
        status, msg = _failure(exc)
        return JSONResponse(status_code=status, content={"status": "error", "message": msg})
    log_cols, log_error = _load_log_columns()
    if log_error is not None:
        return log_error

    fields = {c["Field"] for c in cols}
    data = {
        name: (None if value == "" else value)
        for name, value in (payload or {}).items()
        if name in PLAN_SHARED_COLUMNS and name in fields
    }
    if not data:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": (
                    "Only listing_id and duration can be changed for a whole plan; "
                    "other fields are changed per allocator."
                ),
            },
        )

    try:
        with engine.connect() as conn:
            rows, pk = _active_plan_rows(conn, cols, plan_id)
    except Exception as exc:
        status, msg = _failure(exc)
        return JSONResponse(status_code=status, content={"status": "error", "message": msg})

    if not rows:
        return JSONResponse(
            status_code=404,
            content={"status": "error", "message": "No active base configs for this plan."},
        )

    targets = [
        row for row in rows
        if any(not _equal(row.get(name), value) for name, value in data.items())
    ]
    if not targets:
        return {
            "status": "ok",
            "message": "No changes to record.",
            "logged": False,
            "updated": 0,
            "changes": {},
        }

    set_clause = ", ".join(f"`{name}` = :{name}" for name in data)
    if UPDATED_COLUMN in fields:
        set_clause += f", `{UPDATED_COLUMN}` = NOW()"
    params = dict(data)

    try:
        with engine.begin() as conn:
            log_ids = []
            for row in targets:
                log_ids.append(_insert_log(conn, log_cols, row, row[pk]))
                conn.execute(
                    text(f"UPDATE {TABLE_SQL} SET {set_clause} WHERE `{pk}` = :pk_value"),
                    {**params, "pk_value": row[pk]},
                )
            refreshed, _ = _active_plan_rows(conn, cols, plan_id)
    except Exception as exc:
        status, msg = _failure(exc)
        return JSONResponse(status_code=status, content={"status": "error", "message": msg})

    return {
        "status": "ok",
        "message": f"Updated {len(targets)} allocator(s) of plan {plan_id}.",
        "logged": True,
        "updated": len(targets),
        "log_ids": [_jsonable(v) for v in log_ids],
        "changes": {
            name: {"from": _jsonable(targets[0].get(name)), "to": _jsonable(value)}
            for name, value in data.items()
        },
        "rows": [{k: _jsonable(v) for k, v in row.items()} for row in refreshed],
    }


@router.get("")
def list_base_configs(
    plan_id: str = Query(default="", description="Match rows on this plan_id"),
    include_deactivated: bool = Query(
        default=False,
        description="When false (default) only rows with deactivated_at IS NULL are returned.",
    ),
):
    """List the base configs (allocators) of one plan.

    The plan detail page (`/plans/:id`) calls this with the plan's id: it shows
    ``listing_id``, ``allocator_id``, ``rule_name`` and ``impact_ratio`` up
    front and reveals the remaining columns behind a per-row dropdown. Rows are
    grouped by ``listing_id`` with the biggest ``impact_ratio`` first, so a
    listing's dominant allocator leads.

    A ``deactivated_at`` column (when the table has one) hides deactivated rows
    unless ``include_deactivated=true``; the counts always cover both, so the
    UI can label its "Show deactivated (N)" button. ``impact_ratio_sum`` is
    always the sum over the plan's active rows.
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
    has_deactivated = DEACTIVATED_COLUMN in fields

    where = f"WHERE `{PLAN_ID_COLUMN}` = :plan_id"
    if has_deactivated and not include_deactivated:
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

            # Counts always cover active and deactivated rows.
            if has_deactivated:
                counts = conn.execute(
                    text(
                        f"SELECT COUNT(*) AS total, "
                        f"COALESCE(SUM(CASE WHEN `{DEACTIVATED_COLUMN}` IS NULL "
                        f"THEN 1 ELSE 0 END), 0) AS active "
                        f"FROM {TABLE_SQL} WHERE `{PLAN_ID_COLUMN}` = :plan_id"
                    ),
                    {"plan_id": plan_id},
                ).first()
                total = int(counts._mapping["total"] or 0)
                active_count = int(counts._mapping["active"] or 0)
            else:
                total = len(data)
                active_count = total
            deactivated_count = total - active_count
    except Exception as exc:
        status, msg = _failure(exc)
        return JSONResponse(status_code=status, content={"status": "error", "message": msg})

    # A plan's active allocators normally add up to 1; deactivated rows and
    # rows without a ratio are left out of the sum.
    ratio_sum = None
    if RATIO_COLUMN in fields:
        ratios = [
            row[RATIO_COLUMN]
            for row in data
            if (not has_deactivated or row.get(DEACTIVATED_COLUMN) is None)
            and isinstance(row.get(RATIO_COLUMN), (int, float))
            and not isinstance(row.get(RATIO_COLUMN), bool)
        ]
        if ratios:
            ratio_sum = round(sum(ratios), 6)

    return {
        "plan_id": plan_id,
        "include_deactivated": include_deactivated,
        "columns": _column_meta(cols),
        "summary_columns": [c for c in SUMMARY_COLUMNS if c in fields],
        "rows": data,
        "total": total,
        "active_count": active_count,
        "deactivated_count": deactivated_count,
        "impact_ratio_sum": ratio_sum,
    }


@router.get("/{config_id}/logs")
def list_config_logs(config_id: str):
    """List the logged previous versions of one config, newest first.

    Each row is a config as it was *before* a change, stamped with
    ``changed_at``. Reading works without the log table existing — the caller
    gets an error payload it can show next to the row.
    """
    config_id = (config_id or "").strip()
    if not config_id:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "A config id is required."},
        )

    try:
        log_cols = _log_columns()
    except Exception as exc:
        status, msg = _failure(exc, table=LOG_TABLE_NAME)
        return JSONResponse(status_code=status, content={"status": "error", "message": msg})

    log_fields = {c["Field"] for c in log_cols}
    if CONFIG_ID_COLUMN not in log_fields:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": f"Table '{LOG_TABLE_NAME}' has no '{CONFIG_ID_COLUMN}' column.",
            },
        )

    order_parts = [f"`{c}` DESC" for c in (CHANGED_AT_COLUMN, LOG_PK_COLUMN) if c in log_fields]
    order = f" ORDER BY {', '.join(order_parts)}" if order_parts else ""

    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(f"SELECT * FROM {LOG_TABLE_SQL} WHERE `{CONFIG_ID_COLUMN}` = :config_id{order}"),
                {"config_id": config_id},
            )
            data = [{k: _jsonable(v) for k, v in r._mapping.items()} for r in rows]
    except Exception as exc:
        status, msg = _failure(exc, table=LOG_TABLE_NAME)
        return JSONResponse(status_code=status, content={"status": "error", "message": msg})

    return {
        "config_id": config_id,
        "columns": _column_meta(log_cols),
        "rows": data,
        "total": len(data),
    }


def _load_log_columns():
    """Return (log columns, error response); exactly one of them is set.

    Writes need the log table, so a missing one is reported with its own name
    instead of failing later inside the transaction.
    """
    try:
        log_cols = _log_columns()
    except Exception as exc:
        status, msg = _failure(exc, table=LOG_TABLE_NAME)
        return None, JSONResponse(status_code=status, content={"status": "error", "message": msg})
    if CONFIG_ID_COLUMN not in {c["Field"] for c in log_cols}:
        return None, JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": f"Table '{LOG_TABLE_NAME}' has no '{CONFIG_ID_COLUMN}' column.",
            },
        )
    return log_cols, None


def _clean_update(payload, cols):
    """Keep only real, updatable columns; empty strings become NULL."""
    fields = {c["Field"] for c in cols}
    pk = _primary_key(cols)
    data = {}
    for key, value in (payload or {}).items():
        if key not in fields or key == pk or key in NOT_UPDATABLE:
            continue
        data[key] = None if value in (None, "") else value
    return data


@router.put("/{config_id}")
async def update_config(config_id: str, payload: dict):
    """Update one config, logging the row as it was before the change.

    The previous row is copied to the log table and the update is applied in a
    single transaction, so a failed update leaves no log row behind. A payload
    that changes nothing writes no log row. ``updated_at`` is stamped with
    NOW(); ``created_at``, ``deactivated_at`` and ``plan_id`` are not settable
    here (deactivation has its own endpoint, which logs the same way).
    """
    try:
        cols = _columns()
    except Exception as exc:
        status, msg = _failure(exc)
        return JSONResponse(status_code=status, content={"status": "error", "message": msg})
    log_cols, log_error = _load_log_columns()
    if log_error is not None:
        return log_error

    # listing_id and duration belong to the plan, not to one allocator
    shared = [name for name in PLAN_SHARED_COLUMNS if name in (payload or {})]
    if shared:
        return JSONResponse(
            status_code=409,
            content={
                "status": "error",
                "message": (
                    f"{', '.join(shared)} is shared by every allocator of the plan. "
                    "Use PUT /api/incentive-base-configs/plan/{plan_id} to change it."
                ),
                "columns": shared,
            },
        )

    data = _clean_update(payload, cols)
    if not data:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "No valid fields to update."},
        )

    try:
        with engine.connect() as conn:
            previous, pk = _fetch_config(conn, cols, config_id)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"status": "error", "message": str(exc)})
    except Exception as exc:
        status, msg = _failure(exc)
        return JSONResponse(status_code=status, content={"status": "error", "message": msg})

    if previous is None:
        return JSONResponse(
            status_code=404,
            content={"status": "error", "message": "Base config not found."},
        )

    changes = {
        name: {"from": _jsonable(previous.get(name)), "to": _jsonable(value)}
        for name, value in data.items()
        if not _equal(previous.get(name), value)
    }
    if not changes:
        return {
            "status": "ok",
            "message": "No changes to record.",
            "logged": False,
            "changes": {},
            "row": {k: _jsonable(v) for k, v in previous.items()},
        }

    set_parts = [f"`{name}` = :{name}" for name in data]
    params = dict(data)
    fields = {c["Field"] for c in cols}
    if UPDATED_COLUMN in fields:
        set_parts.append(f"`{UPDATED_COLUMN}` = NOW()")
    params["pk_value"] = config_id

    try:
        with engine.begin() as conn:
            log_id = _insert_log(conn, log_cols, previous, previous[pk])
            conn.execute(
                text(f"UPDATE {TABLE_SQL} SET {', '.join(set_parts)} WHERE `{pk}` = :pk_value"),
                params,
            )
            updated = conn.execute(
                text(f"SELECT * FROM {TABLE_SQL} WHERE `{pk}` = :pk_value"),
                {"pk_value": config_id},
            ).first()
    except Exception as exc:
        status, msg = _failure(exc)
        return JSONResponse(status_code=status, content={"status": "error", "message": msg})

    stored = dict(updated._mapping) if updated is not None else previous
    # Report what is actually stored, not the raw payload ("0.75" -> 0.75).
    for name in changes:
        changes[name]["to"] = _jsonable(stored.get(name))

    return {
        "status": "ok",
        "message": "Base config updated successfully.",
        "logged": True,
        "log_id": _jsonable(log_id),
        "changes": changes,
        "row": {k: _jsonable(v) for k, v in stored.items()},
    }


@router.post("/{config_id}/deactivate")
async def deactivate_config(config_id: str):
    """Deactivate a config (`deactivated_at = NOW()`), logging the row first."""
    try:
        cols = _columns()
    except Exception as exc:
        status, msg = _failure(exc)
        return JSONResponse(status_code=status, content={"status": "error", "message": msg})
    log_cols, log_error = _load_log_columns()
    if log_error is not None:
        return log_error

    fields = {c["Field"] for c in cols}
    if DEACTIVATED_COLUMN not in fields:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": f"Table '{TABLE_NAME}' has no '{DEACTIVATED_COLUMN}' column.",
            },
        )

    try:
        with engine.connect() as conn:
            previous, pk = _fetch_config(conn, cols, config_id)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"status": "error", "message": str(exc)})
    except Exception as exc:
        status, msg = _failure(exc)
        return JSONResponse(status_code=status, content={"status": "error", "message": msg})

    if previous is None:
        return JSONResponse(
            status_code=404,
            content={"status": "error", "message": "Base config not found."},
        )
    if previous[DEACTIVATED_COLUMN] is not None:
        return {
            "status": "ok",
            "message": "Base config is already deactivated.",
            "logged": False,
            "active": False,
        }

    set_parts = [f"`{DEACTIVATED_COLUMN}` = NOW()"]
    if UPDATED_COLUMN in fields:
        set_parts.append(f"`{UPDATED_COLUMN}` = NOW()")

    try:
        with engine.begin() as conn:
            log_id = _insert_log(conn, log_cols, previous, previous[pk])
            conn.execute(
                text(f"UPDATE {TABLE_SQL} SET {', '.join(set_parts)} WHERE `{pk}` = :pk_value"),
                {"pk_value": config_id},
            )
    except Exception as exc:
        status, msg = _failure(exc)
        return JSONResponse(status_code=status, content={"status": "error", "message": msg})

    return {
        "status": "ok",
        "message": "Base config deactivated successfully.",
        "logged": True,
        "log_id": _jsonable(log_id),
        "active": False,
    }
