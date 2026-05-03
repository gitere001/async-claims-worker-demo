import asyncio
import logging
from uuid import UUID

from celery import shared_task
from sqlalchemy import select

from core.database.db_context import WorkerSessionLocal as AsyncSessionLocal
from repositories.claims.database.claim_model import Claim, ClaimStatus
from workers.core.base_task import TaskBase
from workers.core.exceptions import NonRetryableError, RetryableError
from core.circuit_breaker import db_circuit, CircuitOpenError

logger = logging.getLogger(__name__)

_TERMINAL_STATUSES = {ClaimStatus.APPROVED, ClaimStatus.REJECTED, ClaimStatus.FAILED}


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

        if not claim:
            raise NonRetryableError(f"Claim {claim_id} not found in database — payload is corrupt")

        if claim.status in _TERMINAL_STATUSES:
            logger.warning(
                "IDEMPOTENCY GUARD | notify_result | claim=%s already at %s — skipping",
                claim_id, claim.status.value,
            )
            return

        claim.status = (
            ClaimStatus[adjudication_result]
            if adjudication_result in ClaimStatus.__members__
            else ClaimStatus.APPROVED
        )
        await session.commit()

    logger.info("=" * 60)
    logger.info("  CLAIM PROCESSED")
    logger.info("  Claim ID  : %s", claim_id)
    logger.info("  Member    : %s", member_number)
    logger.info("  Provider  : %s", provider_code)
    logger.info("  Result    : %s", adjudication_result)
    logger.info("  Amount    : KES %s", f"{approved_amount:,.2f}")
    logger.info("=" * 60)


@shared_task(queue="notify_result", name="notify_result_task", bind=True, base=TaskBase)
def notify_result_task(self: TaskBase, claim_data: dict) -> None:
    try:
        db_circuit.call(asyncio.run, _notify(claim_data))
    except CircuitOpenError as e:
        raise RetryableError(str(e)) from e
    except (NonRetryableError, RetryableError):
        raise
    except Exception as e:
        raise RetryableError(str(e)) from e
