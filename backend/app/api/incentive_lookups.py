"""Search-and-select lookups for the base-config forms.

The available allocators, rules and listings live in services inside the
network, so the browser never calls them directly: these endpoints proxy them
over the same origin, normalize whatever shape they answer with into a plain
list of names, and filter on ``q``.

    allocators -> {ALLOCATOR_NAMES_URL}          e.g. /allocator/names
    rules      -> {RULE_NAMES_URL}               e.g. /rules/names
    listings   -> {LISTING_QUERIES_URL}/{city}   e.g. /queries/tehran
"""

import requests
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from app.core.config import (
    ALLOCATOR_NAMES_URL,
    LISTING_QUERIES_URL,
    RULE_NAMES_URL,
)
from app.core.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/incentive-lookups", tags=["incentive-lookups"])

REQUEST_TIMEOUT = 10
MAX_LIMIT = 500

# Keys an upstream payload may hide its list under, in the order they are tried.
LIST_KEYS = (
    "names", "data", "results", "result", "items", "rows", "response",
    "queries", "allocators", "rules", "listings",
)
# Keys a single entry may hold its display name under.
NAME_KEYS = (
    "name", "id", "value", "label", "title", "query",
    "allocator", "rule", "listing",
)


def _extract(value):
    """Pull a display name out of one upstream entry, whatever its shape."""
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        for key in NAME_KEYS:
            if value.get(key) not in (None, ""):
                return _extract(value[key])
        for item in value.values():  # no known key: take the first usable value
            name = _extract(item)
            if name:
                return name
        return None
    if isinstance(value, (list, tuple)):
        for item in value:
            name = _extract(item)
            if name:
                return name
        return None
    return str(value)


def _names(payload):
    """Normalize an upstream payload into an ordered list of distinct names."""
    if isinstance(payload, dict):
        for key in LIST_KEYS:
            if key in payload:
                payload = payload[key]
                break
        else:
            # {"tehran": [...]} style: a single list value is the payload.
            lists = [v for v in payload.values() if isinstance(v, (list, tuple))]
            if len(lists) == 1:
                payload = lists[0]
    if not isinstance(payload, (list, tuple)):
        payload = [payload]

    seen, names = set(), []
    for item in payload:
        name = _extract(item)
        if name and name.lower() not in seen:
            seen.add(name.lower())
            names.append(name)
    return names


def _lookup(url, term, limit, kind):
    """Fetch one upstream list, normalize it and filter on the search term."""
    try:
        limit = max(1, min(int(limit), MAX_LIMIT))
    except (TypeError, ValueError):
        limit = 200

    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        logger.error("Lookup '%s' failed for %s: %s", kind, url, exc)
        return JSONResponse(
            status_code=502,
            content={
                "status": "error",
                "kind": kind,
                "message": f"Could not reach the {kind} service ({url}): {exc}",
            },
        )

    names = _names(payload)
    term = (term or "").strip()
    if term:
        lowered = term.lower()
        matches = [n for n in names if lowered in n.lower()]
    else:
        matches = names

    return {
        "kind": kind,
        "source": url,
        "term": term,
        "rows": [{"name": name} for name in matches[:limit]],
        "matched": len(matches),
        "total": len(names),
        "truncated": len(matches) > limit,
    }


@router.get("/allocators")
def allocator_names(
    q: str = Query(default="", description="Case-insensitive substring filter"),
    limit: int = Query(default=200),
):
    """Available allocator ids, for the add/replace allocator forms."""
    return _lookup(ALLOCATOR_NAMES_URL, q, limit, "allocators")


@router.get("/rules")
def rule_names(
    q: str = Query(default="", description="Case-insensitive substring filter"),
    limit: int = Query(default=200),
):
    """Available rule names, for the add/replace allocator forms."""
    return _lookup(RULE_NAMES_URL, q, limit, "rules")


@router.get("/listings")
def listing_names(
    city: str = Query(default="", description="City the listings belong to"),
    q: str = Query(default="", description="Case-insensitive substring filter"),
    limit: int = Query(default=200),
):
    """Available listings (queries) of one city, for the plan-level listing."""
    city = (city or "").strip()
    if not city:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "Query parameter 'city' is required."},
        )
    return _lookup(f"{LISTING_QUERIES_URL.rstrip('/')}/{city}", q, limit, "listings")
