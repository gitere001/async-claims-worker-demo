from uuid import UUID
from fastapi import APIRouter, Depends
from domains.claims.controllers.claim_controller import ClaimController
from domains.claims.app_services.claim_app_service import ClaimAppService
from domains.claims.app_services.interfaces.iclaim_app_service import IClaimAppService
from domains.claims.models.claim_models import (
    SubmitClaimRequest,
    SubmitClaimResponse,
    ClaimStatusResponse,
)
from proxies.claims.claim_service_proxy import ClaimServiceProxy

router = APIRouter(prefix="/claims", tags=["Claims"])


def get_controller() -> ClaimController:
    app_service: IClaimAppService = ClaimAppService(
        claim_service=ClaimServiceProxy()
    )
    return ClaimController(app_service=app_service)


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
