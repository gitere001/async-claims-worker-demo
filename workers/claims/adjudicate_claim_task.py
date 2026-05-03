import asyncio
import logging
from uuid import UUID

from celery import shared_task
from sqlalchemy import select

from core.database.db_context import WorkerSessionLocal as AsyncSessionLocal
from repositories.claims.database.claim_model import Claim, ClaimItem, ClaimStatus
from repositories.benefits.database.member_benefit_balance_model import MemberBenefitBalance
from workers.core.base_task import TaskBase
from workers.core.exceptions import NonRetryableError, RetryableError

logger = logging.getLogger(__name__)


async def _adjudicate(claim_data: dict) -> dict:
    claim_id = UUID(claim_data["id"])
    member_number = claim_data["member_number"]

    async with AsyncSessionLocal() as session:
        claim = (await session.execute(
            select(Claim).where(Claim.id == claim_id)
        )).scalar_one_or_none()

        if not claim:
            raise NonRetryableError(f"Claim {claim_id} not found in database — payload is corrupt")

        items = (await session.execute(
            select(ClaimItem).where(ClaimItem.claim_id == claim_id)
        )).scalars().all()

        if claim.adjudication_result is not None:
            logger.warning(
                "IDEMPOTENCY GUARD | adjudicate_claim | claim=%s already adjudicated with %s — forwarding to notify",
                claim_id, claim.adjudication_result,
            )
            claim_data["approved_amount"] = claim.approved_amount or 0.0
            claim_data["adjudication_result"] = claim.adjudication_result
            return claim_data

        claim.status = ClaimStatus.ADJUDICATING
        await session.commit()

        benefit_totals: dict[str, float] = {}
        for item in items:
            benefit_totals[item.benefit_code] = (
                benefit_totals.get(item.benefit_code, 0) + item.line_total
            )

        approved_amount = 0.0
        rejected_items = []

        for benefit_code, amount in benefit_totals.items():
            balance = (await session.execute(
                select(MemberBenefitBalance).where(
                    MemberBenefitBalance.member_number == member_number,
                    MemberBenefitBalance.benefit_code == benefit_code,
                    MemberBenefitBalance.policy_year == 2024,
                )
            )).scalar_one_or_none()

            if not balance:
                rejected_items.append(f"{benefit_code}: benefit not covered in plan")
                logger.warning("No balance found for %s / %s", member_number, benefit_code)
                continue

            if balance.remaining_amount < amount:
                rejected_items.append(
                    f"{benefit_code}: amount {amount} exceeds remaining balance {balance.remaining_amount}"
                )
                logger.warning(
                    "INSUFFICIENT BALANCE | %s | %s | Required: %s | Remaining: %s",
                    member_number, benefit_code, amount, balance.remaining_amount,
                )
                continue

            balance.used_amount += amount
            balance.remaining_amount -= amount
            approved_amount += amount

            logger.info(
                "BALANCE DEDUCTED | %s | %s | Amount: %s | Remaining: %s",
                member_number, benefit_code, amount, balance.remaining_amount,
            )

        if rejected_items:
            claim.adjudication_result = "PARTIALLY_APPROVED" if approved_amount > 0 else "REJECTED"
        else:
            claim.adjudication_result = "APPROVED"

        claim.approved_amount = approved_amount
        await session.commit()

        logger.info(
            "ADJUDICATE DONE | Claim: %s | Member: %s | Result: %s | Approved: %s",
            claim_id, member_number, claim.adjudication_result, approved_amount,
        )

    claim_data["approved_amount"] = approved_amount
    claim_data["adjudication_result"] = claim.adjudication_result
    return claim_data


@shared_task(queue="adjudicate_claim", name="adjudicate_claim_task", bind=True, base=TaskBase)
def adjudicate_claim_task(self: TaskBase, claim_data: dict) -> dict:
    try:
        result = asyncio.run(_adjudicate(claim_data))
    except (NonRetryableError, RetryableError):
        raise
    except Exception as e:
        raise RetryableError(str(e)) from e

    from workers.claims.notify_result_task import notify_result_task
    notify_result_task.delay(result)

    return result
