from datetime import date, timedelta

import requests

from ..config import WEATHER_API_URL
from ..logger import get_logger

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
        response = requests.get(
            url,
            params=params,
            timeout=10
        )
        response.raise_for_status()

        weather_response = response.json()
        raw_score = weather_response.get("response", 1)
        score = round(raw_score)

        logger.info(
            "Weather score retrieved from API: city=%r, raw_score=%s, rounded_score=%s",
            city,
            raw_score,
            score,
        )

        return score

    except Exception as exc:
        # Collect as much context as possible before logging the failure.
        failed_response = getattr(exc, "response", None)
        details = {
            "city": city,
            "url": url,
            "params": params,
            "incentive_date": incentive_date,
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
            "status_code": getattr(failed_response, "status_code", None),
            "response_text": getattr(failed_response, "text", None),
        }
        logger.exception(
            "Weather score lookup failed for city=%r; falling back to score 1. Details: %s",
            city,
            details,
        )
        return 1  # Fallback score on error
