import time
import logging
from fastapi import Request

logger = logging.getLogger(__name__)


async def log_middleware(request: Request, call_next):
    start = time.perf_counter()

    response = await call_next(request)

    duration_ms = (time.perf_counter() - start) * 1000

    logger.info(
        f"{request.method} {request.url.path} "
        f"→ {response.status_code} "
        f"({duration_ms:.1f}ms)"
    )

    return response
