"""Final Decisions — scores by city/business entity for an incentive date.

Data sources:
- ``incentive.incentive_scores`` (id, created_at, incentive_date, city_id,
  business_entity_id, score_type, score)
- ``incentive.incentive_active_city`` (id, city_id, city, box_city_name, city_group, …)
  for the city name.

Collapsed rows show the business entity with the best priority:
  foodZooket > food > Zooket > others (same level, alphabetical tie-break).

Sorting is by the active city table's primary key ``id`` (not city_id), per spec.
Expanded rows show all entities for that city.
"""

import datetime
import decimal
import re

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import (
    DB_ACTIVE_CITY_TABLE,
    DB_BUSINESS_ENTITIES_TABLE,
    DB_INCENTIVE_SCORES_TABLE,
)
from app.core.utils.database import engine, quote_table
from app.core.utils.logger import get_logger

SCORES_TABLE_SQL = quote_table(DB_INCENTIVE_SCORES_TABLE)
ACTIVE_CITY_SQL = quote_table(DB_ACTIVE_CITY_TABLE)
BUSINESS_ENTITIES_SQL = quote_table(DB_BUSINESS_ENTITIES_TABLE)

SCORE_TYPES = ["performance", "order_level_increase", "weather"]
SCORE_TYPE_LABELS = {
    "performance": "Performance",
    "weather": "Weather",
    "order_level_increase": "Order Level Increase",
}
SCORE_TYPE_ALIASES = {
    alias.lower(): value
    for value, label in SCORE_TYPE_LABELS.items()
    for alias in (value, label)
}

router = APIRouter(prefix="/api/final-decisions", tags=["final-decisions"])
logger = get_logger(__name__)


def _jsonable(value):
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
    table = table or DB_INCENTIVE_SCORES_TABLE
    orig = getattr(exc, "orig", None)
    args = getattr(orig, "args", ()) if orig is not None else ()
    if isinstance(args, tuple) and len(args) >= 2 and isinstance(args[0], int):
        code, msg = args[0], args[1]
        if code == 1146:
            return 404, f"Table '{table}' does not exist in the database."
        if code == 2003:
            return 503, f"Cannot connect to the database: {msg}"
        if code in (1045, 1044):
            return 503, f"Database access denied: {msg}"
        if code == 1049:
            return 503, f"Unknown database: {msg}"
        if code in (1054, 1146):
            return 400, f"Table schema mismatch: {msg}"
        return 400, msg
    return 500, str(exc)


def _normalize_score_type(raw):
    if raw is None:
        return None
    key = str(raw).strip().lower()
    if not key:
        return None
    return SCORE_TYPE_ALIASES.get(key, key)


def _entity_priority(name):
    if name is None:
        return 99
    s = str(name).strip().lower()
    if s == "foodzooket":
        return 0
    if s == "food":
        return 1
    if s == "zooket":
        return 2
    return 3


def _parse_date(value):
    if value is None or (isinstance(value, str) and not value.strip()):
        tomorrow = datetime.date.today() + datetime.timedelta(days=1)
        return tomorrow.isoformat()
    s = str(value).strip()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        raise ValueError("incentive_date must be YYYY-MM-DD")
    try:
        datetime.date.fromisoformat(s)
    except ValueError:
        raise ValueError("incentive_date must be YYYY-MM-DD")
    return s


def _city_display(row):
    for key in ("city", "city_name", "correct_city", "name"):
        if key in row and row[key] not in (None, "", " "):
            v = str(row[key]).strip()
            if v:
                return v
    for key in ("box_city_name", "box_city", "box_name"):
        if key in row and row[key] not in (None, "", " "):
            v = str(row[key]).strip()
            if v:
                return v
    cid = row.get("city_id") or row.get("correct_city_id") or "—"
    return f"City #{cid}"


@router.get("")
def list_final_decisions(
    incentive_date: str = Query(default=None, description="YYYY-MM-DD, defaults to tomorrow"),
):
    try:
        target_date = _parse_date(incentive_date)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"status": "error", "message": str(exc)})

    try:
        with engine.connect() as conn:
            try:
                city_rows = list(conn.execute(text(f"SELECT * FROM {ACTIVE_CITY_SQL}")).mappings())
            except Exception as exc:
                status, msg = _failure(exc, table=DB_ACTIVE_CITY_TABLE)
                return JSONResponse(status_code=status, content={"status": "error", "message": msg})

            city_map = {}
            for r in city_rows:
                d = {k: _jsonable(v) for k, v in r.items()}
                # city_id for grouping — try city_id first, fallback to correct_city_id
                cid = d.get("city_id")
                if cid is None:
                    cid = d.get("correct_city_id")
                # Only if no city_id column at all, fall back to PK id (should not happen for active_city)
                if cid is None:
                    # don't use PK as city_id otherwise; skip
                    continue
                cid_str = str(cid)
                # active PK id for sorting — the `id` column of incentive_active_city
                active_pk = None
                # r is a RowMapping, try direct key access
                try:
                    if "id" in r.keys():
                        active_pk = r["id"]
                except Exception:
                    active_pk = d.get("id")
                if active_pk is None:
                    active_pk = d.get("id")
                # Keep numeric active_pk for sorting; store as int if possible
                active_id_val = None
                if active_pk is not None:
                    try:
                        active_id_val = int(str(active_pk).strip())
                    except (ValueError, TypeError):
                        active_id_val = None
                d["_active_id"] = active_id_val
                # store internal raw active id for later
                if cid_str not in city_map or (_city_display(d) != f"City #{cid_str}" and _city_display(city_map[cid_str]) == f"City #{cid_str}"):
                    city_map[cid_str] = d
                else:
                    # if we already have an entry but this row has a smaller active id, prefer smallest? Keep existing to avoid flip-flop
                    # But if this row has a smaller active id and same display quality, keep smallest for deterministic sort? Not needed.
                    pass

            try:
                score_rows = list(
                    conn.execute(
                        text(f"SELECT * FROM {SCORES_TABLE_SQL} WHERE DATE(`incentive_date`) = :d"),
                        {"d": target_date},
                    ).mappings()
                )
            except Exception as exc:
                orig = getattr(exc, "orig", None)
                args = getattr(orig, "args", ()) if orig is not None else ()
                code = args[0] if args and isinstance(args[0], int) else None
                if code == 1582:
                    score_rows = list(
                        conn.execute(
                            text(f"SELECT * FROM {SCORES_TABLE_SQL} WHERE `incentive_date` = :d"),
                            {"d": target_date},
                        ).mappings()
                    )
                else:
                    raise

            grouped = {}
            for r in score_rows:
                d = dict(r.items() if hasattr(r, "items") else r._mapping.items())
                raw_cid = d.get("city_id")
                if raw_cid is None:
                    continue
                cid_str = str(raw_cid)
                be_raw = d.get("business_entity_id")
                if be_raw is None:
                    be_raw = d.get("business_entity")
                if be_raw is None:
                    be_raw = d.get("business_entity_name") or d.get("entity")
                if be_raw is None:
                    be_raw = "unknown"
                be_str = str(be_raw).strip() if str(be_raw).strip() else "unknown"
                st_raw = d.get("score_type")
                st_norm = _normalize_score_type(st_raw)
                if st_norm is None:
                    continue
                score_val = d.get("score")
                score_json = _jsonable(score_val)
                if isinstance(score_json, str):
                    try:
                        score_json = float(score_json)
                    except (ValueError, TypeError):
                        pass
                if cid_str not in grouped:
                    grouped[cid_str] = {}
                if be_str not in grouped[cid_str]:
                    grouped[cid_str][be_str] = {t: None for t in SCORE_TYPES}
                if st_norm in SCORE_TYPES:
                    grouped[cid_str][be_str][st_norm] = score_json
                else:
                    grouped[cid_str][be_str][st_norm] = score_json

            # numeric FK resolution (best-effort)
            numeric_ids = set()
            for be_map in grouped.values():
                for be_str in be_map.keys():
                    s = str(be_str).strip()
                    if s.lstrip("-").isdigit():
                        numeric_ids.add(s)
            be_name_by_id = {}
            if numeric_ids:
                try:
                    be_rows = list(conn.execute(text(f"SELECT * FROM {BUSINESS_ENTITIES_SQL}")).mappings())
                    for r in be_rows:
                        d = {k: _jsonable(v) for k, v in r.items()}
                        pk_val = None
                        for cand in ("id", "business_entity_id", "entity_id"):
                            if cand in d and d[cand] not in (None, ""):
                                pk_val = str(d[cand]).strip()
                                break
                        if pk_val is None or pk_val not in numeric_ids:
                            continue
                        name_val = None
                        for cand in ("name", "business_entity", "business_entity_name", "entity", "title"):
                            if cand in d and d[cand] not in (None, "", " "):
                                name_val = str(d[cand]).strip()
                                break
                        if name_val:
                            be_name_by_id[pk_val] = name_val
                except Exception:
                    logger.debug("Could not resolve business entity names", exc_info=True)

            cities = []
            for cid_str, be_map in grouped.items():
                city_info = city_map.get(cid_str, {})
                city_name = _city_display(city_info) if city_info else f"City #{cid_str}"
                box_name = city_info.get("box_city_name") if city_info else None
                group = city_info.get("city_group") if city_info else None
                if box_name in (None, "", " "):
                    box_name = city_info.get("box_city") or city_info.get("city") or None
                    if box_name == city_name:
                        box_name = None
                active_id_val = city_info.get("_active_id") if city_info else None
                # fallback if no active info: use large number so unsorted cities go last but still sort by city_id
                if active_id_val is None:
                    try:
                        # try to use city_id numeric for fallback ordering
                        active_id_val = int(cid_str) if str(cid_str).lstrip("-").isdigit() else 999999
                    except Exception:
                        active_id_val = 999999

                entities = []
                for be_raw_str, scores in be_map.items():
                    resolved = be_name_by_id.get(str(be_raw_str).strip(), be_raw_str)
                    full_scores = {t: scores.get(t) for t in SCORE_TYPES}
                    for k, v in scores.items():
                        if k not in full_scores:
                            full_scores[k] = v
                    entities.append(
                        {
                            "business_entity": resolved,
                            "business_entity_id": be_raw_str,
                            "business_entity_name": resolved,
                            "scores": full_scores,
                            "priority": _entity_priority(resolved),
                        }
                    )
                entities.sort(key=lambda e: (e["priority"], str(e["business_entity"]).lower()))
                primary = entities[0] if entities else None
                # keep active_id for sorting; also expose as id for frontend reference
                cities.append(
                    {
                        "id": active_id_val,
                        "active_id": active_id_val,
                        "city_id": _jsonable(cid_str if not str(cid_str).isdigit() else int(cid_str) if str(cid_str).lstrip("-").isdigit() else cid_str),
                        "city_id_raw": cid_str,
                        "city": city_name,
                        "box_city_name": _jsonable(box_name),
                        "city_group": _jsonable(group),
                        "business_entities": entities,
                        "primary_entity": primary,
                        "entity_count": len(entities),
                    }
                )

            # Sort by active table PK `id` ascending per spec
            def _sort_key(c):
                # primary sort by active_id numeric ascending; tie-breaker by city name for stability
                try:
                    aid = int(c.get("active_id") or c.get("id") or 999999)
                except Exception:
                    aid = 999999
                return (aid, str(c.get("city") or "").lower())

            cities.sort(key=_sort_key)

            total_entities = sum(c["entity_count"] for c in cities)
            return {
                "incentive_date": target_date,
                "score_types": SCORE_TYPES,
                "score_type_labels": SCORE_TYPE_LABELS,
                "cities": cities,
                "total_cities": len(cities),
                "total_business_entities": total_entities,
                "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
            }

    except Exception as exc:
        status, msg = _failure(exc)
        logger.exception("Final Decisions load failed for %s", target_date)
        return JSONResponse(status_code=status, content={"status": "error", "message": msg})
