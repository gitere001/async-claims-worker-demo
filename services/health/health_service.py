from fastapi import status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from services.health.contracts.ihealth_service import IHealthService
from services.health.helpers.health_check import check_database, check_rabbitmq, check_redis


class HealthService(IHealthService):

    async def health_checker(self) -> JSONResponse:
        results = [
            await check_database(),
            check_rabbitmq(),
            await check_redis(),
        ]

        is_healthy = all(ok for ok, _ in results)
        checks = {key: value for _, msg in results for key, value in msg.items()}

        status_code = status.HTTP_200_OK if is_healthy else status.HTTP_503_SERVICE_UNAVAILABLE

        return JSONResponse(
            status_code=status_code,
            content=jsonable_encoder({
                "is_healthy": is_healthy,
                "checks": checks,
            }),
        )
