import asyncio
from fastapi import status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from repositories.health.contracts.ihealth_service import IHealthService
from repositories.health.helpers.health_check import check_database, check_rabbitmq, check_redis


class HealthService(IHealthService):

    async def health_checker(self) -> JSONResponse:
        # check_rabbitmq uses blocking pika — run it in a thread so it doesn't
        # block the event loop while the other two checks run concurrently
        loop = asyncio.get_event_loop()

        results = await asyncio.gather(
            check_database(),
            loop.run_in_executor(None, check_rabbitmq),
            check_redis(),
        )

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
