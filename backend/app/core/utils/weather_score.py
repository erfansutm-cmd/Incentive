from datetime import date, timedelta
import requests

from ..config import WEATHER_API_URL


def get_city_weather_score(city: str) -> int:
    """Get the weather score for a given city.
    
    Args:
        city: The name of the city.
        
    Returns:
        The weather severity score (integer), defaults to 1 on error.
    """
    incentive_date = (date.today() + timedelta(days=1)).isoformat()

    try:
        response = requests.get(
            f"{WEATHER_API_URL}/{city}",
            params={
                "date": incentive_date,
            },
            timeout=10
        )
        response.raise_for_status()

        weather_response = response.json()
        return round(weather_response.get("response", 1))

    except Exception:
        return 1  # Fallback score on error
