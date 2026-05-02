# Async Claims Worker Demo

A production-style insurance claims processing system built to learn and demonstrate **Celery + RabbitMQ** async task pipelines. Mirrors the architecture patterns used in real-world health insurance platforms.

---

## What This Project Does

When a claim is submitted via the API, it is **immediately saved and queued** — the API returns in under a second. Three Celery workers then process the claim in sequence across separate RabbitMQ queues:

```
POST /claims/submit
        │
        ▼
   FastAPI saves claim (status=PENDING)
        │
        └──► RabbitMQ
                │
                ▼
        validate_claim_task         ← Is member ACTIVE? Is provider registered?
                │
                ▼
        adjudicate_claim_task       ← Do benefit balances cover the claim items?
                │
                ▼
        notify_result_task          ← Write final status to DB, log summary
```

The claim status moves through: `PENDING → VALIDATING → ADJUDICATING → APPROVED / PARTIALLY_APPROVED / REJECTED`

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API | FastAPI + Uvicorn |
| Task Queue | Celery 5 |
| Message Broker | RabbitMQ (Docker) |
| Result Backend | Redis (Upstash cloud) |
| Database | PostgreSQL (Neon cloud) |
| ORM | SQLAlchemy async + asyncpg |
| Migrations | Alembic |
| Config | Pydantic BaseSettings + python-dotenv |
| Monitoring | Flower |

---

## Architecture

The project follows a strict layered architecture modelled after production CAS (Claims Adjudication System) patterns:

```
domains/          ← HTTP layer: routers, controllers, app services, Pydantic models
proxies/          ← Thin proxy between AppService and Service (for future logging/caching)
services/         ← Business logic + SQLAlchemy models + DB operations
workers/          ← Celery tasks (async bridge via asyncio.run())
core/             ← Shared: database engine, session factory, Base model
config/           ← Settings loaded from .env
```

### Layer responsibilities

**Router** — receives the HTTP request, calls the controller, returns the response.

**Controller** — thin layer, delegates to AppService. No business logic here.

**AppService** — coordinates the workflow. Calls the Service to save data, then fires the Celery task into RabbitMQ.

**Proxy** — sits between AppService and Service. Delegates all calls today but is the right place to add logging, metrics, or caching later without touching the service.

**Service** — owns the database. All SQLAlchemy queries and writes happen here.

**Workers** — Celery tasks. Each task does async DB work via `asyncio.run()`, then fires the next task in the chain.

---

## Project Structure

```
async-claims-worker-demo/
│
├── main.py                          # FastAPI entry point
├── worker.py                        # Celery app + queue definitions
├── seed.py                          # Idempotent database seeder
│
├── config/
│   ├── app_settings.py              # Reads .env into a dict via dotenv
│   └── configuration.py            # Pydantic BaseSettings typed object
│
├── core/
│   └── database/
│       └── db_context.py           # Async engine (NullPool), session factory, Base, model registry
│
├── domains/
│   └── claims/
│       ├── app.py                  # FastAPI app with router included
│       ├── routers/                # HTTP route definitions
│       ├── controllers/            # Thin delegation layer
│       ├── app_services/           # Workflow coordination
│       └── models/                 # Pydantic request/response models
│
├── proxies/
│   └── claims/
│       └── claim_service_proxy.py  # Proxy wrapping ClaimService
│
├── services/
│   ├── claims/
│   │   ├── claim_service.py        # save_claim, get_claim, update_claim_status
│   │   ├── contracts/              # IClaimService interface (ABC)
│   │   └── database/               # Claim + ClaimItem SQLAlchemy models
│   ├── members/
│   │   └── database/               # Member model (member_number, status, product_code)
│   ├── providers/
│   │   └── database/               # ServiceProvider model
│   └── benefits/
│       └── database/               # BenefitType, Product, ProductBenefit, MemberBenefitBalance
│
├── workers/
│   ├── core/
│   │   └── base_task.py            # Celery TaskBase (retries, acks_late, backoff)
│   └── claims/
│       ├── validate_claim_task.py  # Stage 1: member + provider checks
│       ├── adjudicate_claim_task.py # Stage 2: balance deduction + result
│       └── notify_result_task.py   # Stage 3: final status update + logging
│
└── migrations/
    ├── env.py                      # Async Alembic config
    └── versions/                   # Migration files
```

---

## Database Schema

### claims
| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| member_number | VARCHAR | The member making the claim |
| provider_code | VARCHAR | The hospital/clinic |
| status | ENUM | PENDING → VALIDATING → ADJUDICATING → APPROVED/REJECTED |
| approved_amount | FLOAT | Total amount approved after adjudication |
| adjudication_result | VARCHAR | APPROVED / PARTIALLY_APPROVED / REJECTED |

### claim_items
Each claim has one or more line items (e.g. consultation, medication, procedure).

| Column | Type | Description |
|--------|------|-------------|
| claim_id | UUID FK | Parent claim |
| code | VARCHAR | Item code (e.g. OPD-001) |
| benefit_code | VARCHAR FK | Maps to benefit_types (OUTPATIENT, DENTAL, etc.) |
| quantity | INTEGER | |
| unit_price | FLOAT | |
| line_total | FLOAT | quantity × unit_price |

### member_benefit_balances
Tracks how much of each benefit a member has used in a policy year.

| Column | Type | Description |
|--------|------|-------------|
| member_number | VARCHAR FK | |
| benefit_code | VARCHAR FK | OUTPATIENT, INPATIENT, DENTAL, OPTICAL, PHARMACY |
| policy_year | INTEGER | e.g. 2024 |
| annual_limit | FLOAT | Maximum allowed per year |
| used_amount | FLOAT | Deducted so far |
| remaining_amount | FLOAT | annual_limit − used_amount |

---

## Seed Data

The seed script (`seed.py`) populates the database with realistic test data.

### Members

| Member Number | Name | Plan | Status |
|--------------|------|------|--------|
| 1524100 | James Gitere | PREMIUM | ACTIVE |
| 1524101 | Sarah Wanjiku | ENHANCED | ACTIVE |
| 1524102 | Peter Kamau | BASIC | INACTIVE |
| 1524103 | Grace Muthoni | PREMIUM | ACTIVE |

### Plans & Annual Limits (KES)

| Benefit | BASIC | PREMIUM | ENHANCED |
|---------|-------|---------|----------|
| OUTPATIENT | 30,000 | 80,000 | 150,000 |
| INPATIENT | 150,000 | 500,000 | 1,000,000 |
| DENTAL | — | 20,000 | 50,000 |
| OPTICAL | — | 15,000 | 30,000 |
| PHARMACY | 10,000 | 30,000 | 60,000 |

### Providers

| Code | Name |
|------|------|
| METROPOLITAN-01 | Metropolitan Hospital Nairobi |
| VETERAN-01 | Veteran's Hospital |
| NAIROBI-WEST-01 | Nairobi West Hospital |
| KENYATTA-01 | Kenyatta National Hospital |

---

## Getting Started

### Prerequisites

- Python 3.11+
- Docker Desktop (for RabbitMQ)
- A Neon PostgreSQL database
- An Upstash Redis instance

### 1. Clone and install

```bash
git clone https://github.com/jgitere-eden-care/async-claims-worker-demo.git
cd async-claims-worker-demo
make install
```

### 2. Create your `.env` file

```env
DATABASE_URL=postgresql+asyncpg://<user>:<password>@<host>/<dbname>?ssl=require
REDIS_URL=rediss://default:<password>@<host>:<port>
RABBIT_MQ_URL=amqp://guest:guest@localhost:5672//
```

### 3. Run migrations and seed

```bash
make migrate
make seed
```

### 4. Start everything (3 terminals)

**Terminal 1 — RabbitMQ**
```bash
make up
```

**Terminal 2 — FastAPI**
```bash
make api
```

**Terminal 3 — Celery Worker**
```bash
make worker
```

---

## API Usage

### Submit a claim

```
POST http://localhost:8000/app/v1/claims/submit
Content-Type: application/json
```

```json
{
  "member_number": "1524100",
  "provider_code": "METROPOLITAN-01",
  "items": [
    {
      "code": "OPD-001",
      "name": "Outpatient Consultation",
      "benefit_code": "OUTPATIENT",
      "quantity": 1,
      "unit_price": 3500.00
    },
    {
      "code": "PHARM-001",
      "name": "Prescribed Medication",
      "benefit_code": "PHARMACY",
      "quantity": 2,
      "unit_price": 750.00
    }
  ]
}
```

**Response (immediate):**
```json
{
  "claim_id": "1c29e729-bc5f-4d4c-bab3-f4c37dbc1537",
  "status": "PENDING",
  "message": "Claim received and queued for processing"
}
```

### Check claim status

```
GET http://localhost:8000/app/v1/claims/status/{claim_id}
```

**Response (after processing):**
```json
{
  "claim_id": "1c29e729-bc5f-4d4c-bab3-f4c37dbc1537",
  "status": "APPROVED",
  "approved_amount": 5000.0,
  "adjudication_result": "APPROVED"
}
```

### Swagger UI

```
http://localhost:8000/docs
```

---

## Test Scenarios

### Happy path — APPROVED
Use member `1524100` (James, PREMIUM) or `1524101` (Sarah, ENHANCED) with any registered provider. Keep amounts within the benefit limits.

### Inactive member — REJECTED at validation
Use member `1524102` (Peter, INACTIVE). The validate task will reject immediately without reaching adjudication.

### Benefit not covered — REJECTED at adjudication
Use `benefit_code: "DENTAL"` with member `1524100` (BASIC plan does not include dental). The adjudicate task will find no balance and reject.

### Partially approved — PARTIALLY_APPROVED
Mix one covered benefit and one uncovered benefit in the same claim. The adjudicate task will approve the covered portion and reject the rest.

### Insufficient balance — REJECTED at adjudication
Submit a claim amount exceeding the member's remaining benefit balance (e.g. OUTPATIENT amount > 80,000 for a PREMIUM member).

---

## Makefile Commands

| Command | Description |
|---------|-------------|
| `make install` | Create `.venv` and install dependencies |
| `make up` | Start RabbitMQ via Docker |
| `make down` | Stop RabbitMQ |
| `make api` | Start FastAPI on port 8000 |
| `make worker` | Start Celery worker (all queues) |
| `make flower` | Start Flower monitoring UI on port 5555 |
| `make migrate` | Run Alembic migrations |
| `make revision msg="..."` | Generate a new migration |
| `make seed` | Seed the database |
| `make test-config` | Verify settings load correctly |
| `make test-db` | Verify database connection |

---

## Key Design Decisions

### Why NullPool on the database engine?
Celery workers use `asyncio.run()` to bridge sync tasks with async DB code. Each call creates a new event loop. A persistent connection pool binds connections to the previous loop, causing `Future attached to a different loop` errors. `NullPool` disables pooling so each task gets a fresh connection.

### Why asyncio.run() in Celery tasks?
Celery tasks are synchronous by default. Using `asyncio.run()` inside each task lets us use async SQLAlchemy without switching to `celery[gevent]` or `celery[eventlet]`. This is the same pattern used in production CAS systems.

### Why three separate queues?
Each stage of the pipeline (validate, adjudicate, notify) runs on a dedicated queue. In production this allows independent scaling — you can run more adjudication workers during peak claim hours without affecting the validation queue.

### Why a Proxy layer?
The proxy (`ClaimServiceProxy`) sits between `ClaimAppService` and `ClaimService`. Today it delegates everything. In production it is the right place to add structured logging, performance metrics, circuit breakers, or caching without modifying the service.

### Why contracts (interfaces)?
All services implement an ABC interface (`IClaimService`). This enforces the contract — any class that claims to be a `ClaimService` must implement `save_claim`, `get_claim`, and `update_claim_status`. It also makes the proxy and app service testable with mock implementations.

---

## Monitoring

### RabbitMQ Dashboard
```
http://localhost:15672
Login: guest / guest
```
Shows queues, message rates, consumers, and unacknowledged messages.

### Flower (Celery monitoring)
```bash
make flower
# then open http://localhost:5555
```
Shows task history, worker status, success/failure rates, and task arguments.

---

## Learning Outcomes

This project demonstrates:

- **Celery + RabbitMQ** — task queues, named queues, task routing, result backends
- **Async SQLAlchemy** — async engine, sessions, NullPool, context managers
- **Alembic async migrations** — autogenerate, async env setup
- **Domain-Driven Design** — domains, services, proxies, contracts, app services
- **FastAPI** — routers, dependency injection, Pydantic models
- **Event-driven architecture** — decoupled pipeline where each stage only knows about the next
- **Idempotent seeding** — safe to run `make seed` multiple times without duplicates
