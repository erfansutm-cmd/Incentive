
from .utils.clickhouse import (execute_query as execute_clickhouse_query)
from .utils.database import execute_query as execute_mysql_query
from .utils.metrics_config import (
    BUSINESS_SLA_METRICS,
    METRIX_SQL,
    SLA_THRESHOLDS_METRIC,
)
from .utils.query_loader import get_query
from .utils.logger import get_logger

logger = get_logger(__name__)


def get_city_performance_score(city: str, business_entity: str) -> int:
    """Fetch performance data and calculate SLA score for a city and business entity.

    Args:
        city: Name of the target city.
        business_entity: Name or ID of the business entity.

    Returns:
        The calculated performance score (integer), defaults to 1 on error/missing data.
    """
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
        entity = row["business_entity"]
        customer_id = row["main_customer"]
        business_map.setdefault(entity, []).append(customer_id)

    if business_entity not in business_map:
        logger.error(
            "Business entity %r not found in map for city=%r: fallback to score 1",
            business_entity,
            city,
        )
        return 1

    customer_ids = business_map[business_entity]
    customer_ids_str = ", ".join(str(cid) for cid in customer_ids)

    # 2. Build dynamic inslot CASE expression for all customer IDs
    case_branches = []
    for cid in customer_ids:
        metric_key = BUSINESS_SLA_METRICS.get(cid, "default")
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
        city=city,
    )

    ch_results = execute_clickhouse_query(sql=perf_query)

    if not ch_results:
        logger.warning(
            "No performance data returned from ClickHouse for business_entity=%r in city=%r: fallback to score 1",
            business_entity,
            city,
        )
        return 1

    # Simple print
    print("ClickHouse Results:", ch_results)