import asyncio

from repositories.health.contracts.ihealth_service import IHealthService
from repositories.health.helpers.health_check import check_database, check_rabbitmq, check_redis
from domains.health.models.health_models import HealthResponse, HealthChecks


class HealthService(IHealthService):

    async def health_checker(self) -> HealthResponse:
        loop = asyncio.get_event_loop()

        results = await asyncio.gather(
            check_database(),
            loop.run_in_executor(None, check_rabbitmq),
            check_redis(),
        )

        is_healthy = all(ok for ok, _ in results)
        flat = {key: value for _, msg in results for key, value in msg.items()}

        return HealthResponse(
            is_healthy=is_healthy,
            checks=HealthChecks(
                database=flat["database"],
                rabbitmq=flat["rabbitmq"],
                redis=flat["redis"],
            ),
        )
