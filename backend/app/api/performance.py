# from fastapi import APIRouter, HTTPException
#
# from app.core.performance_score import get_city_performance_score
#
# router = APIRouter(prefix="/api/performance", tags=["performance"])
#
#
# @router.get("/score/{city}/{business_entity}")
# def city_performance_score(city: str, business_entity: str):
#     """
#     Get the performance (SLA) score for a given city and business entity.
#
#     Args:
#         city: The name of the city to get the performance score for.
#         business_entity: The name of the business entity, e.g. the name in business_entities.
#
#     Returns:
#         A dictionary containing the city name, business entity and its performance score.
#     """
#     city = (city or "").strip()
#     business_entity = (business_entity or "").strip()
#     if not city or not business_entity:
#         raise HTTPException(
#             status_code=400, detail="Both 'city' and 'business_entity' are required."
#         )
#     score = get_city_performance_score(city, business_entity)
#     return {
#         "city": city,
#         "business_entity": business_entity,
#         "score": score
#     }
