from datetime import date, timedelta
import requests

from app.core.config import WEATHER_API_URL
from app.core.utils.logger import get_logger

logger = get_logger(__name__)


def get_city_weather_score(city: str) -> int:
    """Get the weather score for a given city.

    Args:
        city: The name of the city.

    Returns:
        The weather severity score (integer), defaults to 1 on error.
    """
    incentive_date = (date.today() + timedelta(days=1)).isoformat()
    url = f"{WEATHER_API_URL}/{city}"
    params = {"date": incentive_date}

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()

        weather_response = response.json()
        raw_score = weather_response.get("response")

        # Safely handle null/None values before rounding
        score = round(raw_score) if raw_score is not None else 1

        logger.info(
            "Fetched weather score for %s (%s) | api_response=%s | raw_score=%s | final_score=%s",
            city,
            incentive_date,
            weather_response,
            raw_score,
            score,
        )
        return score

    except Exception as exc:
        logger.error(
            "Failed weather score for %s (%s) due to %s: fallback to score 1",
            city,
            incentive_date,
            exc,
        )
        return 1