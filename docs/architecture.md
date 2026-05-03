# Architecture

This document explains how the project is structured, what each layer does, and why the decisions were made this way.

---

## The big picture

When a claim is submitted:

1. The API receives the request, saves the claim, and immediately responds — under one second
2. The claim data is dropped into RabbitMQ
3. Three background workers process it in sequence: validate → adjudicate → notify
4. The claim status is updated in PostgreSQL at each stage

The user gets a fast response. The complex work happens in the background.

---

## Folder structure

```
async-claims-worker-demo/
│
├── domains/              ← Everything owned by a specific domain
├── repositories/         ← Shared data layer (database models + queries)
├── workers/              ← Celery background tasks
├── core/                 ← Shared infrastructure (database engine, session, notifications)
├── config/               ← App configuration and middleware registration
├── middleware/           ← Request logging and CORS
├── migrations/           ← Alembic database migrations
├── main.py               ← FastAPI entry point
├── worker.py             ← Celery app and queue definitions
└── seed.py               ← Database seeder
```

---

## The layers explained

### domains/

Each domain is a fully independent FastAPI sub-app. Today there are two: `claims` and `health`.

Every domain owns everything it needs internally:

```
domains/claims/
├── app.py                  ← Independent FastAPI app, mounted at /app/v1/claims
├── container.py            ← Lagom DI container — maps interfaces to implementations
├── routers/                ← Receives HTTP requests, calls the controller
├── controllers/            ← Resolves dependencies from container, delegates to service
├── services/               ← Coordinates the workflow
│   └── interfaces/         ← IClaimService interface (contract)
├── proxies/                ← Sits between service and repository
└── models/                 ← Pydantic request and response models
```

Adding a new domain means creating a new folder here and mounting it in `main.py`. Nothing else changes.

---

### repositories/

The shared data layer. Lives outside domains because multiple parts of the system use it — the claims workers need to read member data, benefit data, and provider data. These do not belong to any single domain.

```
repositories/
├── claims/
│   ├── claim_repository.py     ← save_claim, get_claim, update_claim_status
│   ├── contracts/              ← IClaimRepository interface
│   └── database/               ← Claim + ClaimItem SQLAlchemy models
├── members/database/           ← Member model
├── providers/database/         ← ServiceProvider model
├── benefits/database/          ← BenefitType, Product, ProductBenefit, MemberBenefitBalance
└── health/                     ← Health check logic
```

Only repositories talk to the database. No other layer runs SQL queries directly.

---

### core/

Shared infrastructure used by both the API and the workers. Does not belong to any domain.

```
core/
├── database/
│   └── db_context.py       ← Two SQLAlchemy engines (API pool + worker NullPool)
└── notifications/
    ├── email_service.py    ← Calls Resend API to send an email
    └── templates/
        └── task_failed.py  ← Renders the subject + HTML for a task failure alert
```

The notifications folder follows a template pattern — `email_service.py` only knows how to send, it never builds HTML. Each template is its own file in `templates/`. Adding a new email type means adding one new template file and calling `send_email()` with the result. Nothing else changes.

---

### The request journey through the layers

Every HTTP request flows through exactly these layers in order:

```
Router → Controller → Service → Proxy → Repository → PostgreSQL
```

**Router** — matches the URL and HTTP method, parses the request body into a Pydantic model, calls the controller. Zero logic.

**Controller** — asks the DI container to resolve the service, calls the service method, returns the result. Zero logic.

**Service** — the only layer that makes decisions. Calls the repository to save data, fires the Celery task into RabbitMQ, builds and returns the response.

**Proxy** — sits between service and repository. Today it delegates every call straight through. In future it is the right place to add logging, metrics, or caching without touching the repository.

**Repository** — owns the database. All SQLAlchemy queries and writes happen here and nowhere else.

---

## Dependency injection (Lagom)

Dependencies are wired once in `domains/claims/container.py`:

```
IClaimRepository  →  ClaimServiceProxy
IClaimService     →  ClaimService
```

When a request arrives, the controller asks the container for an `IClaimService`. Lagom reads the type hints on `ClaimService.__init__`, sees it needs an `IClaimRepository`, looks that up, builds `ClaimServiceProxy`, injects it into `ClaimService`, and gives the controller a fully wired object.

No manual construction anywhere. Swapping an implementation means changing one line in `container.py`.

---

## Sub-app mounting

Each domain is mounted as an independent FastAPI app:

```
main.py mounts:
  /app/v1/claims  →  domains/claims/app.py
  /app/v1/health  →  domains/health/app.py
```

Each domain gets its own Swagger docs page:
- `http://localhost:8000/app/v1/claims/docs`
- `http://localhost:8000/app/v1/health/docs`

---

## Two database engines

There are two SQLAlchemy engines defined in `core/database/db_context.py`:

**API engine** — uses a connection pool. FastAPI runs in a single event loop permanently, so keeping connections warm is safe and fast. The startup warmup event (`SELECT 1`) pre-warms this pool so the first request is not slow.

**Worker engine** — uses `NullPool` (no pooling). Each Celery task calls `asyncio.run()` which creates a brand new event loop. A pooled connection from a previous loop cannot be used in the new one — it raises `Future attached to a different loop`. NullPool means each task gets a fresh connection and closes it when done.

---

## Contracts (interfaces)

Every repository and service has an abstract base class (ABC) interface:

- `IClaimRepository` — defines `save_claim`, `get_claim`, `update_claim_status`
- `IClaimService` — defines `submit_claim`, `get_claim_status`

No layer depends on a concrete class. The controller depends on `IClaimService`. The service depends on `IClaimRepository`. This means:

- Any class that implements the interface can be swapped in without changing anything else
- Tests can use a mock implementation
- The proxy works because it also implements the interface

---

## Middleware

Two middleware functions are registered centrally in `config/app_routers.py` and applied to the main app:

**Request logging** — logs every request with method, path, status code, and duration in milliseconds.

**CORS** — sets the required headers so browser clients can call the API.

Both are registered in one place. Adding new middleware means one line in `config/app_routers.py`.

---

## The worker pipeline

Three Celery tasks run in sequence after a claim is submitted:

```
validate_claim_task  →  adjudicate_claim_task  →  notify_result_task
     (queue 1)               (queue 2)                (queue 3)
```

Each task fires the next one when it finishes. If a task fails validation or adjudication, the pipeline stops and the claim is marked `REJECTED`. The next task is never fired.

See `docs/workers.md` for the full detailed explanation.

---

## Status progression

The claim status in PostgreSQL tracks exactly where in the pipeline the claim is:

```
PENDING → VALIDATING → ADJUDICATING → APPROVED
                    ↘               ↘ PARTIALLY_APPROVED
                     REJECTED        REJECTED
```

`GET /app/v1/claims/status/{claim_id}` reads this status so you can poll to see progress.

---

## Infrastructure

| Service | Purpose | How to start |
|---|---|---|
| PostgreSQL (Neon) | Permanent data storage | Cloud — always running |
| RabbitMQ | Message queue between API and workers | `make up` (Docker) |
| Redis (Upstash) | Celery result backend | Cloud — always running |
| Flower | Worker monitoring UI | `make flower` |
