import uuid
from typing import Optional
from uuid import UUID

from sqlalchemy import select

from services.claims.contracts.iclaim_service import IClaimService
from services.claims.database.claim_model import Claim, ClaimItem, ClaimStatus
from core.database.db_context import DatabaseContext


class ClaimService(IClaimService):

    async def save_claim(self, data: dict) -> dict:
        async with DatabaseContext() as ctx:
            claim = Claim(
                id=uuid.uuid4(),
                member_number=data["member_number"],
                provider_code=data["provider_code"],
                status=ClaimStatus.PENDING,
            )
            ctx.session.add(claim)

            for item in data.get("items", []):
                claim_item = ClaimItem(
                    id=uuid.uuid4(),
                    claim_id=claim.id,
                    code=item["code"],
                    name=item["name"],
                    benefit_code=item["benefit_code"],
                    quantity=item["quantity"],
                    unit_price=item["unit_price"],
                    line_total=item["quantity"] * item["unit_price"],
                )
                ctx.session.add(claim_item)

        return {
            "id": str(claim.id),
            "member_number": claim.member_number,
            "provider_code": claim.provider_code,
            "status": claim.status.value,
            "items": data.get("items", []),
        }

    async def get_claim(self, claim_id: UUID) -> Optional[dict]:
        async with DatabaseContext() as ctx:
            result = await ctx.session.execute(
                select(Claim).where(Claim.id == claim_id)
            )
            claim = result.scalar_one_or_none()
            if not claim:
                return None
            return {
                "id": str(claim.id),
                "member_number": claim.member_number,
                "provider_code": claim.provider_code,
                "status": claim.status.value,
                "approved_amount": claim.approved_amount,
                "adjudication_result": claim.adjudication_result,
            }

    async def update_claim_status(self, claim_id: UUID, status: str) -> None:
        async with DatabaseContext() as ctx:
            result = await ctx.session.execute(
                select(Claim).where(Claim.id == claim_id)
            )
            claim = result.scalar_one_or_none()
            if claim:
                claim.status = ClaimStatus[status]
