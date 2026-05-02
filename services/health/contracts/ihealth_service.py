from abc import ABC, abstractmethod


class IHealthService(ABC):

    @abstractmethod
    async def health_checker(self) -> dict: ...
