# Async Claims Worker Demo
## Architecture & System Overview

---

## What This System Does

This system processes insurance claims asynchronously. When a hospital billing clerk submits a claim, the system acknowledges it immediately and then processes it in the background — validating eligibility, adjudicating the amounts, and recording the final decision — without making the user wait.

This mirrors how real enterprise insurance platforms work in production.

---

## The Problem It Solves

In a naive system, when a clerk submits a claim the server would:
1. Check if the member is eligible
2. Calculate approved amounts
3. Apply benefit rules
4. Record everything
5. **Then** respond to the user

This could take seconds or minutes. The user is blocked waiting.

In this system the server responds in milliseconds. The heavy work happens in the background, in parallel, without blocking anyone.

---

## The Two Processes

The system runs as two completely separate processes that communicate through a message broker.

### Process 1 — The API
Receives HTTP requests from the frontend or billing system. Its only jobs are:
- Accept the claim
- Validate the shape of the data
- Save the claim to the database with status `PENDING`
- Drop a message into RabbitMQ
- Immediately return a response to the caller

The API never waits for the claim to be processed. It hands off responsibility and moves on.

### Process 2 — The Worker
Runs continuously in the background, listening for messages from RabbitMQ. When a message arrives it processes the claim through three stages in sequence.

---

## The Three-Stage Pipeline

Every claim goes through three workers in order. Each worker does one job, then triggers the next.

```
┌─────────────────────────────────────────────────────────────────┐
│                        STAGE 1                                   │
│                    validate_claim                                 │
│                                                                   │
│  • Is the member active in the system?                           │
│  • Is the hospital a registered service provider?                │
│  • If either check fails → reject the claim immediately          │
│  • If both pass → trigger Stage 2                                │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                        STAGE 2                                   │
│                   adjudicate_claim                               │
│                                                                   │
│  • Calculate the total from all line items                       │
│    (quantity × unit_price per item, summed)                      │
│  • Apply any benefit rules or limits                             │
│  • Record the approved amount                                    │
│  • Set the adjudication result (APPROVED / REJECTED)             │
│  • Trigger Stage 3                                               │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                        STAGE 3                                   │
│                    notify_result                                  │
│                                                                   │
│  • Record the final status in the database                       │
│  • Log the decision (member, provider, amount, result)           │
│  • Future: send email / push notification / STOMP message        │
└─────────────────────────────────────────────────────────────────┘
```

---

## How the Components Talk to Each Other

```
                    ┌──────────────────┐
                    │  Billing Clerk   │
                    │  (HTTP Client)   │
                    └────────┬─────────┘
                             │
                    POST /app/v1/claims/submit
                             │
                             ▼
              ┌──────────────────────────┐
              │        FastAPI           │
              │          API             │
              │                          │
              │  1. Validate JSON        │
              │  2. Save to PostgreSQL   │
              │  3. Publish to RabbitMQ  │
              │  4. Return 200 OK        │
              └──────┬─────────┬─────────┘
                     │         │
              Save claim     Publish message
                     │         │
                     ▼         ▼
              ┌──────────┐  ┌──────────────────────┐
              │PostgreSQL│  │       RabbitMQ        │
              │  (Neon)  │  │   Message Broker      │
              │          │  │                       │
              │ claims   │  │  queue: validate      │
              │ members  │  │  queue: adjudicate    │
              │providers │  │  queue: notify        │
              └──────────┘  └──────────┬────────────┘
                                       │
                                       │ Worker picks up message
                                       ▼
                        ┌──────────────────────────┐
                        │      Celery Worker        │
                        │                           │
                        │  validate_claim_task      │
                        │         ↓                 │
                        │  adjudicate_claim_task    │
                        │         ↓                 │
                        │  notify_result_task       │
                        │                           │
                        │  Reads/writes PostgreSQL  │
                        │  Results stored in Redis  │
                        └──────────────────────────┘
```

---

## The Infrastructure

| Component | Technology | Purpose | Where it runs |
|---|---|---|---|
| API | FastAPI (Python) | Receives HTTP requests | Local / server |
| Worker | Celery (Python) | Processes claims in background | Local / server |
| Message Broker | RabbitMQ | Passes messages between API and Worker | Docker |
| Primary Database | PostgreSQL (Neon) | Stores all data persistently | Cloud |
| Result Backend | Redis (Upstash) | Stores Celery task results and state | Cloud |

---

## The Data

### What a Claim Looks Like

When a billing clerk submits a claim they send the member's insurance number, the hospital code, and a list of items that were provided during the visit.

```json
{
  "member_number": "1524100",
  "provider_code": "METROPOLITAN-01",
  "items": [
    { "code": "ST10920", "name": "MRI Brain",     "quantity": 1,  "unit_price": 15000 },
    { "code": "DR0041",  "name": "Panadol 500mg", "quantity": 10, "unit_price": 50    }
  ]
}
```

### What Happens to It

```
Submitted    →  status: PENDING        approved_amount: null
After Stage 1 →  status: VALIDATING
After Stage 2 →  status: APPROVED      approved_amount: 15500
After Stage 3 →  status: APPROVED      result logged
```

### The Four Database Tables

| Table | What it stores |
|---|---|
| `members` | Insured people — their number, name, policy, active status |
| `service_providers` | Registered hospitals and clinics |
| `claims` | Every submitted claim and its current status |
| `claim_items` | Each individual line item inside a claim |

---

## Retry and Failure Handling

The worker is not naive. If something goes wrong it does not give up immediately.

- **Automatic retry** — if a worker fails it retries up to 5 times with exponential backoff (waits longer between each retry)
- **Jitter** — a small random delay is added to retries so multiple failing tasks do not all retry at the same instant
- **Late acknowledgement** — a message is only removed from RabbitMQ after the worker successfully completes it. If the worker crashes mid-processing the message goes back to the queue
- **Dead letter** — after 5 failed retries the task is rejected permanently and not requeued

---

## Why This Architecture

### Separation of concerns
Every component does exactly one thing. The API does not process claims. The worker does not serve HTTP. The database does not make decisions.

### Scalability
Because the API and the worker are separate processes, you can scale them independently. If claims are backing up you spin up more workers. If the API is getting high traffic you scale the API. Neither affects the other.

### Resilience
If the worker crashes, the messages stay in RabbitMQ. When the worker comes back up it picks up exactly where it left off. No claims are lost.

### Observability
Every task that passes through Celery is visible in the Flower dashboard. You can see which claims are queued, processing, succeeded, or failed — in real time.

---

## The Journey of One Claim

```
10:00:00.000  Billing clerk POSTs the claim
10:00:00.012  API saves claim to DB  (status: PENDING)
10:00:00.015  API publishes message to RabbitMQ
10:00:00.016  API returns 200 OK to billing clerk  ← clerk is done

              (meanwhile, in the background...)

10:00:00.050  validate_claim picks up the message
10:00:00.060  Queries DB — member 1524100 is ACTIVE ✓
10:00:00.065  Queries DB — METROPOLITAN-01 is registered ✓
10:00:00.070  Triggers adjudicate_claim

10:00:00.080  adjudicate_claim picks up
10:00:00.081  Calculates: (1 × 15000) + (10 × 50) = 15500
10:00:00.082  Sets approved_amount: 15500, result: APPROVED
10:00:00.083  Triggers notify_result

10:00:00.090  notify_result picks up
10:00:00.091  Updates claim status in DB to APPROVED
10:00:00.092  Logs: "Member: 1524100 | APPROVED | Amount: 15500"

10:00:00.093  Done. Total background processing time: ~80ms
```

The billing clerk received their response at `10:00:00.016`. The entire processing pipeline completed by `10:00:00.093`. They never waited for any of it.

---

## How This Relates to Production Systems

This project is a miniature version of how enterprise insurance platforms like Eden Care's Claim Adjudication System (CAS) work in production.

| This project | Production CAS |
|---|---|
| 1 claim type | Multiple claim types (outpatient, inpatient, optical, dental) |
| 3 worker stages | 70+ worker tasks across rules, scoring, decisioning, notifications |
| Simple eligibility check | Full benefit plan evaluation, preauth rules, waiting periods |
| Single database | Five logically separated databases (insurance, medical, master, claims, identity) |
| Basic approved amount | Full adjudication with benefit limits, exclusions, co-payments |

The patterns are identical. The scale is different.
