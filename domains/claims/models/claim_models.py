from pydantic import BaseModel
from typing import List, Optional
from uuid import UUID


class ClaimItemRequest(BaseModel):
    code: str
    name: str
    benefit_code: str
    quantity: int
    unit_price: float


class SubmitClaimRequest(BaseModel):
    member_number: str
    provider_code: str
    items: List[ClaimItemRequest]


class SubmitClaimResponse(BaseModel):
    claim_id: UUID
    status: str
    message: str


class ClaimStatusResponse(BaseModel):
    claim_id: UUID
    status: str
    approved_amount: Optional[float] = None
    adjudication_result: Optional[str] = None
