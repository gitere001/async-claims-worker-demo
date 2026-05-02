from fastapi import FastAPI
from domains.claims.routers.claim_router import router as claim_router
from domains.claims.routers.health_router import router as health_router

app = FastAPI(
    title="Async Claims Worker Demo",
    description="Mini claims processor — FastAPI + Celery + RabbitMQ",
    version="1.0.0",
)

app.include_router(claim_router, prefix="/app/v1")
app.include_router(health_router, prefix="/app/v1")
