"""Metrics and SLA configurations for business calculations."""

import logging

logger = logging.getLogger(__name__)

# SQL formulas for specific metric definitions
METRIX_SQL = {
    "ha30": "COUNT(DISTINCT CASE WHEN T1_C < 30 THEN customer_ref_id END) / COUNT(DISTINCT customer_ref_id)",
    "trp60": "COUNT(DISTINCT CASE WHEN TRP <= 60 THEN customer_ref_id END) / COUNT(DISTINCT customer_ref_id)",
    "default": "COUNT(DISTINCT customer_ref_id) / COUNT(DISTINCT customer_ref_id)",
}

# Mapping of business IDs to their designated metric key
BUSINESS_SLA_METRICS = {
    2: "ha30",
    11653225: "trp60",
}

# Metric threshold levels mapped by customer ID
SLA_THRESHOLDS_METRIC = {
    2: [0.996, 0.994, 0.990, 0.985],
    11653225: [0.98, 0.96, 0.95, 0.93],
}

ALPHA = 0.3


def get_customer_score(customer_id: int | str, metric_value: float) -> int:
    """Evaluate metric_value starting from index 0 upwards.

    Scores range from 1 to 5:
      - Score 1: > thresholds[0]
      - Score 2: > thresholds[1]
      - Score 3: > thresholds[2]
      - Score 4: > thresholds[3]
      - Score 5: Fallback (if metric_value <= thresholds[-1])
    """
    try:
        cid = int(customer_id)
        thresholds = SLA_THRESHOLDS_METRIC.get(cid)
    except (ValueError, TypeError):
        thresholds = None

    if not thresholds:
        logger.warning(
            "No SLA thresholds configured for customer_id: %s. Returning default score 1.",
            customer_id,
        )
        return 1

    # Iterate from index 0 upwards
    for idx, threshold in enumerate(thresholds):
        if metric_value > threshold:
            return idx + 1

    # Fallback score if metric_value <= lowest threshold
    return len(thresholds) + 1