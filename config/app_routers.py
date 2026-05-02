from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware

from domains.claims.routers.claim_router import router as claim_router
from domains.health.routers.health_router import router as health_router
from middleware.request_logging import log_middleware
from middleware.cors_middleware import cors_middleware


def load_claims_routers(app: FastAPI) -> None:
    app.include_router(claim_router)


def load_health_routers(app: FastAPI) -> None:
    app.include_router(health_router)


def load_middleware(app: FastAPI) -> None:
    app.add_middleware(BaseHTTPMiddleware, dispatch=cors_middleware)
    app.add_middleware(BaseHTTPMiddleware, dispatch=log_middleware)
