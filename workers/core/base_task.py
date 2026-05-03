import asyncio
import logging
from celery import Task
from celery.exceptions import Reject

logger = logging.getLogger(__name__)


class TaskBase(Task):
    max_retries = 5
    retry_backoff = True
    retry_jitter = True
    acks_late = True
    reject_on_worker_lost = True

    def retry_task(self, exception=None):
        if self.request.retries >= self.max_retries:
            raise Reject(exception, requeue=False)
        raise self.retry(exc=exception, countdown=10)

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        payload = args[0] if args else {}
        claim_id = payload.get("id") if isinstance(payload, dict) else None

        logger.error(
            "TASK DEAD | task=%s | task_id=%s | claim_id=%s | error=%s",
            self.name, task_id, claim_id, exc,
        )

        async def _save_failure():
            from repositories.tasks.database.failed_task_model import FailedTask
            from core.database.db_context import WorkerSessionLocal

            async with WorkerSessionLocal() as session:
                session.add(FailedTask(
                    task_id=task_id,
                    task_name=self.name,
                    claim_id=claim_id,
                    error=str(exc),
                    payload=payload if isinstance(payload, dict) else None,
                    attempts=self.request.retries + 1,
                ))
                await session.commit()

        try:
            asyncio.run(_save_failure())
        except Exception as save_exc:
            logger.error("FAILED to save dead task to DB | %s", save_exc)

        try:
            from datetime import datetime, timezone
            from core.notifications.templates import task_failed
            from core.notifications.email_service import send_email

            subject, html = task_failed.render(
                task_name=self.name,
                claim_id=claim_id,
                error=str(exc),
                attempts=self.request.retries + 1,
                failed_at=datetime.now(timezone.utc),
            )
            send_email(subject, html)
        except Exception as email_exc:
            logger.error("FAILED to send failure alert email | %s", email_exc)
