from celery import Celery
from kombu import Queue
from config.app_settings import settings
from workers.core.base_task import TaskBase

_redis_url = settings.get("redis_url", "")
if _redis_url.startswith("rediss://") and "ssl_cert_reqs" not in _redis_url:
    _redis_url += ("&" if "?" in _redis_url else "?") + "ssl_cert_reqs=CERT_NONE"

app = Celery(
    "claims_worker",
    broker=settings.get("rabbitmq_url"),
    backend=_redis_url,
    include=[
        "workers.claims.validate_claim_task",
        "workers.claims.adjudicate_claim_task",
        "workers.claims.notify_result_task",
    ],
    task_cls=TaskBase,
)

app.conf.update(
    task_default_queue="default",
    task_queues=[
        Queue("default"),
        Queue("validate_claim"),
        Queue("adjudicate_claim"),
        Queue("notify_result"),
    ],
    task_routes={
        "validate_claim_task":   {"queue": "validate_claim"},
        "adjudicate_claim_task": {"queue": "adjudicate_claim"},
        "notify_result_task":    {"queue": "notify_result"},
    },
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    broker_connection_retry_on_startup=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
)
