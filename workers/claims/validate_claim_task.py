import asyncio
import logging
from uuid import UUID

from celery import shared_task
from sqlalchemy import select

from core.database.db_context import WorkerSessionLocal as AsyncSessionLocal
from services.claims.database.claim_model import Claim, ClaimStatus
from services.members.database.member_model import Member, MemberStatus
from services.providers.database.provider_model import ServiceProvider
from workers.core.base_task import TaskBase

logger = logging.getLogger(__name__)


async def _validate(claim_data: dict) -> dict:
    claim_id = UUID(claim_data["id"])
    member_number = claim_data["member_number"]
    provider_code = claim_data["provider_code"]

    async with AsyncSessionLocal() as session:
        # Mark claim as VALIDATING
        claim = (await session.execute(
            select(Claim).where(Claim.id == claim_id)
        )).scalar_one_or_none()

        if not claim:
            raise ValueError(f"Claim {claim_id} not found in database")

        claim.status = ClaimStatus.VALIDATING
        await session.commit()

        # Check member exists and is ACTIVE
        member = (await session.execute(
            select(Member).where(Member.member_number == member_number)
        )).scalar_one_or_none()

        if not member:
            claim.status = ClaimStatus.REJECTED
            claim.adjudication_result = f"Member {member_number} not found"
            await session.commit()
            raise ValueError(f"Member {member_number} not found")

        if member.status != MemberStatus.ACTIVE:
            claim.status = ClaimStatus.REJECTED
            claim.adjudication_result = f"Member {member_number} is {member.status.value}"
            await session.commit()
            raise ValueError(f"Member {member_number} is not ACTIVE")

        # Check provider is registered
        provider = (await session.execute(
            select(ServiceProvider).where(ServiceProvider.provider_code == provider_code)
        )).scalar_one_or_none()

        if not provider:
            claim.status = ClaimStatus.REJECTED
            claim.adjudication_result = f"Provider {provider_code} not registered"
            await session.commit()
            raise ValueError(f"Provider {provider_code} not registered")

        logger.info(
            f"VALIDATE OK | Claim: {claim_id} | "
            f"Member: {member_number} ({member.first_name} {member.last_name}) | "
            f"Provider: {provider.name}"
        )

    claim_data["validation_passed"] = True
    claim_data["member_product_code"] = member.product_code
    return claim_data


@shared_task(queue="validate_claim", name="validate_claim_task", bind=True, base=TaskBase)
def validate_claim_task(self: TaskBase, claim_data: dict) -> dict:
    try:
        result = asyncio.run(_validate(claim_data))
    except ValueError as e:
        logger.error(f"VALIDATE FAILED | {e}")
        return claim_data

    from workers.claims.adjudicate_claim_task import adjudicate_claim_task
    adjudicate_claim_task.delay(result)

    return result
