from fastapi import APIRouter

from .utils.weather_score import get_city_weather_score

router = APIRouter(prefix="/api/weather", tags=["weather"])


@router.get("/score/{city}")
def city_weather_score(city: str):
    """
    Get the weather score for a given city.
    
    Args:
        city: The name of the city to get the weather score for.
        
    Returns:
        A dictionary containing the city name and its weather score.
    """
    score = get_city_weather_score(city)
    return {
        "city": city,
        "score": score
    }
