from fastapi import APIRouter
from domains.admin.routers.admin_router import router as admin_router

router = APIRouter(prefix="/app/v1/admin")
router.include_router(admin_router)
