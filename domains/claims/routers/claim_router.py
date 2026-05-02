from uuid import UUID
from fastapi import APIRouter, Depends
from domains.claims.container import container
from domains.claims.controllers.claim_controller import ClaimController
from domains.claims.models.claim_models import (
    SubmitClaimRequest,
    SubmitClaimResponse,
    ClaimStatusResponse,
)

router = APIRouter(tags=["Claims"])


def get_controller() -> ClaimController:
    return ClaimController(container)


@router.post("/submit", response_model=SubmitClaimResponse)
async def submit_claim(
    request: SubmitClaimRequest,
    controller: ClaimController = Depends(get_controller),
):
    return await controller.submit_claim(request)


@router.get("/status/{claim_id}", response_model=ClaimStatusResponse)
async def get_claim_status(
    claim_id: UUID,
    controller: ClaimController = Depends(get_controller),
):
    return await controller.get_claim_status(claim_id)
