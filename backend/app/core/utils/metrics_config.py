"""Metrics and SLA configurations for business calculations."""

# SQL formulas for specific metric definitions
METRIX_SQL = {
    "ha30": "COUNT(DISTINCT CASE WHEN T1_C <= 30 THEN customer_ref_id END) / COUNT(DISTINCT customer_ref_id)",
    "trp60": "COUNT(DISTINCT CASE WHEN TRP <= 60 THEN customer_ref_id END) / COUNT(DISTINCT customer_ref_id)",
    "default": "COUNT(DISTINCT customer_ref_id) / COUNT(DISTINCT customer_ref_id)",
}

# Mapping of business IDs to their designated metric key
BUSINESS_SLA_METRICS = {
    2: "ha30",
    11653225: "trp60",
}

# Metric threshold levels mapped by business ID
SLA_THRESHOLDS_METRIC = {
    2: [0.996, 0.994, 0.990, 0.985],
    11653225: [0.98, 0.96, 0.95, 0.93],
}