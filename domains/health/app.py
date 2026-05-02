from fastapi import FastAPI
from config.app_config import health_api_config
from domains.health.routers.health_router import router as health_router

health_app = FastAPI(**health_api_config.model_dump())
health_app.include_router(health_router)
