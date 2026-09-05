import os

# Database settings
DB_USER = os.getenv("DB_USER", "erfan.mohamadi")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_HOST = os.getenv("DB_HOST", "172.21.41.75")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_NAME = os.getenv("DB_NAME", "")

# Table names
DB_CITIES_TABLE = os.getenv("DB_CITIES_TABLE", "cities")
DB_CITY_MAPPING_TABLE = os.getenv("DB_CITY_MAPPING_TABLE", "mafsho/city_mapping")

# Weather API
WEATHER_API_URL = os.getenv("weather_ENDPOINT", "http://172.21.88.66:5000/severity-forecast")
