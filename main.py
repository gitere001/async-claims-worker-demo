import logging
import uvicorn
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from config.app_config import main_api_config
from config.app_routers import load_middleware
from core.database.db_context import engine
from core.exceptions.app_exceptions import AppException
from core.exceptions.exception_handlers import (
    app_exception_handler,
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from domains.claims.app import router as claims_router
from domains.health.app import router as health_router
from worker import app as celery_app  # noqa: F401 — initialises Celery on startup

logger = logging.getLogger(__name__)

app = FastAPI(**main_api_config.model_dump())

app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

app.include_router(claims_router)
app.include_router(health_router)

load_middleware(app)


@app.on_event("startup")
async def warmup_db() -> None:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    logger.info("Database pool warmed up — Neon connection ready")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
