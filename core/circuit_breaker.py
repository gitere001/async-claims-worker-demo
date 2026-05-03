import logging
import time
from enum import Enum

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "CLOSED"       # normal — requests go through
    OPEN = "OPEN"           # tripped — requests fail immediately
    HALF_OPEN = "HALF_OPEN" # testing recovery — one request allowed through


class CircuitBreaker:
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,   # trips after this many failures
        recovery_timeout: int = 60,   # seconds before trying again
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float | None = None

    def call(self, func, *args, **kwargs):
        if self._state == CircuitState.OPEN:
            if self._should_attempt_recovery():
                self._state = CircuitState.HALF_OPEN
                logger.warning("CIRCUIT BREAKER | %s | HALF-OPEN — testing recovery", self.name)
            else:
                raise CircuitOpenError(
                    f"Circuit breaker '{self.name}' is OPEN — "
                    f"database is down, failing fast"
                )

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except CircuitOpenError:
            raise
        except Exception as exc:
            self._on_failure(exc)
            raise

    def _on_success(self):
        if self._state == CircuitState.HALF_OPEN:
            logger.info("CIRCUIT BREAKER | %s | CLOSED — recovery confirmed", self.name)
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = None

    def _on_failure(self, exc: Exception):
        self._failure_count += 1
        self._last_failure_time = time.monotonic()

        if self._failure_count >= self.failure_threshold:
            if self._state != CircuitState.OPEN:
                logger.error(
                    "CIRCUIT BREAKER | %s | OPEN — %d consecutive failures, last error: %s",
                    self.name, self._failure_count, exc,
                )
            self._state = CircuitState.OPEN

    def _should_attempt_recovery(self) -> bool:
        if self._last_failure_time is None:
            return True
        return (time.monotonic() - self._last_failure_time) >= self.recovery_timeout

    @property
    def state(self) -> str:
        return self._state.value


class CircuitOpenError(Exception):
    """Raised when a circuit breaker is open — fail fast, do not attempt the call."""
    pass


# One breaker per external dependency, shared across all tasks in the worker process
db_circuit = CircuitBreaker(name="database", failure_threshold=5, recovery_timeout=60)
