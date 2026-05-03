from uuid import UUID
from lagom import Container
from domains.claims.services.interfaces.iclaim_service import IClaimService
from domains.claims.models.claim_models import (
    SubmitClaimRequest,
    SubmitClaimResponse,
    ClaimStatusResponse,
)


class ClaimController:

    def __init__(self, container: Container) -> None:
        self.app_service = container.resolve(IClaimService)

    async def submit_claim(self, request: SubmitClaimRequest) -> SubmitClaimResponse:
        return await self.app_service.submit_claim(request)

    async def get_claim_status(self, claim_id: UUID) -> ClaimStatusResponse:
        return await self.app_service.get_claim_status(claim_id)
