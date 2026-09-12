import os

# Database settings - MySQL
DB_USER = os.getenv("DB_USER", "erfan.mohamadi")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_HOST = os.getenv("DB_HOST", "172.21.41.75")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_NAME = os.getenv("DB_NAME", "incentive")

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
DB_ACTIVE_CITY_TABLE = os.getenv("DB_ACTIVE_CITY_TABLE", "incentive/incentive_active_city")
DB_BUSINESS_ENTITIES_TABLE = os.getenv(
    "DB_BUSINESS_ENTITIES_TABLE", "incentive/business_entities"
)
DB_INCENTIVE_TYPE_TABLE = os.getenv("DB_INCENTIVE_TYPE_TABLE", "mafsho/incentive_type")
DB_DECISION_MATRIX_TABLE = os.getenv(
    "DB_DECISION_MATRIX_TABLE", "incentive/incentive_decision_matrix"
)

# Weather API
WEATHER_API_URL = os.getenv("weather_ENDPOINT", "http://172.21.88.66:5000/severity-forecast")

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Microsoft Teams incoming-webhook URL used to post notifications
TEAMS_WEBHOOK_URL = os.getenv("TEAMS_WEBHOOK_URL", "")