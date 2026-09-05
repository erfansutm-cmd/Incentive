from datetime import date, timedelta
import os
import requests


def get_city_weather_score(city: str) -> int:
    API_URL = os.getenv("weather_ENDPOINT", "http://172.21.88.66:5000/severity-forecast")
    incentive_date = (date.today() + timedelta(days=1)).isoformat()

    try:
        response = requests.get(
            f"{API_URL}/{city}",
            params={
                "date": incentive_date,
            },
            timeout=10
        )
        response.raise_for_status()

        weather_response = response.json()
        return round(weather_response.get("response", 1))

    except Exception as e:
        # print(f"Failed to fetch weather data for {city}: {e}")
        return 1  # Fallback score on error