from fastapi import FastAPI
from config.app_config import claims_api_config
from domains.claims.routers.claim_router import router as claim_router

claims_app = FastAPI(**claims_api_config.model_dump())
claims_app.include_router(claim_router)
