# Async Claims Worker Demo

A production-style insurance claims processing system built to learn and demonstrate Celery + RabbitMQ async task pipelines.

---

## What This Project Does

When a claim is submitted via the API, it is immediately saved and queued — the API returns in under a second. Three Celery workers then process the claim in sequence across separate RabbitMQ queues:

1. **validate_claim** — Is the member active? Is the provider registered?
2. **adjudicate_claim** — Do benefit balances cover the claim items?
3. **notify_result** — Write the final status to the database and log the outcome.

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
| DI Container | Lagom |
| Monitoring | Flower |

---

## Architecture

The project is organised in strict layers. Each layer has one responsibility and only talks to the layer below it.

```
domains/          ← Everything owned by a domain: routers, controllers, services, proxies, models
repositories/     ← Shared data layer: SQLAlchemy models and all database read/write operations
workers/          ← Celery tasks
core/             ← Shared: database engines, session factories, Base model
config/           ← App configuration, router registration, and settings
middleware/       ← Request logging and CORS
```

### Layer responsibilities

**Router** — receives the HTTP request, calls the controller, returns the response. No logic.

**Controller** — resolves its dependencies from the DI container and delegates to the Service. No logic.

**Service** — coordinates the workflow. Calls the Repository to persist data, then fires the next step into RabbitMQ.

**Proxy** — sits between Service and Repository. Delegates everything today, but is the right place to add logging, metrics, or caching later without touching the repository itself.

**Repository** — owns the database. All SQLAlchemy queries and writes happen here.

**Workers** — Celery tasks. Each task reads from and writes to the database via repositories, then fires the next task in the chain.

### Sub-app mounting

Each domain is a completely independent FastAPI app mounted under the main app. This gives every domain its own Swagger docs page and keeps `main.py` clean regardless of how many domains are added.

### Dependency injection (Lagom)

Dependencies are wired once in `domains/claims/container.py`. The container maps each interface to its implementation and resolves the full dependency tree automatically at request time. No manual wiring in routers.

### Central middleware

All middleware is registered in `config/app_routers.py`. One place to look, one place to add new middleware — never scattered across domain files.

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
│   ├── app_config.py                # Pydantic config per sub-app (title, version, servers)
│   ├── app_routers.py               # Router loaders + middleware registration
│   ├── app_settings.py              # Reads .env into a dict
│   └── configuration.py            # Pydantic BaseSettings typed object
│
├── core/
│   └── database/
│       └── db_context.py           # Two engines (pooled + NullPool), session factories, Base
│
├── middleware/
│   ├── request_logging.py          # Logs method, path, status, and duration for every request
│   └── cors_middleware.py          # Sets CORS headers on every response
│
├── domains/
│   ├── claims/
│   │   ├── app.py                  # Claims FastAPI sub-app
│   │   ├── container.py            # Lagom DI container — interface-to-implementation wiring
│   │   ├── routers/                # HTTP route definitions
│   │   ├── controllers/            # Thin delegation layer, resolves from container
│   │   ├── services/               # Workflow coordination
│   │   │   └── interfaces/         # IClaimService interface (ABC)
│   │   ├── proxies/
│   │   │   └── claim_service_proxy.py  # Proxy wrapping ClaimRepository
│   │   └── models/                 # Pydantic request/response models
│   └── health/
│       ├── app.py                  # Health FastAPI sub-app
│       ├── proxies/
│       │   └── health_service_proxy.py # Proxy wrapping HealthService
│       └── routers/
│           └── health_router.py    # GET /health — checks DB, RabbitMQ, and Redis
│
├── repositories/
│   ├── claims/
│   │   ├── claim_repository.py     # save_claim, get_claim, update_claim_status
│   │   ├── contracts/              # IClaimRepository interface (ABC)
│   │   └── database/               # Claim + ClaimItem SQLAlchemy models
│   ├── health/
│   │   ├── health_service.py       # Runs all three checks concurrently, returns 200 or 503
│   │   ├── contracts/              # IHealthService interface (ABC)
│   │   └── helpers/
│   │       └── health_check.py     # check_database, check_rabbitmq, check_redis
│   ├── members/
│   │   └── database/               # Member model
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
| provider_code | VARCHAR | The hospital or clinic |
| status | ENUM | PENDING → VALIDATING → ADJUDICATING → APPROVED / REJECTED |
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

The seed script (`seed.py`) populates the database with realistic test data. It is idempotent — safe to run multiple times.

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

## API Endpoints

### Submit a claim

`POST /app/v1/claims/submit`

Payload requires a `member_number`, a `provider_code`, and a list of items. Each item needs a `code`, `name`, `benefit_code`, `quantity`, and `unit_price`. Returns immediately with `status: PENDING` and a `claim_id` to poll with.

### Check claim status

`GET /app/v1/claims/status/{claim_id}`

Returns the current status, approved amount, and adjudication result. Poll this after submitting to see the claim move through the pipeline.

### Health check

`GET /app/v1/health`

Returns `200 OK` with a breakdown of database, RabbitMQ, and Redis status. Returns `503 Service Unavailable` if any dependency is down.

### Swagger UI

Each domain has its own Swagger docs page:

- Claims — `http://localhost:8000/app/v1/claims/docs`
- Health — `http://localhost:8000/app/v1/health/docs`

---

## Test Scenarios

**Happy path — APPROVED**
Use member `1524100` (James, PREMIUM) or `1524101` (Sarah, ENHANCED) with any registered provider. Keep amounts within benefit limits.

**Inactive member — REJECTED at validation**
Use member `1524102` (Peter, INACTIVE). The validate task rejects immediately without reaching adjudication.

**Benefit not covered — REJECTED at adjudication**
Use `benefit_code: DENTAL` with member `1524100` (BASIC plan has no dental). The adjudicate task finds no balance and rejects.

**Partially approved — PARTIALLY_APPROVED**
Mix one covered benefit and one uncovered benefit in the same claim. The adjudicate task approves the covered portion and rejects the rest.

**Insufficient balance — REJECTED at adjudication**
Submit an amount exceeding the member's remaining benefit balance.

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

## Monitoring

**RabbitMQ Dashboard** — `http://localhost:15672` (login: guest / guest)
Shows queues, message rates, consumers, and unacknowledged messages.

**Flower** — run `make flower`, then open `http://localhost:5555`
Shows task history, worker status, success/failure rates, and task arguments.

---

## Key Design Decisions

**Why NullPool on the worker engine?**
Celery tasks use `asyncio.run()` to bridge sync task execution with async database code. Each call creates a new event loop. A pooled connection binds to the previous loop and raises `Future attached to a different loop`. NullPool disables pooling so every task gets a fresh connection.

**Why three separate queues?**
Each pipeline stage runs on a dedicated queue. This allows independent scaling — more adjudication workers can be added during peak hours without affecting the validation queue.

**Why a Proxy layer?**
The proxy sits between the Service and the Repository. It delegates everything today but is the right place to add structured logging, metrics, or circuit breakers later without modifying the repository.

**Why contracts (interfaces)?**
All repositories and services implement an ABC interface. This enforces what methods must exist and makes every layer testable with a mock implementation. Each layer depends on the interface, not the concrete class.

**Why a DI container?**
The container maps interfaces to implementations in one place. Swapping an implementation — for testing or refactoring — requires changing one line in `container.py`, nothing else.

**Why sub-app mounting?**
Each domain is a fully independent FastAPI app. Every domain gets its own Swagger docs page and adding a new domain never requires touching existing domain files.

---

## Learning Outcomes

- Celery + RabbitMQ — task queues, named queues, task routing, result backends
- Async SQLAlchemy — async engine, sessions, NullPool, context managers
- Alembic async migrations — autogenerate, async env setup
- Domain-Driven Design — domains, services, repositories, proxies, contracts
- Dependency injection — Lagom container, interface-to-implementation mapping
- FastAPI — routers, dependency injection via `Depends`, Pydantic models, sub-app mounting
- Event-driven architecture — decoupled pipeline where each stage only knows the next
- Idempotent seeding — safe to run `make seed` multiple times
- Health checks — real connection tests against all three infrastructure dependencies
