import json
import time

from app.core.utils.clickhouse import execute_query as execute_clickhouse_query
from app.core.utils.database import execute_query as execute_mysql_query
from app.core.utils.logger import get_logger
from app.core.utils.metrics_config import (
    ALPHA,
    BUSINESS_SLA_METRICS,
    METRIX_SQL,
    get_customer_score,
)
from app.core.utils.query_loader import get_query

logger = get_logger(__name__)


def _extract_customer_ids(raw_value) -> list[int]:
    """Safely extract list of integer customer IDs from list, JSON string, or scalar."""
    if raw_value is None:
        return []

    if isinstance(raw_value, list):
        return [int(cid) for cid in raw_value if cid is not None]

    if isinstance(raw_value, str):
        raw_value = raw_value.strip()
        if raw_value.startswith("[") and raw_value.endswith("]"):
            try:
                parsed = json.loads(raw_value)
                if isinstance(parsed, list):
                    return [int(cid) for cid in parsed if cid is not None]
            except Exception:
                pass
        try:
            return [int(raw_value)]
        except ValueError:
            return []

    if isinstance(raw_value, int):
        return [raw_value]

    return []


def get_city_performance_score(city: str, business_entity: str) -> int:
    """Fetch performance data and calculate weighted SLA score using EWMA without DataFrames."""
    # ---------------------------
    # 1. Fetch Main Customer Mapping
    # ---------------------------
    main_query = get_query("main_customers_query.sql")
    mysql_results = execute_mysql_query(sql=main_query)

    if not mysql_results:
        logger.error(
            "No customer mappings returned from MySQL for business_entity=%r, city=%r: fallback to score 1",
            business_entity,
            city,
        )
        return 1

    customer_ids = []
    for row in mysql_results:
        if row.get("business_entity") == business_entity:
            cids = row.get("main_customer")
            customer_ids.extend(_extract_customer_ids(cids))
            break

    if not customer_ids:
        logger.error(
            "Business entity %r not found or main_customer list is empty for city=%r: fallback to score 1",
            business_entity,
            city,
        )
        return 1

    customer_ids = list(set(customer_ids))
    customer_ids_str = ", ".join(str(cid) for cid in customer_ids)

    # ---------------------------
    # 2. Build SQL Case Expressions
    # ---------------------------
    case_branches = []
    for cid in customer_ids:
        metric_key = BUSINESS_SLA_METRICS.get(cid, "default")
        formula = METRIX_SQL.get(metric_key)

        if formula is None:
            logger.warning(
                "Metric formula for key %r (customer_id=%d) is missing in METRIX_SQL. Falling back to default formula.",
                metric_key,
                cid,
            )
            formula = METRIX_SQL["default"]

        case_branches.append(f"WHEN customer_id = {cid} THEN {formula}")

    default_formula = METRIX_SQL["default"]
    inslot_case = f"CASE {' '.join(case_branches)} ELSE {default_formula} END"

    # Query ClickHouse
    perf_query = get_query(
        "performance_query.sql",
        inslot_case=inslot_case,
        customer_ids_str=customer_ids_str,
        city=city,
    )

    started = time.monotonic()
    ch_results = execute_clickhouse_query(sql=perf_query)
    elapsed_ms = int((time.monotonic() - started) * 1000)

    if not ch_results:
        logger.warning(
            "ClickHouse returned empty results for business_entity=%r in city=%r (%d ms): fallback to score 1",
            business_entity,
            city,
            elapsed_ms,
        )
        return 1

    # ---------------------------
    # 3. Group and Sort
    # ---------------------------
    # Group rows by (customer_id, city)
    grouped_data = {}
    for row in ch_results:
        key = (row["customer_id"], row["city"])
        if key not in grouped_data:
            grouped_data[key] = []
        grouped_data[key].append(row)

    # Sort each group chronologically by created_date
    for key in grouped_data:
        grouped_data[key].sort(key=lambda r: str(r["created_date"]))

    # ---------------------------
    # 4. Time weighting (EWMA) & Customer Summary
    # ---------------------------
    alpha = float(ALPHA) if ALPHA is not None else 0.3

    customer_metrics_summary = {}

    for (cid, c_city), rows in grouped_data.items():
        smoothed_metric_val = None
        customer_total_orders = 0

        # Exponential Weighted Moving Average (EWMA) chronologically
        for row in rows:
            metric_val = float(row.get("InSlot") or 0.0)
            orders_val = int(row.get("orders_cnt") or 0)

            if smoothed_metric_val is None:
                # Initialize with first day's metric value
                smoothed_metric_val = metric_val
            else:
                # Apply EWMA formula: alpha * current + (1 - alpha) * previous
                smoothed_metric_val = alpha * metric_val + (1 - alpha) * smoothed_metric_val

            customer_total_orders += orders_val

        customer_weighted_avg = smoothed_metric_val if smoothed_metric_val is not None else 0.0

        # Store customer summary in dictionary
        customer_metrics_summary[cid] = {
            "total_orders": customer_total_orders,
            "smoothed_metric_val": customer_weighted_avg,
        }

    # ---------------------------
    # 5. Customer Scoring & Weighted Average Score Calculation
    # ---------------------------
    weighted_score_sum = 0.0
    total_entity_orders = 0

    for cid, summary in customer_metrics_summary.items():
        orders = summary["total_orders"]
        metric_val = summary["smoothed_metric_val"]

        # Get individual score for each customer ID (Scores 1 to 5)
        customer_score = get_customer_score(cid, metric_val)

        weighted_score_sum += customer_score * orders
        total_entity_orders += orders

    if total_entity_orders == 0:
        logger.warning(
            "Total entity orders is 0 for business_entity=%r in city=%r: fallback to score 1",
            business_entity,
            city,
        )
        return 1

    # Calculate overall weighted average score and round to nearest integer
    final_score = round(weighted_score_sum / total_entity_orders)

    logger.info(
        "Calculated score %d for business_entity=%r in city=%r (total_orders=%d, alpha=%.2f)",
        final_score,
        business_entity,
        city,
        total_entity_orders,
        alpha,
    )

    return final_score