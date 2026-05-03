from fastapi import APIRouter, Response, status
from domains.health.proxies.health_service_proxy import HealthServiceProxy
from domains.health.models.health_models import HealthResponse

router = APIRouter(tags=["Health"])


@router.get("/", response_model=HealthResponse)
async def health_check(response: Response):
    result = await HealthServiceProxy().health_checker()
    if not result.is_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return result
