# How the Workers Work

This document explains what happens after a claim is submitted — who is involved, what each piece does, and every production strategy built into the system.

---

## The problem workers solve

When a claim is submitted, three things need to happen:

1. Check the member is active and the provider is registered
2. Check benefit balances and deduct the approved amount
3. Write the final result and log the outcome

Each of these involves database queries and could take several seconds. If the API waited for all three to finish before responding to the user, every claim submission would take 5–10 seconds. That is unacceptable.

The solution is to respond immediately and do the slow work in the background. The API saves the claim, tells the user "received", and hands the work off to workers that run completely independently.

---

## The three things involved

### 1. RabbitMQ — the waiting room

RabbitMQ holds messages. That is its only job.

When the API finishes saving a claim, it drops a message into RabbitMQ that says "here is a claim that needs validating, here is all the data". RabbitMQ puts that message into a queue called `validate_claim` and holds it there.

RabbitMQ does not run any code. It does not know what validation means. It just holds the message until someone picks it up.

RabbitMQ runs in Docker. You start it with `make up`.

### 2. The Worker — the background process

The worker is a completely separate Python process from your API. You start it in a different terminal with `make worker`. It has nothing to do with FastAPI.

The worker connects to RabbitMQ and keeps that connection open permanently. It sits there waiting. When RabbitMQ receives a message, it immediately pushes it down the open connection to the worker. The worker wakes up and runs the Python function.

There is no polling. The worker does not ask RabbitMQ "any messages?" every second. RabbitMQ pushes to the worker the instant something arrives — the same way a WebSocket pushes data to a browser instead of the browser refreshing the page every second.

### 3. Celery — the library that connects them

Celery is not a separate process. It is a Python library — like SQLAlchemy is a library for talking to PostgreSQL, Celery is a library for talking to RabbitMQ.

The API uses Celery to drop messages into RabbitMQ. The worker uses Celery to pick messages up from RabbitMQ and run the task functions. Both use the same library. Neither talks to RabbitMQ directly.

---

## The two terminals

```
Terminal 1 — make api          Terminal 2 — make worker
(FastAPI + Celery library)     (Celery worker process)
          │                              │
          │                         connected to RabbitMQ
          │                         listening on all queues
          │                              │
    claim submitted                      │
          │                              │
    .delay() called                      │
          │                              │
          └── drops message ──► RabbitMQ ──► pushed to worker
                                              │
                                        runs validate_claim_task
```

Terminal 1 drops messages in. Terminal 2 picks messages out. RabbitMQ is the post box in the middle.

---

## The queues

The worker listens on five queues simultaneously. These are defined in `worker.py`:

| Queue | Purpose |
|---|---|
| `default` | General fallback queue |
| `validate_claim` | Stage 1 — member and provider checks |
| `adjudicate_claim` | Stage 2 — benefit balance checks and deductions |
| `notify_result` | Stage 3 — final status write and logging |
| `dead_letter` | Catches any message that failed all its retries |

Each pipeline queue (`validate_claim`, `adjudicate_claim`, `notify_result`) is configured with a **dead letter exchange**. If a message is rejected after exhausting all retries, RabbitMQ automatically routes it to the `dead_letter` queue. Nothing is ever lost.

---

## The happy path — full pipeline

```
API saves claim (status=PENDING)
        │
        └──► validate_claim queue
                    │
             validate_claim_task runs
             member active? provider registered?
                    │
             ┌──────┴──────┐
           PASS           FAIL → status=REJECTED → pipeline stops
             │
             └──► adjudicate_claim queue
                        │
                 adjudicate_claim_task runs
                 benefit balances covered?
                        │
                 ┌──────┴──────┐
               PASS          FAIL → status=REJECTED / PARTIALLY_APPROVED
                 │
                 └──► notify_result queue
                            │
                     notify_result_task runs
                     writes final status → APPROVED
                     logs summary
                     pipeline complete
```

---

## The three task files

### Stage 1 — `workers/claims/validate_claim_task.py`

**Queue:** `validate_claim`

**What triggers it:** The service calls `validate_claim_task.delay(saved)` after saving the claim to PostgreSQL. `saved` is a plain Python dict containing the claim id, member number, provider code, and items.

**What it does:**

1. Creates a new event loop with `asyncio.run(_validate(claim_data))`. This is necessary because Celery tasks are synchronous by default, but the database code is async.
2. **Idempotency check** — if the claim status is already past validation (`ADJUDICATING`, `APPROVED`, `REJECTED`, or `FAILED`), logs a warning and returns immediately without doing any work. This means if RabbitMQ re-delivers this message (network blip, worker restart), the task is completely safe to run again.
3. Fetches the claim from PostgreSQL and sets status to `VALIDATING`.
4. Looks up the member. If the member does not exist or is not `ACTIVE`, sets status to `REJECTED`, writes the reason, and stops. The pipeline ends here.
5. Looks up the provider. If the provider is not registered, sets status to `REJECTED` and stops.
6. If both checks pass, adds `validation_passed: True` and `member_product_code` to the dict.
7. Calls `adjudicate_claim_task.delay(result)` — drops the updated dict into the `adjudicate_claim` queue.

**What it passes on:** The same dict it received, with two new fields added — `validation_passed` and `member_product_code`.

---

### Stage 2 — `workers/claims/adjudicate_claim_task.py`

**Queue:** `adjudicate_claim`

**What triggers it:** `validate_claim_task` calls `adjudicate_claim_task.delay(result)` at the end of Stage 1.

**What it does:**

1. `asyncio.run(_adjudicate(claim_data))` — same async bridge.
2. **Idempotency check** — if `claim.adjudication_result` is already set, the adjudication already happened. Instead of running it again, it copies the already-stored result into the dict and **still forwards to `notify_result_task`**. This handles the case where adjudication completed but the worker crashed before notify ran — the re-delivered message skips adjudication but still completes the pipeline.
3. Loads the claim and all its `ClaimItem` rows from PostgreSQL.
4. Sets status to `ADJUDICATING`.
5. Groups all items by `benefit_code` and sums the amounts.
6. For each benefit code, queries `MemberBenefitBalance` to check if the member has this benefit and has enough remaining balance.
7. For every benefit that passes, deducts the amount from `used_amount`, reduces `remaining_amount`, and adds to `approved_amount`.
8. For every benefit that fails, records the reason in `rejected_items`.
9. Sets the final adjudication result:
   - All benefits approved → `APPROVED`
   - Some approved, some rejected → `PARTIALLY_APPROVED`
   - Nothing approved → `REJECTED`
10. Writes `approved_amount` and `adjudication_result` to the claim row and commits.
11. Calls `notify_result_task.delay(result)`.

**What it passes on:** The same dict with two new fields — `approved_amount` and `adjudication_result`.

---

### Stage 3 — `workers/claims/notify_result_task.py`

**Queue:** `notify_result`

**What triggers it:** `adjudicate_claim_task` calls `notify_result_task.delay(result)` at the end of Stage 2.

**What it does:**

1. `asyncio.run(_notify(claim_data))` — same async bridge.
2. **Idempotency check** — if the claim status is already terminal (`APPROVED`, `REJECTED`, or `FAILED`), logs a warning and returns without doing any work. Safe to re-run.
3. Loads the claim from PostgreSQL.
4. Sets the final status on the claim row — `APPROVED`, `PARTIALLY_APPROVED`, or `REJECTED`.
5. Commits.
6. Logs the full summary to the console:

```
============================================================
  CLAIM PROCESSED
  Claim ID  : 1c29e729-bc5f-4d4c-bab3-f4c37dbc1537
  Member    : 1524100
  Provider  : METROPOLITAN-01
  Result    : APPROVED
  Amount    : KES 5,000.00
============================================================
```

There is no next task. This is the end of the pipeline.

---

## The dict that travels through every stage

The same Python dict starts in the repository and travels through all three workers. Each worker adds fields to it.

After the repository saves the claim:
```json
{
  "id": "1c29e729-...",
  "member_number": "1524100",
  "provider_code": "METROPOLITAN-01",
  "status": "PENDING",
  "items": [...]
}
```

After validate_claim_task:
```json
{
  "id": "1c29e729-...",
  "member_number": "1524100",
  "provider_code": "METROPOLITAN-01",
  "status": "PENDING",
  "items": [...],
  "validation_passed": true,
  "member_product_code": "PREMIUM"
}
```

After adjudicate_claim_task:
```json
{
  "id": "1c29e729-...",
  "member_number": "1524100",
  "provider_code": "METROPOLITAN-01",
  "status": "PENDING",
  "items": [...],
  "validation_passed": true,
  "member_product_code": "PREMIUM",
  "approved_amount": 5000.0,
  "adjudication_result": "APPROVED"
}
```

The notify worker receives the full picture and uses it to write the final status and log the summary.

---

## Production strategy 1 — Idempotency guards

### The problem

RabbitMQ can re-deliver a message in several scenarios:
- The worker processed the task successfully but crashed before sending the acknowledgement to RabbitMQ
- A network blip causes RabbitMQ to think the worker is gone and re-deliver the message
- A manual replay of a failed task re-submits a message for a claim that is already partially processed

Without protection, the same task would run twice on the same claim — deducting balances twice, setting the wrong final status, or overwriting completed work.

### The solution

Every task checks the current state of the claim in the database **before doing any work**. If the claim is already past the stage this task handles, the task exits immediately.

**validate_claim_task** — skips if claim status is already `ADJUDICATING`, `APPROVED`, `REJECTED`, or `FAILED`:
```python
_PAST_VALIDATION = {ClaimStatus.ADJUDICATING, ClaimStatus.APPROVED, ClaimStatus.REJECTED, ClaimStatus.FAILED}

if claim.status in _PAST_VALIDATION:
    logger.warning("IDEMPOTENCY GUARD | validate_claim | claim=%s already at %s — skipping", ...)
    return None
```

**adjudicate_claim_task** — skips adjudication but still fires notify if adjudication already ran:
```python
if claim.adjudication_result is not None:
    # Don't re-adjudicate. But notify may not have run yet — forward to it.
    claim_data["approved_amount"] = claim.approved_amount or 0.0
    claim_data["adjudication_result"] = claim.adjudication_result
    return claim_data  # notify_result_task.delay(result) still fires
```

**notify_result_task** — skips if claim is already in a terminal status:
```python
_TERMINAL_STATUSES = {ClaimStatus.APPROVED, ClaimStatus.REJECTED, ClaimStatus.FAILED}

if claim.status in _TERMINAL_STATUSES:
    logger.warning("IDEMPOTENCY GUARD | notify_result | claim=%s already at %s — skipping", ...)
    return
```

The result: every task is safe to run multiple times. The second run is a no-op. This is the foundation of reliable message processing.

---

## Production strategy 2 — Smart retry with exception classification

### The problem

Not all failures deserve the same response. A database connection drop is temporary — retrying makes sense. A payload with a missing `claim_id` will never succeed no matter how many times you retry — it wastes resources and fills your logs.

### The solution

Two exception types in `workers/core/exceptions.py`:

```python
class RetryableError(Exception):
    """Temporary infrastructure problem — DB blip, network timeout. Retry with backoff."""
    pass

class NonRetryableError(Exception):
    """Permanent business failure — corrupt payload, claim not found. Fail immediately."""
    pass
```

Every task wraps its logic in structured exception handling:

```python
try:
    result = db_circuit.call(asyncio.run, _validate(claim_data))
except CircuitOpenError as e:
    raise RetryableError(str(e)) from e      # DB is down — retry
except (NonRetryableError, RetryableError):
    raise                                     # already classified — re-raise as-is
except Exception as e:
    raise RetryableError(str(e)) from e      # unknown error — assume retryable
```

Business rule failures (member not found, provider not registered) raise `ValueError` — a separate branch catches these, logs them, and returns without retrying:
```python
except ValueError as e:
    logger.error("VALIDATE FAILED | %s", e)
    return claim_data   # pipeline stops cleanly, no retry
```

### The retry configuration in `workers/core/base_task.py`

```python
autoretry_for = (RetryableError,)   # only retry on this specific type
max_retries = 5
retry_backoff = 30                  # first retry waits 30s
retry_backoff_max = 300             # retries never wait more than 5 minutes
retry_jitter = True                 # adds small random variation to avoid thundering herd
```

The backoff schedule for 5 retries:
- Attempt 1 fails → wait ~30s → Attempt 2
- Attempt 2 fails → wait ~60s → Attempt 3
- Attempt 3 fails → wait ~120s → Attempt 4
- Attempt 4 fails → wait ~240s → Attempt 5
- Attempt 5 fails → wait ~300s → Attempt 6 (final)
- All retries exhausted → `on_failure` fires

The jitter means no two claims retry at exactly the same moment, which prevents a burst of retries from overwhelming a database that is just recovering.

---

## Production strategy 3 — Circuit breaker

### The problem

If the database goes down, every task will fail immediately, wait for backoff, retry, fail again, and repeat. With 100 queued messages and 5 retries each, the worker will hammer the database with 500 failed connection attempts — making it harder for the database to recover and wasting all available retry budget.

### The solution

A circuit breaker in `core/circuit_breaker.py`. It sits in front of every database call and tracks consecutive failures. After a threshold is reached, it "trips" and starts rejecting calls immediately without even attempting the database.

### The three states

```
CLOSED (normal)
  │
  │  5 consecutive failures
  ▼
OPEN (tripped — fail fast)
  │
  │  60 seconds pass
  ▼
HALF-OPEN (testing recovery — one request allowed through)
  │
  ├── that request succeeds → back to CLOSED
  └── that request fails    → back to OPEN, reset 60s timer
```

**CLOSED** — all calls go through normally. This is the default state.

**OPEN** — calls are rejected immediately with `CircuitOpenError` before touching the database. When a task receives `CircuitOpenError`, it raises `RetryableError` — which triggers the exponential backoff. The messages are NOT dropped. They wait in RabbitMQ, backing off, until the circuit closes again.

**HALF-OPEN** — after 60 seconds in OPEN state, the breaker allows exactly one request through as a probe. If it succeeds, the circuit closes and normal operation resumes. If it fails, the breaker goes back to OPEN and resets the 60-second timer.

### Shared instance

One breaker instance is shared across all tasks in the worker process:

```python
# core/circuit_breaker.py
db_circuit = CircuitBreaker(name="database", failure_threshold=5, recovery_timeout=60)
```

Every task wraps its database call with:
```python
result = db_circuit.call(asyncio.run, _validate(claim_data))
```

This means if the database is down, the very first task to detect it trips the breaker. All subsequent tasks immediately get `CircuitOpenError` without attempting the database — protecting the database and conserving retry budget.

---

## Production strategy 4 — Dead letter queue

### The problem

Before the DLQ was added, if a task failed all its retries the message simply disappeared. No record of what failed, no way to replay it, no notification. A claim could silently vanish from the pipeline.

### How the DLQ works

Every pipeline queue (`validate_claim`, `adjudicate_claim`, `notify_result`) is configured with a **dead letter exchange (DLX)**. This is an instruction to RabbitMQ at the infrastructure level:

> "If a message in this queue is rejected after all retries, do not drop it — route it to the `dead_letter` queue instead."

This happens inside RabbitMQ, before any Python code runs. Even if the worker process crashes, the routing still happens.

### The three safety nets

**Safety net 1 — RabbitMQ `dead_letter` queue**

The message lands here and stays until you deal with it. Nothing is lost. Visible in the RabbitMQ dashboard at `http://localhost:15672`.

**Safety net 2 — `failed_tasks` table in PostgreSQL**

Every time a task exhausts all its retries, a row is written to the `failed_tasks` table. Permanent, queryable record of every claim that failed with the exact error and full payload.

```sql
SELECT task_name, claim_id, error, attempts, failed_at, replayed_at
FROM failed_tasks
ORDER BY failed_at DESC;
```

**Safety net 3 — Email alert via Resend**

Immediately after saving to `failed_tasks`, an HTML alert email is sent. The email shows the task name, claim id, exact error message, number of attempts, and a timestamp. You know about the failure the moment it happens.

### How the `failed_tasks` save works — step by step

This all happens inside `workers/core/base_task.py` in the `on_failure` method, which Celery calls automatically when a task exhausts all its retries.

**Step 1 — Extract the payload and claim id**
```python
payload = args[0] if args else {}
claim_id = payload.get("id") if isinstance(payload, dict) else None
```

**Step 2 — Log the failure immediately**
```python
logger.error("TASK DEAD | task=%s | task_id=%s | claim_id=%s | error=%s", ...)
```
Even if the DB save fails next, this always appears in the worker logs.

**Step 3 — Save to `failed_tasks` table**

Each field saved:

| Field | Value |
|---|---|
| `task_id` | Celery's unique ID for this execution |
| `task_name` | e.g. `validate_claim_task` |
| `claim_id` | from `payload["id"]` |
| `error` | `str(exc)` — the full exception message |
| `payload` | The entire dict — everything needed to replay |
| `attempts` | `self.request.retries + 1` |
| `replayed_at` | `NULL` until the admin replay endpoint stamps it |

**Step 4 — Send the alert email**

Runs in a separate `try/except` block, independent of the DB save. If the email fails, the DB save still completed. If the DB save failed, the email still sends.

### The dead letter task handler

`workers/core/dead_letter_task.py` listens on the `dead_letter` queue. When a message arrives it logs a full alert and tells the operator to check the `failed_tasks` table.

### The full failure flow

```
validate_claim_task fails
        │
        retry 1 → retry 2 → retry 3 → retry 4 → retry 5 → retry 6
                                                               │
                                                       max retries reached
                                                               │
                                                       on_failure fires
                                                               │
                    ┌──────────────────────────────────────────┼──────────────────────────────┐
                    │                                          │                               │
                    ▼                                          ▼                               ▼
          dead_letter queue                  failed_tasks row in PostgreSQL       alert email sent via Resend
          (message preserved)               (task_name, claim_id, error,          (task name, error, attempts,
                    │                        payload, attempts, failed_at)         timestamp)
                    ▼
          dead_letter_task logs alert
```

---

## Production strategy 5 — Admin replay endpoint

### The problem

When a failed task is fixed (bug patched, data corrected), you need a way to re-run it without manually constructing a Celery call or writing a script. You also need to know whether the replay actually resolved the claim.

### The API endpoints

**List failed tasks** — `GET /app/v1/admin/failed-tasks`

By default returns only unresolved failed tasks. Add `?include_replayed=true` to see everything.

Response includes `claim_status` — the **live current status** of the claim from the `claims` table via a JOIN, not a cached value:

```json
[
  {
    "id": "abc123",
    "task_name": "validate_claim_task",
    "claim_id": "1c29e729-...",
    "error": "Database connection refused",
    "attempts": 6,
    "failed_at": "2024-01-15T10:30:00Z",
    "replayed_at": null,
    "claim_status": "PENDING"
  }
]
```

**Replay a failed task** — `POST /app/v1/admin/failed-tasks/{id}/replay`

1. Fetches the `failed_tasks` row and its stored `payload`
2. Looks up the correct task function from the internal router:
   ```python
   _TASK_ROUTER = {
       "validate_claim_task":   "workers.claims.validate_claim_task",
       "adjudicate_claim_task": "workers.claims.adjudicate_claim_task",
       "notify_result_task":    "workers.claims.notify_result_task",
   }
   ```
3. Calls `task_fn.delay(payload)` — re-queues the exact original payload
4. Stamps `replayed_at = now()` on the `failed_tasks` row

**The idempotency guards make replay safe.** If the claim already completed stages 1 and 2 before failing at stage 3, replaying `validate_claim_task` will:
- Stage 1: detect claim is already `ADJUDICATING` → skip
- Stage 2: detect `adjudication_result` already set → skip adjudication, still fires notify
- Stage 3: run notify, write final status

No duplicate deductions. No double-processing. The pipeline completes from exactly where it failed.

### How to know if a replay resolved the claim

The `claim_status` field in the list endpoint is a live JOIN against the `claims` table. After a successful replay, call `GET /app/v1/admin/failed-tasks` again — the `claim_status` will have changed from `PENDING` or `ADJUDICATING` to `APPROVED` or `REJECTED`. This tells you definitively whether the replay succeeded without having to query a separate endpoint.

---

## Production strategy 6 — Worker concurrency with gevent

### The problem with the default prefork pool

By default, Celery starts 8 worker processes (one per CPU core). Each process handles one task at a time. When a task makes a database query, the entire process sits idle waiting for the response. With 8 processes, you can only handle 8 concurrent tasks — most of them doing nothing while waiting for Postgres.

### The solution: gevent pool

The worker uses the gevent pool instead of prefork:

```bash
celery -A worker worker --loglevel=info --pool=gevent --concurrency=32
```

gevent is a concurrency library that patches Python's standard IO operations to be non-blocking. Instead of 8 separate OS processes each waiting for IO, you have **1 process running 32 lightweight coroutines**. When one coroutine makes a database call and waits for the response, the event loop immediately switches to another coroutine that is ready to run.

### Why this is the right choice for this worker

All three task functions call `asyncio.run()` which drives async SQLAlchemy database queries. The work is entirely IO-bound — CPU is barely used. The bottleneck is network round-trips to Postgres and RabbitMQ.

With gevent:
- 32 tasks can be in-flight simultaneously in one process
- When any task is waiting on a DB query, the other 31 can be running
- Memory usage is far lower than 8 separate processes
- Scaling up means increasing `--concurrency` — no rebuild required

With prefork at 8 processes, 7 of those processes are typically idle at any given moment, just waiting for database responses.

### What gevent does NOT change

- Retry logic — still works identically
- Circuit breaker — shared at the process level, still works identically
- Idempotency guards — each task still does its own DB check
- The `asyncio.run()` bridge — still required because gevent and asyncio are separate concurrency systems; `asyncio.run()` creates a fresh event loop for each task call

---

## Why asyncio.run() in every worker

Celery tasks are regular synchronous Python functions. But all the database code uses async SQLAlchemy — it uses `await` everywhere.

You cannot call `await` inside a synchronous function. So each task wraps the async database code in `asyncio.run()`, which creates a brand new event loop, runs the async function to completion, then destroys the loop.

This is also why the workers use a separate database engine with `NullPool`. The FastAPI API runs in one event loop permanently, so it can keep a connection pool warm. But each `asyncio.run()` creates a brand new event loop — a pooled connection from the previous loop cannot be reused in the new one. `NullPool` disables pooling so each worker task gets a fresh connection and closes it when done.

---

## Why the import is inside the function

In each task file you will see the next task imported inside the function rather than at the top of the file:

```python
def validate_claim_task(self, claim_data):
    ...
    from workers.claims.adjudicate_claim_task import adjudicate_claim_task
    adjudicate_claim_task.delay(result)
```

This is intentional. If the tasks imported each other at the top of the file, Python would hit a circular import error — validate imports adjudicate, adjudicate imports notify, and they all load at startup in a loop. Importing inside the function means the import only happens at the moment the function runs, by which point all modules are already loaded.

---

## Base task configuration — `workers/core/base_task.py`

Every task in this project inherits from `TaskBase`. This class sets all resilience defaults in one place:

| Setting | Value | What it does |
|---|---|---|
| `autoretry_for` | `(RetryableError,)` | Only retry on temporary infrastructure errors — never on business rule failures |
| `max_retries` | `5` | Maximum 6 total attempts (1 original + 5 retries) |
| `retry_backoff` | `30` | First retry waits 30 seconds |
| `retry_backoff_max` | `300` | Retries never wait more than 5 minutes |
| `retry_jitter` | `True` | Small random variation — prevents synchronized retry storms |
| `acks_late` | `True` | Message stays in RabbitMQ until task succeeds — crash-safe |
| `reject_on_worker_lost` | `True` | If worker dies mid-task, message is re-queued, not lost |

`on_failure` is called automatically by Celery when all retries are exhausted. It saves to `failed_tasks` and sends the alert email.

---

## The status progression in PostgreSQL

As the claim moves through the pipeline, its status in the database changes:

| Stage | Status in PostgreSQL | Set by |
|---|---|---|
| API saves the claim | `PENDING` | `ClaimRepository.save_claim` |
| Validate task starts | `VALIDATING` | `validate_claim_task` |
| Validate fails (business rule) | `REJECTED` | `validate_claim_task` |
| Adjudicate task starts | `ADJUDICATING` | `adjudicate_claim_task` |
| Notify task finishes | `APPROVED` / `PARTIALLY_APPROVED` / `REJECTED` | `notify_result_task` |
| Task exhausts all retries | recorded in `failed_tasks`, alert email sent | `base_task.on_failure` |

At any point you can call `GET /app/v1/claims/status/{claim_id}` and see exactly which stage the claim is at.

---

## Monitoring

### RabbitMQ Dashboard
Open `http://localhost:15672` (login: guest / guest).

Shows every queue, how many messages are waiting, how many are being processed, and how many consumers are connected. If a queue is growing and not shrinking, your worker is not keeping up or has crashed. If the `dead_letter` queue has messages, something in your pipeline is failing — investigate immediately.

### Flower
Run `make flower` then open `http://localhost:5555`.

Shows every task that has run — success, failure, how long it took, what arguments it received. Best tool for debugging why a specific claim did not process correctly.

### Admin API
`GET /app/v1/admin/failed-tasks` — lists every claim that died with the error message, retry count, and live current claim status. The starting point for any incident investigation.

### failed_tasks table
Direct query for a quick overview:
```sql
SELECT task_name, claim_id, error, attempts, failed_at, replayed_at
FROM failed_tasks
ORDER BY failed_at DESC;
```

`replayed_at IS NULL` means unresolved. `replayed_at IS NOT NULL` means a replay was attempted — check `claim_status` in the admin API to confirm it succeeded.
