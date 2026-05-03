from typing import Optional
from uuid import UUID
from repositories.claims.contracts.iclaim_repository import IClaimRepository
from repositories.claims.claim_repository import ClaimRepository


class ClaimServiceProxy(IClaimRepository):

    def __init__(self):
        self.service = ClaimRepository()

    async def save_claim(self, data: dict) -> dict:
        return await self.service.save_claim(data)

    async def get_claim(self, claim_id: UUID) -> Optional[dict]:
        return await self.service.get_claim(claim_id)

    async def update_claim_status(self, claim_id: UUID, status: str) -> None:
        return await self.service.update_claim_status(claim_id, status)
