"""Final Decisions — scores by city/business entity for an incentive date.

Data sources:
- ``incentive.incentive_scores`` (id, created_at, incentive_date, city_id,
  business_entity_id, score_type, score)
- ``incentive.incentive_active_city`` (city_id, city, box_city_name, city_group, …)
  for the city name.

The UI shows two connected but separate parts: **Scores** (this endpoint) and
**Decisions** (future: 4–5 plans per city, displayed in the expanded integrated
view). The endpoint is deliberately designed so the decisions integration only
needs an extra field — the scoring shape stays stable.

Collapsed rows show the business entity with the best priority:
  foodZooket > food > Zooket > others (same level, alphabetical tie-break).

Expanded rows show all entities for that city. All cities can be expanded at once.
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

# Canonical score types the UI renders as 3 columns
SCORE_TYPES = ["performance", "order_level_increase", "weather"]
SCORE_TYPE_LABELS = {
    "performance": "Performance",
    "weather": "Weather",
    "order_level_increase": "Order Level Increase",
}
# Display labels use the canonical mapping, but storage may use label spelling.
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
        # 1054 = unknown column — schema mismatch
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
    # exact alias match for presets; custom types stay as-is (lowercased)
    return SCORE_TYPE_ALIASES.get(key, key)


def _entity_priority(name):
    """Lower number = higher priority (shown when collapsed)."""
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
        # default tomorrow (server local date)
        tomorrow = datetime.date.today() + datetime.timedelta(days=1)
        return tomorrow.isoformat()
    s = str(value).strip()
    # accept YYYY-MM-DD only
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        raise ValueError("incentive_date must be YYYY-MM-DD")
    try:
        datetime.date.fromisoformat(s)
    except ValueError:
        raise ValueError("incentive_date must be YYYY-MM-DD")
    return s


def _city_display(row):
    """Pick the best city name from an active-city row."""
    # active_city may have 'city', 'city_name', or just box_city_name
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
    # fallback to city_id
    cid = row.get("city_id") or row.get("correct_city_id") or "—"
    return f"City #{cid}"


@router.get("")
def list_final_decisions(
    incentive_date: str = Query(default=None, description="YYYY-MM-DD, defaults to tomorrow"),
):
    """Return all cities with their per-entity scores for one incentive date.

    The response groups by city, then by business entity, then by score_type.
    Each city's ``business_entities`` are sorted by priority so the first entry
    is what the collapsed row shows.
    """
    try:
        target_date = _parse_date(incentive_date)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"status": "error", "message": str(exc)})

    try:
        with engine.connect() as conn:
            # --- active cities: city_id -> {city, box_city_name, city_group} ---
            # Use SELECT * to be tolerant of schema drift (column names differ
            # between deployments). The mapping below handles any name.
            try:
                city_rows = list(conn.execute(text(f"SELECT * FROM {ACTIVE_CITY_SQL}")).mappings())
            except Exception as exc:
                # Report active-city table failures with its own name
                status, msg = _failure(exc, table=DB_ACTIVE_CITY_TABLE)
                return JSONResponse(status_code=status, content={"status": "error", "message": msg})

            city_map = {}
            for r in city_rows:
                d = {k: _jsonable(v) for k, v in r.items()}
                # city_id may be under different keys; try in order
                cid = d.get("city_id")
                if cid is None:
                    cid = d.get("correct_city_id") or d.get("id")
                if cid is None:
                    continue
                cid_str = str(cid)
                # keep first occurrence, but prefer row with a real city name
                if cid_str not in city_map or (_city_display(d) != f"City #{cid_str}" and _city_display(city_map[cid_str]) == f"City #{cid_str}"):
                    city_map[cid_str] = d

            # --- scores for the date ---
            # Support both DATE and DATETIME columns: compare via DATE()
            # If incentive_date is stored as string, DATE() will still work on MySQL for YYYY-MM-DD.
            # Fallback to plain equality if DATE() fails (caught by _failure).
            try:
                score_rows = list(
                    conn.execute(
                        text(
                            f"SELECT * FROM {SCORES_TABLE_SQL} "
                            f"WHERE DATE(`incentive_date`) = :d"
                        ),
                        {"d": target_date},
                    ).mappings()
                )
            except Exception as exc:
                # Try plain equality as fallback for strict DATE columns
                orig = getattr(exc, "orig", None)
                args = getattr(orig, "args", ()) if orig is not None else ()
                code = args[0] if args and isinstance(args[0], int) else None
                if code == 1582:  # incorrect parameter count or DATE() not applicable?
                    score_rows = list(
                        conn.execute(
                            text(f"SELECT * FROM {SCORES_TABLE_SQL} WHERE `incentive_date` = :d"),
                            {"d": target_date},
                        ).mappings()
                    )
                else:
                    # If unknown column etc, report as failure
                    # Check if it's a missing column/table error
                    raise

            # Normalize score rows for response
            # Group: city_id -> business_entity -> {score_type: score}
            grouped = {}
            for r in score_rows:
                d = dict(r.items() if hasattr(r, "items") else r._mapping.items())  # compatibility
                # _jsonable conversion later; keep raw for logic
                raw_cid = d.get("city_id")
                if raw_cid is None:
                    continue
                cid_str = str(raw_cid)
                # business_entity may be under business_entity_id or business_entity
                be_raw = d.get("business_entity_id")
                if be_raw is None:
                    be_raw = d.get("business_entity")
                if be_raw is None:
                    be_raw = d.get("business_entity_name") or d.get("entity")
                if be_raw is None:
                    be_raw = "unknown"
                be_str = str(be_raw).strip() if str(be_raw).strip() else "unknown"
                # score_type
                st_raw = d.get("score_type")
                st_norm = _normalize_score_type(st_raw)
                if st_norm is None:
                    continue
                # only keep canonical 3 types; ignore others but still keep? Keep only known 3 for now, but allow others to not break.
                # We'll keep all, but the UI columns are the 3 canonical.
                score_val = d.get("score")
                # convert to jsonable numeric if decimal
                score_json = _jsonable(score_val)
                # if it's a decimal string numeric, keep float?
                # Try to parse numeric strings
                if isinstance(score_json, str):
                    try:
                        # keep as float if numeric
                        score_json = float(score_json)
                    except (ValueError, TypeError):
                        pass

                if cid_str not in grouped:
                    grouped[cid_str] = {}
                if be_str not in grouped[cid_str]:
                    # init with all 3 types as None
                    grouped[cid_str][be_str] = {t: None for t in SCORE_TYPES}
                # if score_type is one of the 3, fill it; else stash under its own key (future-proof)
                if st_norm in SCORE_TYPES:
                    grouped[cid_str][be_str][st_norm] = score_json
                else:
                    # store under original normalized name as well, so custom types not lost
                    grouped[cid_str][be_str][st_norm] = score_json

            # --- resolve numeric business_entity_ids to names when possible ---
            # Sample data uses string names (foodZooket) directly, but some
            # deployments store an integer foreign key. If any entity looks
            # numeric, try to map it via incentive.business_entities.
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
                    # Detect which column holds the entity name: prefer 'name',
                    # fall back to 'business_entity' or first text column.
                    for r in be_rows:
                        d = {k: _jsonable(v) for k, v in r.items()}
                        # primary key candidate for id
                        pk_val = None
                        for cand in ("id", "business_entity_id", "entity_id"):
                            if cand in d and d[cand] not in (None, ""):
                                pk_val = str(d[cand]).strip()
                                break
                        if pk_val is None:
                            continue
                        if pk_val not in numeric_ids:
                            continue
                        name_val = None
                        for cand in ("name", "business_entity", "business_entity_name", "entity", "title"):
                            if cand in d and d[cand] not in (None, "", " "):
                                name_val = str(d[cand]).strip()
                                break
                        if name_val:
                            be_name_by_id[pk_val] = name_val
                except Exception:
                    # Business entities lookup is best-effort; scores still usable
                    logger.debug("Could not resolve business entity names", exc_info=True)

            # Build city list
            cities = []
            # Include cities that have scores; also include active cities with no scores? No — only those with scores for the date,
            # because otherwise table would be huge. But spec says rows are cities that have scores for that incentive_date.
            # However if no scores, we still return empty list with message.
            for cid_str, be_map in grouped.items():
                city_info = city_map.get(cid_str, {})
                city_name = _city_display(city_info) if city_info else f"City #{cid_str}"
                box_name = city_info.get("box_city_name") if city_info else None
                group = city_info.get("city_group") if city_info else None
                # fallback: if box_city_name missing, try other keys
                if box_name in (None, "", " "):
                    box_name = city_info.get("box_city") or city_info.get("city") or None
                    if box_name == city_name:
                        box_name = None

                entities = []
                for be_raw_str, scores in be_map.items():
                    # If this entity was a numeric FK, use the resolved name for display/priority
                    resolved = be_name_by_id.get(str(be_raw_str).strip(), be_raw_str)
                    # ensure all 3 types present
                    full_scores = {t: scores.get(t) for t in SCORE_TYPES}
                    # keep any extra types as well
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
                # sort by priority then name case-insensitive
                entities.sort(key=lambda e: (e["priority"], str(e["business_entity"]).lower()))

                primary = entities[0] if entities else None

                cities.append(
                    {
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

            # Also include active cities that have zero scores? Not by default.
            # Sort cities: by city_group then city name (similar to decision matrix grouping could be useful)
            # Use locale-like sort: city_group alphabetical then city name
            def _city_sort_key(c):
                g = (c.get("city_group") or "").strip().lower()
                # Put empty groups last
                g_rank = 0 if g else 1
                return (g_rank, g, str(c.get("city") or "").lower(), str(c.get("city_id_raw") or ""))

            cities.sort(key=_city_sort_key)

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
