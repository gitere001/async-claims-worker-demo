import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import select, desc, cast
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from core.database.db_context import DatabaseContext
from repositories.tasks.database.failed_task_model import FailedTask
from repositories.claims.database.claim_model import Claim


class TaskRepository:

    async def get_failed_task(self, task_id: uuid.UUID) -> Optional[FailedTask]:
        async with DatabaseContext() as ctx:
            result = await ctx.session.execute(
                select(FailedTask).where(FailedTask.id == task_id)
            )
            return result.scalar_one_or_none()

    async def list_failed_tasks(self, include_replayed: bool = False) -> list[dict]:
        async with DatabaseContext() as ctx:
            query = (
                select(FailedTask, Claim.status.label("claim_status"))
                .outerjoin(Claim, cast(FailedTask.claim_id, PGUUID(as_uuid=True)) == Claim.id)
                .order_by(desc(FailedTask.failed_at))
            )
            if not include_replayed:
                query = query.where(FailedTask.replayed_at.is_(None))
            rows = (await ctx.session.execute(query)).all()
            return [
                {
                    "id": row.FailedTask.id,
                    "task_id": row.FailedTask.task_id,
                    "task_name": row.FailedTask.task_name,
                    "claim_id": row.FailedTask.claim_id,
                    "error": row.FailedTask.error,
                    "payload": row.FailedTask.payload,
                    "attempts": row.FailedTask.attempts,
                    "failed_at": row.FailedTask.failed_at,
                    "replayed_at": row.FailedTask.replayed_at,
                    "claim_status": row.claim_status.value if row.claim_status else None,
                }
                for row in rows
            ]

    async def mark_as_replayed(self, task_id: uuid.UUID) -> None:
        async with DatabaseContext() as ctx:
            result = await ctx.session.execute(
                select(FailedTask).where(FailedTask.id == task_id)
            )
            task = result.scalar_one_or_none()
            if task:
                task.replayed_at = datetime.now(timezone.utc)
                await ctx.session.commit()
