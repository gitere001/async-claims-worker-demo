class RetryableError(Exception):
    """Infrastructure failure — database blip, network timeout, temporary unavailability.
    Celery will retry automatically with exponential backoff."""
    pass


class NonRetryableError(Exception):
    """Hard failure — bad data, missing record, corrupt payload.
    Retrying will never succeed. Goes straight to on_failure."""
    pass
