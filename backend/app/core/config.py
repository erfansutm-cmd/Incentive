import os

# Database settings - MySQL
DB_USER = os.getenv("DB_USER", "erfan.mohamadi")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_HOST = os.getenv("DB_HOST", "172.21.41.75")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_NAME = os.getenv("DB_NAME", "")

# ClickHouse settings (used by the performance score calculation).
# NOTE: clickhouse-driver speaks the native protocol (default port 9000),
# not the HTTP port 8123.
CLICKHOUSE_HOST = os.getenv("CLICKHOUSE_HOST", "clickhouse.de.data.snapp.tech")
CLICKHOUSE_PORT = os.getenv("CLICKHOUSE_PORT", "8123")
CLICKHOUSE_DB = os.getenv("CLICKHOUSE_DB", "default")
CLICKHOUSE_USER = os.getenv("CLICKHOUSE_USER", "erfan_mohamadi")
CLICKHOUSE_PASSWORD = os.getenv("CLICKHOUSE_PASSWORD", "")

# Table names
DB_CITIES_TABLE = os.getenv("DB_CITIES_TABLE", "incentive/incentive_active_city")
DB_CITY_MAPPING_TABLE = os.getenv("DB_CITY_MAPPING_TABLE", "mafsho/city_mapping")
DB_CITY_PLAN_MAPPING_TABLE = os.getenv("DB_CITY_PLAN_MAPPING_TABLE", "incentive/incentive_city_plan_mapping")
DB_ACTIVE_CITY_TABLE = os.getenv("DB_ACTIVE_CITY_TABLE", "incentive/incentive_active_city")
DB_BUSINESS_ENTITIES_TABLE = os.getenv(
    "DB_BUSINESS_ENTITIES_TABLE", "incentive/business_entities"
)
DB_INCENTIVE_TYPE_TABLE = os.getenv("DB_INCENTIVE_TYPE_TABLE", "mafsho/incentive_type")
DB_DECISION_MATRIX_TABLE = os.getenv(
    "DB_DECISION_MATRIX_TABLE", "incentive/incentive_decision_matrix"
)
DB_INCENTIVE_BASE_CONFIG_TABLE = os.getenv(
    "DB_INCENTIVE_BASE_CONFIG_TABLE", "incentive/incentive_base_configs"
)
DB_INCENTIVE_BASE_CONFIG_LOG_TABLE = os.getenv(
    "DB_INCENTIVE_BASE_CONFIG_LOG_TABLE", "incentive/incentive_base_configs_logs"
)

DB_INCENTIVE_SCORES_TABLE = os.getenv(
    "DB_INCENTIVE_SCORES_TABLE", "incentive/incentive_scores"
)

# Final decisions — the plans of every city for an incentive date, joined to
# incentive_city_plan_mapping on plan_mapping_id to reach the city, the
# incentive type and the business entity.
DB_INCENTIVE_PLANS_TABLE = os.getenv(
    "DB_INCENTIVE_PLANS_TABLE", "incentive/final_incentive_plans"
)
# Display order ("top first") of the plan types in the Final Decisions tab.
# Comma separated type names; whatever is not listed follows alphabetically.
# The UI loads this order and lets the user reorder it in a popup.
FINAL_DECISION_PLAN_TYPE_ORDER = os.getenv(
    "FINAL_DECISION_PLAN_TYPE_ORDER", "DAILY,ON-TOP-FOOD"
)
# Order ("top first") the cities of the Final Decisions tab are listed in, by
# their city group. Comma separated group names, matched ignoring capitalization
# and separators; tiers that are not listed follow the listed ones, and every
# other group comes last, alphabetically.
FINAL_DECISION_GROUP_ORDER = os.getenv(
    "FINAL_DECISION_GROUP_ORDER", "Tehran Group,Top 4,Tier 1,Tier 2,Tier 3"
)

# Allocator / rule / listing lookups behind the base-config forms.
# The browser never calls these directly; /api/incentive-lookups proxies them.
ALLOCATOR_NAMES_URL = os.getenv("ALLOCATOR_NAMES_URL", "http://172.21.88.174:5000/allocator/names")
RULE_NAMES_URL = os.getenv("RULE_NAMES_URL", "http://172.21.88.174:5000/rules/names")
# All available listings ("queries"), for every city at once
LISTING_QUERIES_URL = os.getenv("LISTING_QUERIES_URL", "http://172.21.88.148:5000/queries/all")

# Weather API
WEATHER_API_URL = os.getenv("weather_ENDPOINT", "http://172.21.88.66:5000/severity-forecast")

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Microsoft Teams incoming-webhook URL used to post notifications
TEAMS_WEBHOOK_URL = os.getenv("TEAMS_WEBHOOK_URL", "")