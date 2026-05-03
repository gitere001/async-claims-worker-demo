from pydantic import BaseModel


class HealthChecks(BaseModel):
    database: str
    rabbitmq: str
    redis: str


class HealthResponse(BaseModel):
    is_healthy: bool
    checks: HealthChecks
