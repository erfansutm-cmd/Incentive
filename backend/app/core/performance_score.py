
import time

from app.core.utils.clickhouse import (execute_query as execute_clickhouse_query)
from app.core.utils.database import execute_query as execute_mysql_query
from app.core.utils.metrics_config import (
    BUSINESS_SLA_METRICS,
    METRIX_SQL,
    SLA_THRESHOLDS_METRIC,
)
from app.core.utils.query_loader import get_query
from app.core.utils.logger import get_logger

logger = get_logger(__name__)


def _score_from_inslot(inslot: float, thresholds) -> int:
    """Map an InSlot value to a 1-based score using descending thresholds.

    With N thresholds ``[t1, t2, ..., tN]`` (highest first), an InSlot >= t1
    scores 1, >= t2 scores 2, ..., and anything below tN scores N + 1.
    """
    for index, threshold in enumerate(thresholds):
        if inslot >= float(threshold):
            return index + 1
    return len(thresholds) + 1


def _to_int(value) -> int:
    """Coerce a customer id to int, accepting ints, floats and numeric strings."""
    if isinstance(value, bool):
        raise ValueError(f"Invalid customer id: {value!r}")
    if isinstance(value, (int, float)):
        return int(value)
    return int(str(value).strip())


def _escape_clickhouse_string(value: str) -> str:
    """Escape a value interpolated into a single-quoted ClickHouse string literal."""
    return str(value).replace("\\", "\\\\").replace("'", "\\'")


def get_city_performance_score(city: str, business_entity: str) -> int:
    """Fetch performance data and calculate SLA score for a city and business entity.

    The score is derived from the orders-weighted average InSlot per customer,
    mapped through that customer's SLA thresholds (1 = best). The final score
    is the worst (highest) per-customer score, so a struggling customer drives
    the incentive.

    Args:
        city: Name of the target city.
        business_entity: Name of the business entity.

    Returns:
        The calculated performance score (integer), defaults to 1 on error/missing data.
    """
    city = (city or "").strip()
    business_entity = (business_entity or "").strip()
    if not city or not business_entity:
        logger.error(
            "Empty city (%r) or business_entity (%r): fallback to score 1",
            city,
            business_entity,
        )
        return 1
    try:
        return _calculate_city_performance_score(city, business_entity)
    except Exception as exc:
        logger.exception(
            "Failed performance score for business_entity=%r in city=%r due to %s: fallback to score 1",
            business_entity,
            city,
            exc,
        )
        return 1


def _calculate_city_performance_score(city: str, business_entity: str) -> int:
    # 1. Fetch main customer mapping using MySQL
    main_query = get_query("main_customers_query.sql")
    mysql_results = execute_mysql_query(sql=main_query)

    if not mysql_results:
        logger.error(
            "No customer mappings returned from MySQL for business_entity=%r, city=%r: fallback to score 1",
            business_entity,
            city,
        )
        return 1

    # Build business_map: {"business_entity_name": [customer_id_1, customer_id_2]}
    business_map = {}
    for row in mysql_results:
        entity = row.get("business_entity")
        if entity is None or str(entity).strip() == "":
            continue
        try:
            customer_id = _to_int(row.get("main_customer"))
        except (TypeError, ValueError):
            logger.warning(
                "Skipping non-numeric customer id %r for business_entity=%r",
                row.get("main_customer"),
                entity,
            )
            continue
        business_map.setdefault(str(entity).strip(), []).append(customer_id)

    if business_entity not in business_map:
        logger.error(
            "Business entity %r not found in map for city=%r: fallback to score 1",
            business_entity,
            city,
        )
        return 1

    customer_ids = business_map[business_entity]
    if not customer_ids:
        logger.error(
            "No valid customer ids for business_entity=%r in city=%r: fallback to score 1",
            business_entity,
            city,
        )
        return 1
    customer_ids_str = ", ".join(str(cid) for cid in customer_ids)
    logger.info(
        "Performance lookup for business_entity=%r in city=%r | customer_ids=%s",
        business_entity,
        city,
        customer_ids,
    )

    # 2. Build dynamic inslot CASE expression for all customer IDs
    case_branches = []
    for cid in customer_ids:
        metric_key = BUSINESS_SLA_METRICS.get(cid, BUSINESS_SLA_METRICS.get(str(cid), "default"))
        formula = METRIX_SQL.get(metric_key)

        if formula is None:
            logger.warning(
                "Metric formula for key %r (customer_id=%s) is null or missing in METRIX_SQL. Falling back to default formula.",
                metric_key,
                cid,
            )
            formula = METRIX_SQL["default"]

        case_branches.append(f"WHEN customer_id = {cid} THEN {formula}")

    default_formula = METRIX_SQL["default"]
    inslot_case = f"CASE {' '.join(case_branches)} ELSE {default_formula} END"

    # Fetch performance data with calculated inslot metric from ClickHouse
    perf_query = get_query(
        "performance_query.sql",
        inslot_case=inslot_case,
        customer_ids_str=customer_ids_str,
        city=_escape_clickhouse_string(city),
    )
    logger.info(
        "Running ClickHouse performance query for business_entity=%r in city=%r:\n%s",
        business_entity,
        city,
        perf_query,
    )

    started = time.monotonic()
    ch_results = execute_clickhouse_query(sql=perf_query)
    elapsed_ms = int((time.monotonic() - started) * 1000)

    if ch_results is None:
        # None means the query never ran: ClickHouse not configured or the
        # query failed (see the clickhouse module logs for the cause).
        logger.error(
            "ClickHouse query failed for business_entity=%r in city=%r (%d ms): fallback to score 1",
            business_entity,
            city,
            elapsed_ms,
        )
        return 1

    if not ch_results:
        logger.warning(
            "ClickHouse returned 0 rows for business_entity=%r in city=%r (%d ms): fallback to score 1",
            business_entity,
            city,
            elapsed_ms,
        )
        return 1

    logger.info(
        "ClickHouse returned %d rows for business_entity=%r in city=%r (%d ms)",
        len(ch_results),
        business_entity,
        city,
        elapsed_ms,
    )
    logger.debug("ClickHouse results: %s", ch_results)

    # 3. Aggregate InSlot per customer and map through SLA thresholds.
    # Rows may carry real column names (customer_id/orders_cnt/InSlot) or the
    # legacy positional aliases col_0..col_4 in SELECT order.
    aggregates = {}  # cid -> [weighted_sum, orders_total, inslot_sum, row_count]
    for row in ch_results:
        lowered = {str(key).lower(): value for key, value in row.items()}
        raw_cid = lowered.get("customer_id", row.get("col_0"))
        raw_orders = lowered.get("orders_cnt", row.get("col_3"))
        raw_inslot = lowered.get("inslot", row.get("col_4"))
        try:
            cid = _to_int(raw_cid)
            inslot = float(raw_inslot)
        except (TypeError, ValueError):
            logger.warning(
                "Skipping ClickHouse row with invalid customer_id (%r) or InSlot (%r) "
                "for business_entity=%r in city=%r",
                raw_cid,
                raw_inslot,
                business_entity,
                city,
            )
            continue
        try:
            orders = float(raw_orders) if raw_orders is not None else 0.0
        except (TypeError, ValueError):
            orders = 0.0
        if orders < 0:
            orders = 0.0
        slot = aggregates.setdefault(cid, [0.0, 0.0, 0.0, 0])
        slot[0] += inslot * orders
        slot[1] += orders
        slot[2] += inslot
        slot[3] += 1

    if not aggregates:
        logger.warning(
            "No usable performance rows for business_entity=%r in city=%r: fallback to score 1",
            business_entity,
            city,
        )
        return 1

    per_customer = {}
    for cid, (weighted_sum, orders_total, inslot_sum, row_count) in aggregates.items():
        thresholds = SLA_THRESHOLDS_METRIC.get(cid, SLA_THRESHOLDS_METRIC.get(str(cid)))
        if not thresholds:
            logger.warning(
                "No SLA thresholds configured for customer_id=%s (business_entity=%r, city=%r): skipping customer",
                cid,
                business_entity,
                city,
            )
            continue
        avg_inslot = weighted_sum / orders_total if orders_total > 0 else inslot_sum / row_count
        per_customer[cid] = {
            "avg_inslot": round(avg_inslot, 4),
            "score": _score_from_inslot(avg_inslot, thresholds),
        }

    if not per_customer:
        logger.warning(
            "No customers with SLA thresholds for business_entity=%r in city=%r: fallback to score 1",
            business_entity,
            city,
        )
        return 1

    final_score = max(item["score"] for item in per_customer.values())
    logger.info(
        "Performance score for business_entity=%r in city=%r | per_customer=%s | final_score=%s",
        business_entity,
        city,
        per_customer,
        final_score,
    )
    return final_score
