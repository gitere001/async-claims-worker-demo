from abc import ABC, abstractmethod
from typing import Optional
from uuid import UUID


class IClaimRepository(ABC):

    @abstractmethod
    async def save_claim(self, data: dict) -> dict: ...

    @abstractmethod
    async def get_claim(self, claim_id: UUID) -> Optional[dict]: ...

    @abstractmethod
    async def update_claim_status(self, claim_id: UUID, status: str) -> None: ...
