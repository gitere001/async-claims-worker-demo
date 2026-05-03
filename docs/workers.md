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

## The four queues

The worker listens on four queues simultaneously. These are defined in `worker.py`:

| Queue | Purpose |
|---|---|
| `default` | General fallback queue |
| `validate_claim` | Stage 1 — member and provider checks |
| `adjudicate_claim` | Stage 2 — benefit balance checks and deductions |
| `notify_result` | Stage 3 — final status write and logging |

Each stage of the pipeline has its own dedicated queue. This means in production you could run more workers listening only on `adjudicate_claim` during peak hours without affecting the other stages.

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
   - Does this member have this benefit in their plan? (e.g. does a BASIC plan member have DENTAL coverage?)
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
```
{
  "id": "1c29e729-...",
  "member_number": "1524100",
  "provider_code": "METROPOLITAN-01",
  "status": "PENDING",
  "items": [...]
}
```

After validate_claim_task:
```
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
```
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

## What happens when a task fails

The base task class in `workers/core/base_task.py` handles failures. If a task throws an exception it will be retried automatically with exponential backoff — it waits longer between each retry. After the maximum number of retries it gives up and logs the failure.

`acks_late=True` means the message is not removed from RabbitMQ until the task completes successfully. If the worker crashes mid-task, the message stays in RabbitMQ and will be picked up again when the worker restarts. No messages are lost.

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

At any point you can call `GET /app/v1/claims/status/{claim_id}` and see exactly which stage the claim is at.

---

## Monitoring the workers

### RabbitMQ Dashboard
Open `http://localhost:15672` in your browser (login: guest / guest).

Shows every queue, how many messages are waiting, how many are being processed, and how many consumers are connected. If a queue is growing and not shrinking, your worker is not keeping up or has crashed.

### Flower
Run `make flower` then open `http://localhost:5555`.

Shows every task that has run — success, failure, how long it took, what arguments it received. This is the best tool for debugging why a specific claim did not process correctly.
