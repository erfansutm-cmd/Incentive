"""City group -> incentive type -> score type -> sequential score steps.

Parents are derived from matrix rows. Creating a type also creates its first
step; no placeholder rows or additional tables are needed for an empty matrix.
"""

import datetime
import decimal
import hashlib
import re
from contextlib import contextmanager

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from sqlalchemy import text

from ..core.config import DB_ACTIVE_CITY_TABLE, DB_DECISION_MATRIX_TABLE, DB_NAME
from ..core.database import engine, quote_table
from ..core.logger import get_logger
from .incentive_types import TABLE_SQL as INCENTIVE_TYPE_SQL

TABLE_SQL = quote_table(DB_DECISION_MATRIX_TABLE)
ACTIVE_CITY_SQL = quote_table(DB_ACTIVE_CITY_TABLE)
COLUMNS = (
    "id", "incentive_type", "city_group", "score_type", "score",
    "target_increase", "pr_increase", "control_bucket", "created_at", "deactivated_at",
)
VALUE_COLUMNS = ("target_increase", "pr_increase", "control_bucket")
# MySQL named locks are connection-scoped (not transaction-scoped). Serialize
# inserts even when the matrix is empty, without changing the user's schema or
# requiring write/locking permissions on mafsho.incentive_type. A table-wide
# lock also respects case-insensitive DB collations for city/score type names.
WRITE_LOCK = "decision-matrix:" + hashlib.sha256(
    f"{DB_NAME}/{TABLE_SQL}".encode()
).hexdigest()[:48]

router = APIRouter(prefix="/api/decision-matrix", tags=["decision-matrix"])
logger = get_logger(__name__)


class MatrixError(Exception):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = status_code


def _jsonable(value):
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _row_json(row):
    return {k: _jsonable(v) for k, v in row.items()}


def _error(exc):
    if isinstance(exc, MatrixError):
        status, message = exc.status_code, str(exc)
    else:
        logger.exception("Decision Matrix database operation failed")
        args = getattr(getattr(exc, "orig", None), "args", ())
        code = args[0] if args else None
        status, message = 500, "Could not access the Decision Matrix. Please try again."
        if code == 1146:
            status, message = 404, "A required table does not exist. Check the Decision Matrix table settings."
        elif code in (2002, 2003, 2006, 2013):
            status, message = 503, "Cannot connect to the database. Check the backend database settings."
        elif code in (1044, 1045):
            status, message = 503, "Database access denied. Check the backend database settings."
        elif code == 1049:
            status, message = 503, "The configured database does not exist."
        elif code in (1062, 1205, 1213):
            status, message = 409, "The matrix was changed by another request. Refresh and try again."
        elif code in (1054, 1264, 1265, 1364, 1366, 1406):
            status, message = 400, f"The values do not match the table schema: {args[1]}"
    return JSONResponse(status_code=status, content={"status": "error", "message": message})


def _columns(conn):
    cols = [dict(r) for r in conn.execute(text(f"SHOW COLUMNS FROM {TABLE_SQL}")).mappings()]
    missing = set(COLUMNS) - {c["Field"] for c in cols}
    if missing:
        raise MatrixError(
            f"Table '{DB_DECISION_MATRIX_TABLE}' has no column(s): {', '.join(sorted(missing))}."
        )
    return cols


def _column_json(col):
    return {
        "name": col["Field"],
        "type": col["Type"],
        "nullable": col.get("Null") == "YES",
        "key": col.get("Key") or "",
        "default": _jsonable(col.get("Default")),
        "extra": col.get("Extra") or "",
    }


def _required_text(value, name):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise MatrixError(f"'{name}' is required and must be a single value.")
    value = str(value).strip()
    if not value:
        raise MatrixError(f"'{name}' is required.")
    return value


def _positive_integer(value, name):
    try:
        number = decimal.Decimal(_required_text(value, name))
    except decimal.InvalidOperation:
        raise MatrixError(f"'{name}' must be a positive whole number.") from None
    if not number.is_finite() or number < 1 or number != number.to_integral_value():
        raise MatrixError(f"'{name}' must be a positive whole number.")
    # These fields are stored as MySQL integer identifiers/scores.
    if number > 18446744073709551615:
        raise MatrixError(f"'{name}' is too large.")
    return int(number)


def _clean_value(value, col):
    """Respect the existing table's nullability and numeric/text field types.

    No percentage conversion or assumed control-bucket range: store the values
    entered by the user. Bind numeric values as strings to preserve decimals.
    """
    name = col["Field"]
    if value is None or (isinstance(value, str) and not value.strip()):
        if col.get("Default") is not None:
            value = col["Default"]
        elif col.get("Null") == "YES":
            return None
        else:
            raise MatrixError(f"'{name}' is required.")
    if isinstance(value, bool) or not isinstance(value, (str, int, float, decimal.Decimal)):
        raise MatrixError(f"'{name}' must be a single value.")
    value = str(value).strip()
    column_type = col["Type"].lower()
    if re.match(r"^(tinyint|smallint|mediumint|int|integer|bigint|decimal|numeric|float|double|real)\b", column_type):
        try:
            number = decimal.Decimal(value)
        except decimal.InvalidOperation:
            raise MatrixError(f"'{name}' must be a number.") from None
        if not number.is_finite():
            raise MatrixError(f"'{name}' must be a finite number.")
        if re.match(r"^(tinyint|smallint|mediumint|int|integer|bigint)\b", column_type):
            if number != number.to_integral_value():
                raise MatrixError(f"'{name}' must be a whole number.")
        if "unsigned" in column_type and number < 0:
            raise MatrixError(f"'{name}' cannot be negative.")
        return str(number)
    length = re.match(r"^(?:var)?char\((\d+)\)", column_type)
    if length and len(value) > int(length[1]):
        raise MatrixError(f"'{name}' must be at most {length[1]} characters.")
    return value


@contextmanager
def _write_transaction():
    with engine.connect() as conn:
        acquired = False
        try:
            acquired = conn.execute(
                text("SELECT GET_LOCK(:name, 5)"), {"name": WRITE_LOCK}
            ).scalar() == 1
            if not acquired:
                raise MatrixError("Another step is being saved. Please try again.", 409)
            yield conn
            # Commit BEFORE releasing the lock, so the next writer sees the new score.
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            if acquired:
                try:
                    conn.execute(text("SELECT RELEASE_LOCK(:name)"), {"name": WRITE_LOCK})
                    conn.commit()
                except Exception:
                    # Never put a connection holding a named lock back in the pool.
                    conn.invalidate()
                    logger.exception("Could not release the Decision Matrix write lock")


@router.get("/city-groups")
def list_city_groups():
    """Read independently of the matrix so groups appear before its first row."""
    try:
        with engine.connect() as conn:
            rows = conn.execute(text(
                f"SELECT DISTINCT `city_group` FROM {ACTIVE_CITY_SQL} "
                "WHERE `city_group` IS NOT NULL AND TRIM(`city_group`) <> '' "
                "ORDER BY `city_group`"
            )).mappings()
            return {"rows": [_row_json(r) for r in rows]}
    except Exception as exc:
        return _error(exc)


@router.get("")
def list_steps(
    city_group: str = Query(..., min_length=1),
    include_deactivated: bool = False,
):
    """Return one group's rows and series metadata (counts/next score).

    Series metadata always includes history, even when deactivated rows are
    hidden. A series with no active steps remains discoverable.
    """
    try:
        city_group = _required_text(city_group, "city_group")
        with engine.connect() as conn:
            cols = _columns(conn)
            params = {"city_group": city_group}
            series = conn.execute(text(
                "SELECT `incentive_type`, `score_type`, MAX(`score`) + 1 AS next_score, "
                "SUM(CASE WHEN `deactivated_at` IS NULL THEN 1 ELSE 0 END) AS active_count, "
                "SUM(CASE WHEN `deactivated_at` IS NOT NULL THEN 1 ELSE 0 END) AS deactivated_count "
                f"FROM {TABLE_SQL} WHERE `city_group` = :city_group "
                "GROUP BY `incentive_type`, `score_type` ORDER BY `incentive_type`, `score_type`"
            ), params).mappings()
            series_data = [
                {
                    "incentive_type": _jsonable(s["incentive_type"]),
                    "score_type": _jsonable(s["score_type"]),
                    "next_score": int(s["next_score"]),
                    "active_count": int(s["active_count"]),
                    "deactivated_count": int(s["deactivated_count"]),
                }
                for s in series
            ]
            active_filter = "" if include_deactivated else " AND m.`deactivated_at` IS NULL"
            rows = conn.execute(text(
                f"SELECT m.*, t.`name` AS incentive_type_name FROM {TABLE_SQL} m "
                f"LEFT JOIN {INCENTIVE_TYPE_SQL} t ON t.`id` = m.`incentive_type` "
                f"WHERE m.`city_group` = :city_group{active_filter} "
                "ORDER BY m.`incentive_type`, m.`score_type`, m.`score`, m.`id`"
            ), params).mappings()
            data = [_row_json(r) for r in rows]
        return {
            "city_group": city_group,
            "include_deactivated": include_deactivated,
            "columns": [_column_json(c) for c in cols],
            "rows": data,
            "series": series_data,
        }
    except Exception as exc:
        return _error(exc)


@router.post("")
def add_step(payload: dict):
    """Append MAX(score) + 1 within a (city group, incentive type, score type).

    An optional score is an optimistic check of the UI's displayed next step,
    never a user-controlled sequence number. Historical scores are not reused.
    """
    try:
        allowed = {"city_group", "incentive_type", "score_type", "score", *VALUE_COLUMNS}
        unknown = set(payload) - allowed
        if unknown:
            raise MatrixError(f"Fields cannot be set: {', '.join(sorted(unknown))}.")
        city_group = _required_text(payload.get("city_group"), "city_group")
        type_id = _positive_integer(payload.get("incentive_type"), "incentive_type")
        score_type = _required_text(payload.get("score_type"), "score_type")
        expected_score = (
            _positive_integer(payload["score"], "score") if "score" in payload else None
        )

        with _write_transaction() as conn:
            cols = {c["Field"]: c for c in _columns(conn)}
            params = {
                "city_group": _clean_value(city_group, cols["city_group"]),
                "incentive_type": type_id,
                "score_type": _clean_value(score_type, cols["score_type"]),
                **{name: _clean_value(payload.get(name), cols[name]) for name in VALUE_COLUMNS},
            }
            group = conn.execute(text(
                f"SELECT `city_group` FROM {ACTIVE_CITY_SQL} "
                "WHERE `city_group` = :city_group LIMIT 1"
            ), {"city_group": params["city_group"]}).first()
            if group is None:
                raise MatrixError("Select a city group from the active cities table.")
            params["city_group"] = group[0]
            incentive_type = conn.execute(text(
                f"SELECT `id` FROM {INCENTIVE_TYPE_SQL} WHERE `id` = :id"
            ), {"id": type_id}).first()
            if incentive_type is None:
                raise MatrixError("Select an existing incentive type from mafsho.incentive_type.")
            params["incentive_type"] = incentive_type[0]

            previous = conn.execute(text(
                f"SELECT `score_type`, MAX(`score`) AS max_score FROM {TABLE_SQL} "
                "WHERE `city_group` = :city_group AND `incentive_type` = :incentive_type "
                "AND `score_type` = :score_type GROUP BY `score_type`"
            ), params).mappings().first()
            next_score = int(previous["max_score"]) + 1 if previous else 1
            if expected_score is not None and expected_score != next_score:
                raise MatrixError(
                    f"The next score for this score type is {next_score}. "
                    "Refresh the matrix and add the next step from its score type panel.",
                    409,
                )
            if previous:
                # Preserve the existing spelling under case-insensitive DB collations.
                params["score_type"] = previous["score_type"]
            params["score"] = next_score
            insert = conn.execute(text(
                f"INSERT INTO {TABLE_SQL} "
                "(`city_group`, `incentive_type`, `score_type`, `score`, "
                "`target_increase`, `pr_increase`, `control_bucket`, `created_at`, `deactivated_at`) "
                "VALUES (:city_group, :incentive_type, :score_type, :score, "
                ":target_increase, :pr_increase, :control_bucket, NOW(), NULL)"
            ), params)
            row = conn.execute(text(
                f"SELECT * FROM {TABLE_SQL} WHERE `id` = :id"
            ), {"id": insert.lastrowid}).mappings().one()
            result = _row_json(row)
        return {"status": "ok", "message": f"Score {next_score} added successfully.", "row": result}
    except Exception as exc:
        return _error(exc)


@router.post("/{step_id}/deactivate")
def deactivate_step(step_id: int):
    """Soft deactivate atomically; repeated requests keep the original timestamp."""
    try:
        with engine.begin() as conn:
            updated = conn.execute(text(
                f"UPDATE {TABLE_SQL} SET `deactivated_at` = NOW() "
                "WHERE `id` = :id AND `deactivated_at` IS NULL"
            ), {"id": step_id})
            if updated.rowcount == 0:
                row = conn.execute(text(
                    f"SELECT `id` FROM {TABLE_SQL} WHERE `id` = :id"
                ), {"id": step_id}).first()
                if row is None:
                    raise MatrixError("Score step not found.", 404)
                return {"status": "ok", "message": "Score step is already deactivated.", "active": False}
        return {"status": "ok", "message": "Score step deactivated successfully.", "active": False}
    except Exception as exc:
        return _error(exc)
