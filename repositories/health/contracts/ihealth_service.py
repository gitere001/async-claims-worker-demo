from abc import ABC, abstractmethod
from domains.health.models.health_models import HealthResponse


class IHealthService(ABC):

    @abstractmethod
    async def health_checker(self) -> HealthResponse: ...
