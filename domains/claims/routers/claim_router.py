from uuid import UUID
from fastapi import APIRouter, Depends
from domains.claims.container import container
from domains.claims.controllers.claim_controller import ClaimController
from domains.claims.models.claim_models import SubmitClaimRequest, SubmitClaimResponse, ClaimStatusResponse
from core.responses.api_response import ApiResponse

router = APIRouter(tags=["Claims"])


def get_controller() -> ClaimController:
    return ClaimController(container)


@router.post("/submit", response_model=ApiResponse[SubmitClaimResponse])
async def submit_claim(
    request: SubmitClaimRequest,
    controller: ClaimController = Depends(get_controller),
):
    result = await controller.submit_claim(request)
    return ApiResponse.ok(result, "Claim received and queued for processing")


@router.get("/status/{claim_id}", response_model=ApiResponse[ClaimStatusResponse])
async def get_claim_status(
    claim_id: UUID,
    controller: ClaimController = Depends(get_controller),
):
    result = await controller.get_claim_status(claim_id)
    return ApiResponse.ok(result, "Claim status retrieved")
