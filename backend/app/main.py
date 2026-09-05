from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text

from .api import cities, business_entities, city_plan_mappings, incentive_types, weather
from .core.database import engine, DB_HOST, DB_NAME, DB_PORT, DB_USER

app = FastAPI(title="Incentive API")

# Include API routers
app.include_router(cities.router)
app.include_router(business_entities.router)
app.include_router(city_plan_mappings.router)
app.include_router(incentive_types.router)
app.include_router(weather.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/health/db")
def db_health():
    """Checks that the backend can reach and query the MySQL database."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # keep it simple: report the failure in the response
        return JSONResponse(
            status_code=503,
            content={"status": "error", "detail": str(exc)},
        )

    return {
        "status": "ok",
        "database": DB_NAME or None,
        "host": DB_HOST,
        "port": DB_PORT,
        "user": DB_USER,
    }
