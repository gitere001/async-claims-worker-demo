from celery import Task
from celery.exceptions import Reject


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
        retries = self.request.retries if hasattr(self.request, "retries") else 0
        if retries >= self.max_retries:
            raise Reject(reason=str(exc), requeue=False)
