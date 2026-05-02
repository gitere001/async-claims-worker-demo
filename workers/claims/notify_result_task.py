import asyncio
import logging
from uuid import UUID

from celery import shared_task
from sqlalchemy import select

from core.database.db_context import AsyncSessionLocal
from services.claims.database.claim_model import Claim, ClaimStatus
from workers.core.base_task import TaskBase

logger = logging.getLogger(__name__)


async def _notify(claim_data: dict) -> None:
    claim_id = UUID(claim_data["id"])
    adjudication_result = claim_data.get("adjudication_result", "UNKNOWN")
    approved_amount = claim_data.get("approved_amount", 0)
    member_number = claim_data.get("member_number")
    provider_code = claim_data.get("provider_code")

    async with AsyncSessionLocal() as session:
        claim = (await session.execute(
            select(Claim).where(Claim.id == claim_id)
        )).scalar_one_or_none()

        if claim:
            claim.status = ClaimStatus[adjudication_result] if adjudication_result in ClaimStatus.__members__ else ClaimStatus.APPROVED
            await session.commit()

    logger.info("=" * 60)
    logger.info(f"  CLAIM PROCESSED")
    logger.info(f"  Claim ID  : {claim_id}")
    logger.info(f"  Member    : {member_number}")
    logger.info(f"  Provider  : {provider_code}")
    logger.info(f"  Result    : {adjudication_result}")
    logger.info(f"  Amount    : KES {approved_amount:,.2f}")
    logger.info("=" * 60)


@shared_task(queue="notify_result", name="notify_result_task", bind=True, base=TaskBase)
def notify_result_task(self: TaskBase, claim_data: dict) -> None:
    try:
        asyncio.run(_notify(claim_data))
    except Exception as e:
        logger.error(f"NOTIFY FAILED | {e}")
