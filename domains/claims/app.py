from fastapi import APIRouter
from domains.claims.routers.claim_router import router as claim_router

router = APIRouter(prefix="/app/v1/claims")
router.include_router(claim_router)
