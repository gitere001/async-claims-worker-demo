import asyncio
import logging
from uuid import UUID

from celery import shared_task
from sqlalchemy import select

from core.database.db_context import WorkerSessionLocal as AsyncSessionLocal
from repositories.claims.database.claim_model import Claim, ClaimStatus
from repositories.members.database.member_model import Member, MemberStatus
from repositories.providers.database.provider_model import ServiceProvider
from workers.core.base_task import TaskBase
from workers.core.exceptions import NonRetryableError, RetryableError

logger = logging.getLogger(__name__)

_PAST_VALIDATION = {
    ClaimStatus.ADJUDICATING,
    ClaimStatus.APPROVED,
    ClaimStatus.REJECTED,
    ClaimStatus.FAILED,
}


async def _validate(claim_data: dict) -> dict | None:
    claim_id = UUID(claim_data["id"])
    member_number = claim_data["member_number"]
    provider_code = claim_data["provider_code"]

    async with AsyncSessionLocal() as session:
        claim = (await session.execute(
            select(Claim).where(Claim.id == claim_id)
        )).scalar_one_or_none()

        if not claim:
            raise NonRetryableError(f"Claim {claim_id} not found in database — payload is corrupt")

        if claim.status in _PAST_VALIDATION:
            logger.warning(
                "IDEMPOTENCY GUARD | validate_claim | claim=%s already at %s — skipping",
                claim_id, claim.status.value,
            )
            return None

        claim.status = ClaimStatus.VALIDATING
        await session.commit()

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

        provider = (await session.execute(
            select(ServiceProvider).where(ServiceProvider.provider_code == provider_code)
        )).scalar_one_or_none()

        if not provider:
            claim.status = ClaimStatus.REJECTED
            claim.adjudication_result = f"Provider {provider_code} not registered"
            await session.commit()
            raise ValueError(f"Provider {provider_code} not registered")

        logger.info(
            "VALIDATE OK | Claim: %s | Member: %s (%s %s) | Provider: %s",
            claim_id, member_number, member.first_name, member.last_name, provider.name,
        )

    claim_data["validation_passed"] = True
    claim_data["member_product_code"] = member.product_code
    return claim_data


@shared_task(queue="validate_claim", name="validate_claim_task", bind=True, base=TaskBase)
def validate_claim_task(self: TaskBase, claim_data: dict) -> dict:
    try:
        result = asyncio.run(_validate(claim_data))
    except ValueError as e:
        # Business rule failure — claim already marked REJECTED in DB, do not retry
        logger.error("VALIDATE FAILED | %s", e)
        return claim_data
    except (NonRetryableError, RetryableError):
        raise  # Let TaskBase handle — NonRetryable goes to on_failure, Retryable gets retried
    except Exception as e:
        # Unexpected infrastructure error — wrap and retry
        raise RetryableError(str(e)) from e

    if result is None:
        return claim_data

    from workers.claims.adjudicate_claim_task import adjudicate_claim_task
    adjudicate_claim_task.delay(result)

    return result
