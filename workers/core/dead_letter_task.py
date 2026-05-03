import logging
from celery import shared_task
from workers.core.base_task import TaskBase

logger = logging.getLogger(__name__)


@shared_task(queue="dead_letter", name="dead_letter_task", bind=True, base=TaskBase)
def dead_letter_task(self: TaskBase, claim_data: dict) -> None:
    claim_id = claim_data.get("id", "unknown")
    member_number = claim_data.get("member_number", "unknown")

    logger.error("=" * 60)
    logger.error("  DEAD LETTER MESSAGE RECEIVED")
    logger.error("  Claim ID     : %s", claim_id)
    logger.error("  Member       : %s", member_number)
    logger.error("  Full payload : %s", claim_data)
    logger.error("  Action       : inspect failed_tasks table to investigate")
    logger.error("=" * 60)
