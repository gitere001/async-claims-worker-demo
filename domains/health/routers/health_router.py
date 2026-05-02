from fastapi import APIRouter
from proxies.health.health_service_proxy import HealthServiceProxy

router = APIRouter(tags=["Health"])


@router.get("/")
async def health_check():
    return await HealthServiceProxy().health_checker()
