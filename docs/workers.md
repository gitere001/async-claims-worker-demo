# How the Workers Work

This document explains exactly what happens after a claim is submitted — who is involved, what each piece does, and why it is built this way.

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
2. Fetches the claim from PostgreSQL and sets status to `VALIDATING`.
3. Looks up the member. If the member does not exist or is not `ACTIVE`, sets status to `REJECTED`, writes the reason, and stops. The pipeline ends here.
4. Looks up the provider. If the provider is not registered, sets status to `REJECTED` and stops.
5. If both checks pass, adds `validation_passed: True` and `member_product_code` to the dict.
6. Calls `adjudicate_claim_task.delay(result)` — drops the updated dict into the `adjudicate_claim` queue.

**What it passes on:** The same dict it received, with two new fields added — `validation_passed` and `member_product_code`.

---

### Stage 2 — `workers/claims/adjudicate_claim_task.py`

**Queue:** `adjudicate_claim`

**What triggers it:** `validate_claim_task` calls `adjudicate_claim_task.delay(result)` at the end of Stage 1.

**What it does:**

1. `asyncio.run(_adjudicate(claim_data))` — same async bridge.
2. Loads the claim and all its `ClaimItem` rows from PostgreSQL.
3. Sets status to `ADJUDICATING`.
4. Groups all items by `benefit_code` and sums the amounts. For example if a claim has two OUTPATIENT items worth 2000 and 1500, they become `{"OUTPATIENT": 3500}`.
5. For each benefit code, queries `MemberBenefitBalance` to check:
   - Does this member have this benefit in their plan?
   - Is the remaining balance enough to cover the amount?
6. For every benefit that passes both checks, deducts the amount from `used_amount`, reduces `remaining_amount`, and adds to `approved_amount`.
7. For every benefit that fails, records the reason in `rejected_items`.
8. Sets the final adjudication result:
   - All benefits approved → `APPROVED`
   - Some approved, some rejected → `PARTIALLY_APPROVED`
   - Nothing approved → `REJECTED`
9. Writes `approved_amount` and `adjudication_result` to the claim row and commits.
10. Calls `notify_result_task.delay(result)`.

**What it passes on:** The same dict with two new fields — `approved_amount` and `adjudication_result`.

---

### Stage 3 — `workers/claims/notify_result_task.py`

**Queue:** `notify_result`

**What triggers it:** `adjudicate_claim_task` calls `notify_result_task.delay(result)` at the end of Stage 2.

**What it does:**

1. `asyncio.run(_notify(claim_data))` — same async bridge.
2. Loads the claim from PostgreSQL.
3. Sets the final status on the claim row — `APPROVED`, `PARTIALLY_APPROVED`, or `REJECTED`.
4. Commits.
5. Logs the full summary to the console:

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

## Production safety — Dead Letter Queue (DLQ)

### The problem without DLQ

Before DLQ was added, if a task failed all its retries the message simply disappeared. No record of what failed, no way to replay it, no notification. A claim could silently vanish from the pipeline with no trace.

### How the DLQ works

Every pipeline queue (`validate_claim`, `adjudicate_claim`, `notify_result`) is configured with a **dead letter exchange (DLX)**. This is an instruction to RabbitMQ at the infrastructure level:

> "If a message in this queue is rejected after all retries, do not drop it — route it to the `dead_letter` queue instead."

This happens automatically inside RabbitMQ, before any Python code runs. Even if the worker process crashes, the routing still happens.

### The three safety nets

**Safety net 1 — RabbitMQ `dead_letter` queue**

The message lands here and stays until you deal with it. Nothing is lost. You can see it in the RabbitMQ dashboard at `http://localhost:15672`.

**Safety net 2 — `failed_tasks` table in PostgreSQL**

Every time a task exhausts all its retries, a row is written to the `failed_tasks` table. This is a permanent, queryable record in your database of every claim that died and exactly why.

**Safety net 3 — Email alert via Resend**

Immediately after saving to `failed_tasks`, an HTML alert email is sent to the configured address. The email shows the task name, claim id, exact error message, number of attempts, and a timestamp. You know about the failure the moment it happens — you do not have to go and query the database to find out something went wrong.

---

### How the failed_tasks save actually works — step by step

This all happens inside `workers/core/base_task.py` in the `on_failure` method.

**What is `on_failure`?**

Celery calls `on_failure` automatically on every task that has inherited from `TaskBase` — which is every task in this project. You never call it yourself. When a task throws an exception and has no retries left, Celery calls `on_failure` before the message moves to the dead letter queue.

**Step 1 — Extract the payload and claim id**

```python
payload = args[0] if args else {}
claim_id = payload.get("id") if isinstance(payload, dict) else None
```

`args` is a tuple of the arguments the task was called with. Every task in this project receives one argument — the claim dict. So `args[0]` is that dict. From it we pull the `id` field which is the claim UUID. If for any reason the payload is not a dict or is empty, `claim_id` is just `None` — the save still happens, just without a claim id.

**Step 2 — Log the failure immediately**

```python
logger.error(
    "TASK DEAD | task=%s | task_id=%s | claim_id=%s | error=%s",
    self.name, task_id, claim_id, exc,
)
```

This logs to the worker terminal right away. Even if the database save fails in the next step, this line means the failure is always visible in the worker logs.

**Step 3 — Define the async save function**

```python
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
```

This is an inner async function defined inside `on_failure`. It uses `WorkerSessionLocal` — the NullPool engine — because `on_failure` runs inside the worker process where each operation needs a fresh database connection.

The imports (`FailedTask`, `WorkerSessionLocal`) are inside the function for the same reason as the task chain imports — to avoid circular imports at module load time.

Each field being saved:

| Field | Where the value comes from |
|---|---|
| `task_id` | Celery's unique ID for this specific task execution — passed in by Celery automatically |
| `task_name` | `self.name` — the registered name of the task e.g. `validate_claim_task` |
| `claim_id` | Extracted from `payload["id"]` in Step 1 |
| `error` | `str(exc)` — the full exception message |
| `payload` | The entire dict the task received — so you have everything needed to replay it |
| `attempts` | `self.request.retries + 1` — how many times it was tried. `retries` is zero-indexed so we add 1 |

`failed_at` is not set here — the model sets it automatically via `default=lambda: datetime.now(timezone.utc)`.

**Step 4 — Run the async function from synchronous code**

```python
try:
    asyncio.run(_save_failure())
except Exception as save_exc:
    logger.error("FAILED to save dead task to DB | %s", save_exc)
```

`on_failure` is a regular synchronous method — Celery calls it synchronously. But `_save_failure` uses `await` because SQLAlchemy async requires it. So `asyncio.run()` creates a fresh event loop, runs `_save_failure` to completion, and destroys the loop. This is the same pattern used in all the worker tasks.

The whole thing is wrapped in a `try/except`. If the database is also down at the moment of failure — the worst possible scenario — the save fails silently but the error is logged. The message is still in the RabbitMQ dead letter queue so nothing is truly lost. The database failure does not cause `on_failure` itself to crash.

**Step 5 — Send the alert email**

```python
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
```

This runs in its own separate `try/except`. The email step never blocks or breaks the DB save, and the DB save never blocks or breaks the email. Each step is independent — if one fails the other still runs.

`task_failed.render()` lives in `core/notifications/templates/task_failed.py` and returns the subject line and the full styled HTML. `send_email()` in `core/notifications/email_service.py` calls the Resend API. The template is kept separate from the sending function so that adding new email templates in the future only requires creating a new file in `core/notifications/templates/` — nothing else changes.

### The dead letter task handler — `workers/core/dead_letter_task.py`

This task listens on the `dead_letter` queue. When a message arrives it logs a full alert:

```
============================================================
  DEAD LETTER MESSAGE RECEIVED
  Claim ID     : 1c29e729-...
  Member       : 1524100
  Full payload : {...}
  Action       : inspect failed_tasks table to investigate
============================================================
```

This task lives in `workers/core/` — not inside any specific domain — because the dead letter queue catches failures from any worker in the system, not just claims.

### The full failure flow

```
validate_claim_task fails
        │
        retry 1 → retry 2 → retry 3 → retry 4 → retry 5
                                                     │
                                             max retries reached
                                                     │
                                             on_failure fires
                                                     │
                    ┌────────────────────────────────┼──────────────────────────┐
                    │                                │                          │
                    ▼                                ▼                          ▼
          dead_letter queue            failed_tasks row in PostgreSQL    alert email sent
          (message safe                (task_name, claim_id, error,      to configured
           in RabbitMQ)                 payload, attempts, failed_at)    address via Resend
                    │
                    ▼
          dead_letter_task runs
          logs the alert
```

### How to investigate and replay a failed claim

1. Query the `failed_tasks` table to find the failed claim
2. Read the `error` and `payload` columns to understand what went wrong
3. Fix the bug or data issue
4. Take the `payload` from the `failed_tasks` row and re-submit it by calling `validate_claim_task.delay(payload)` directly

---

## Why asyncio.run() in every worker

Celery tasks are regular synchronous Python functions. But all the database code in this project uses async SQLAlchemy — it uses `await` everywhere.

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

## What happens when a task fails — retry logic

The base task class in `workers/core/base_task.py` handles all failures:

- `max_retries = 5` — tries up to 5 times before giving up
- `retry_backoff = True` — waits longer between each retry (exponential backoff)
- `retry_jitter = True` — adds a small random delay to avoid all retries hitting the DB at the same moment
- `acks_late = True` — the message is NOT removed from RabbitMQ until the task completes successfully. If the worker crashes mid-task, the message stays in RabbitMQ and will be picked up again when the worker restarts
- `reject_on_worker_lost = True` — if the worker process dies unexpectedly, the message is rejected and re-queued rather than silently lost

---

## The status progression in PostgreSQL

As the claim moves through the pipeline, its status in the database changes:

| Stage | Status in PostgreSQL | Set by |
|---|---|---|
| API saves the claim | `PENDING` | `ClaimRepository.save_claim` |
| Validate task starts | `VALIDATING` | `validate_claim_task` |
| Validate fails | `REJECTED` | `validate_claim_task` |
| Adjudicate task starts | `ADJUDICATING` | `adjudicate_claim_task` |
| Notify task finishes | `APPROVED` / `PARTIALLY_APPROVED` / `REJECTED` | `notify_result_task` |
| Task exhausts all retries | recorded in `failed_tasks`, alert email sent | `base_task.on_failure` |

At any point you can call `GET /app/v1/claims/status/{claim_id}` and see exactly which stage the claim is at.

---

## Monitoring

### RabbitMQ Dashboard
Open `http://localhost:15672` in your browser (login: guest / guest).

Shows every queue, how many messages are waiting, how many are being processed, and how many consumers are connected. If a queue is growing and not shrinking, your worker is not keeping up or has crashed. If the `dead_letter` queue has messages, something in your pipeline is failing — investigate immediately.

### Flower
Run `make flower` then open `http://localhost:5555`.

Shows every task that has run — success, failure, how long it took, what arguments it received. This is the best tool for debugging why a specific claim did not process correctly.

### failed_tasks table
Query directly in PostgreSQL to see every message that died:

```sql
SELECT task_name, claim_id, error, attempts, failed_at
FROM failed_tasks
ORDER BY failed_at DESC;
```
