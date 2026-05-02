import asyncio
import logging
from uuid import UUID

from celery import shared_task
from sqlalchemy import select

from core.database.db_context import AsyncSessionLocal
from services.claims.database.claim_model import Claim, ClaimItem, ClaimStatus
from services.benefits.database.member_benefit_balance_model import MemberBenefitBalance
from workers.core.base_task import TaskBase

logger = logging.getLogger(__name__)


async def _adjudicate(claim_data: dict) -> dict:
    claim_id = UUID(claim_data["id"])
    member_number = claim_data["member_number"]

    async with AsyncSessionLocal() as session:
        # Load claim and its items from DB
        claim = (await session.execute(
            select(Claim).where(Claim.id == claim_id)
        )).scalar_one_or_none()

        items = (await session.execute(
            select(ClaimItem).where(ClaimItem.claim_id == claim_id)
        )).scalars().all()

        claim.status = ClaimStatus.ADJUDICATING
        await session.commit()

        # Group items by benefit_code and sum their line totals
        benefit_totals: dict[str, float] = {}
        for item in items:
            benefit_totals[item.benefit_code] = (
                benefit_totals.get(item.benefit_code, 0) + item.line_total
            )

        approved_amount = 0.0
        rejected_items = []

        for benefit_code, amount in benefit_totals.items():
            # Check member's remaining balance for this benefit
            balance = (await session.execute(
                select(MemberBenefitBalance).where(
                    MemberBenefitBalance.member_number == member_number,
                    MemberBenefitBalance.benefit_code == benefit_code,
                    MemberBenefitBalance.policy_year == 2024,
                )
            )).scalar_one_or_none()

            if not balance:
                rejected_items.append(f"{benefit_code}: benefit not covered in plan")
                logger.warning(f"No balance found for {member_number} / {benefit_code}")
                continue

            if balance.remaining_amount < amount:
                rejected_items.append(
                    f"{benefit_code}: amount {amount} exceeds remaining balance {balance.remaining_amount}"
                )
                logger.warning(
                    f"INSUFFICIENT BALANCE | {member_number} | {benefit_code} | "
                    f"Required: {amount} | Remaining: {balance.remaining_amount}"
                )
                continue

            # Deduct from balance
            balance.used_amount += amount
            balance.remaining_amount -= amount
            approved_amount += amount

            logger.info(
                f"BALANCE DEDUCTED | {member_number} | {benefit_code} | "
                f"Amount: {amount} | Remaining: {balance.remaining_amount}"
            )

        # Set final adjudication result
        if rejected_items:
            claim.adjudication_result = "PARTIALLY_APPROVED" if approved_amount > 0 else "REJECTED"
        else:
            claim.adjudication_result = "APPROVED"

        claim.approved_amount = approved_amount
        await session.commit()

        logger.info(
            f"ADJUDICATE DONE | Claim: {claim_id} | Member: {member_number} | "
            f"Result: {claim.adjudication_result} | Approved: {approved_amount}"
        )

    claim_data["approved_amount"] = approved_amount
    claim_data["adjudication_result"] = claim.adjudication_result
    return claim_data


@shared_task(queue="adjudicate_claim", name="adjudicate_claim_task", bind=True, base=TaskBase)
def adjudicate_claim_task(self: TaskBase, claim_data: dict) -> dict:
    try:
        result = asyncio.run(_adjudicate(claim_data))
    except Exception as e:
        logger.error(f"ADJUDICATE FAILED | {e}")
        return claim_data

    from workers.claims.notify_result_task import notify_result_task
    notify_result_task.delay(result)

    return result
