from fastapi import APIRouter
from domains.health.routers.health_router import router as health_router

router = APIRouter(prefix="/app/v1/health")
router.include_router(health_router)
