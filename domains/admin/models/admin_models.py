import uuid
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


class ClaimItemPayload(BaseModel):
    code: str
    name: str
    benefit_code: str
    quantity: int
    unit_price: float


class ClaimPayload(BaseModel):
    id: str
    member_number: str
    provider_code: str
    status: str
    items: List[ClaimItemPayload]


class FailedTaskResponse(BaseModel):
    id: uuid.UUID
    task_id: str
    task_name: str
    claim_id: Optional[str]
    error: str
    payload: Optional[ClaimPayload]
    attempts: int
    failed_at: datetime
    replayed_at: Optional[datetime] = None
    claim_status: Optional[str] = None


class ReplayResponse(BaseModel):
    replayed: bool
    message: str
    failed_task_id: uuid.UUID
    claim_id: Optional[str]
