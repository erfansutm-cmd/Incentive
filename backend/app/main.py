from fastapi import FastAPI

app = FastAPI(title="Incentive API")


@app.get("/api/health")
def health():
    return {"status": "ok"}
