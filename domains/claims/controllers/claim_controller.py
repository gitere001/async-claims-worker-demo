from uuid import UUID
from lagom import Container
from domains.claims.app_services.interfaces.iclaim_app_service import IClaimAppService
from domains.claims.models.claim_models import (
    SubmitClaimRequest,
    SubmitClaimResponse,
    ClaimStatusResponse,
)


class ClaimController:

    def __init__(self, container: Container) -> None:
        self.app_service = container.resolve(IClaimAppService)

    async def submit_claim(self, request: SubmitClaimRequest) -> SubmitClaimResponse:
        return await self.app_service.submit_claim(request)

    async def get_claim_status(self, claim_id: UUID) -> ClaimStatusResponse:
        return await self.app_service.get_claim_status(claim_id)
