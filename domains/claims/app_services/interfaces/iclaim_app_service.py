from abc import ABC, abstractmethod
from uuid import UUID
from domains.claims.models.claim_models import (
    SubmitClaimRequest,
    SubmitClaimResponse,
    ClaimStatusResponse,
)


class IClaimAppService(ABC):

    @abstractmethod
    async def submit_claim(self, request: SubmitClaimRequest) -> SubmitClaimResponse: ...

    @abstractmethod
    async def get_claim_status(self, claim_id: UUID) -> ClaimStatusResponse: ...
