from uuid import UUID
from domains.claims.services.interfaces.iclaim_service import IClaimService
from domains.claims.models.claim_models import (
    SubmitClaimRequest,
    SubmitClaimResponse,
    ClaimStatusResponse,
)
from repositories.claims.contracts.iclaim_repository import IClaimRepository


class ClaimService(IClaimService):

    def __init__(self, claim_service: IClaimRepository):
        self.claim_service = claim_service

    async def submit_claim(self, request: SubmitClaimRequest) -> SubmitClaimResponse:
        saved = await self.claim_service.save_claim(request.model_dump())

        from workers.claims.validate_claim_task import validate_claim_task
        validate_claim_task.delay(saved)

        return SubmitClaimResponse(
            claim_id=saved["id"],
            status="PENDING",
            message="Claim received and queued for processing",
        )

    async def get_claim_status(self, claim_id: UUID) -> ClaimStatusResponse:
        claim = await self.claim_service.get_claim(claim_id)
        return ClaimStatusResponse(
            claim_id=claim_id,
            status=claim.get("status", "UNKNOWN"),
            approved_amount=claim.get("approved_amount"),
            adjudication_result=claim.get("adjudication_result"),
        )
