import uvicorn
from fastapi import FastAPI

from config.app_config import main_api_config
from config.app_routers import load_middleware
from domains.claims.app import claims_app
from domains.health.app import health_app
from worker import app as celery_app  # noqa: F401 — initialises Celery on startup

app = FastAPI(**main_api_config.model_dump())

app.mount("/app/v1/claims", claims_app)
app.mount("/app/v1/health", health_app)

load_middleware(app)

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
