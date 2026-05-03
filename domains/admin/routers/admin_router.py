import uuid
from fastapi import APIRouter, Query
from core.responses.api_response import ApiResponse
from core.exceptions.app_exceptions import FailedTaskNotFoundException, ReplayException
from domains.admin.models.admin_models import FailedTaskResponse, ReplayResponse
from repositories.tasks.task_repository import TaskRepository

router = APIRouter(tags=["Admin"])

_TASK_ROUTER = {
    "validate_claim_task":   "workers.claims.validate_claim_task",
    "adjudicate_claim_task": "workers.claims.adjudicate_claim_task",
    "notify_result_task":    "workers.claims.notify_result_task",
}


@router.get("/failed-tasks", response_model=ApiResponse[list[FailedTaskResponse]])
async def list_failed_tasks(
    include_replayed: bool = Query(default=False, description="Include already-replayed tasks"),
):
    repo = TaskRepository()
    rows = await repo.list_failed_tasks(include_replayed=include_replayed)
    data = [FailedTaskResponse.model_validate(row) for row in rows]
    label = "all" if include_replayed else "unresolved"
    return ApiResponse.ok(data, f"{len(data)} {label} failed task(s) found")


@router.post("/failed-tasks/{failed_task_id}/replay", response_model=ApiResponse[ReplayResponse])
async def replay_failed_task(failed_task_id: uuid.UUID):
    repo = TaskRepository()
    failed_task = await repo.get_failed_task(failed_task_id)

    if not failed_task:
        raise FailedTaskNotFoundException(f"Failed task {failed_task_id} not found")

    if not failed_task.payload:
        raise ReplayException(f"Failed task {failed_task_id} has no payload — cannot replay")

    module_path = _TASK_ROUTER.get(failed_task.task_name)
    if not module_path:
        raise ReplayException(f"No replay route registered for task '{failed_task.task_name}'")

    import importlib
    module = importlib.import_module(module_path)
    task_fn = getattr(module, failed_task.task_name)
    task_fn.delay(failed_task.payload)

    await repo.mark_as_replayed(failed_task_id)

    return ApiResponse.ok(
        ReplayResponse(
            replayed=True,
            message=f"Claim requeued into '{failed_task.task_name}' — idempotency guards will skip already-completed stages",
            failed_task_id=failed_task_id,
            claim_id=failed_task.claim_id,
        ),
        "Replay queued successfully",
    )
