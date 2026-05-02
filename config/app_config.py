from pydantic import BaseModel


class MainAPIConfig(BaseModel):
    title: str = "Async Claims Worker Demo"
    version: str = "1.0.0"
    servers: list[dict] = [
        {"url": "http://localhost:8000", "description": "Local Dev Environment"},
    ]
    contact: dict = {
        "name": "Developer Support",
        "email": "james@edencaremedical.com",
    }


class ClaimsAPIConfig(BaseModel):
    title: str = "Claims A.P.I.s"
    version: str = "1.0.0"
    servers: list[dict] = [
        {"url": "http://localhost:8000/app/v1/claims", "description": "Local Dev Environment"},
    ]
    contact: dict = {
        "name": "Developer Support",
        "email": "james@edencaremedical.com",
    }


class HealthAPIConfig(BaseModel):
    title: str = "Health Checker A.P.I.s"
    version: str = "1.0.0"
    servers: list[dict] = [
        {"url": "http://localhost:8000/app/v1/health", "description": "Local Dev Environment"},
    ]
    contact: dict = {
        "name": "Developer Support",
        "email": "james@edencaremedical.com",
    }


main_api_config  = MainAPIConfig()
claims_api_config = ClaimsAPIConfig()
health_api_config = HealthAPIConfig()
