from services.health.contracts.ihealth_service import IHealthService
from services.health.health_service import HealthService


class HealthServiceProxy(IHealthService):

    def __init__(self) -> None:
        self.service: IHealthService = HealthService()

    async def health_checker(self):
        return await self.service.health_checker()
