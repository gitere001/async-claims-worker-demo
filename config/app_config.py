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


main_api_config = MainAPIConfig()
