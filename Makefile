.PHONY: install up down ps api worker flower test-config test-db logs migrate revision seed

VENV := .venv/bin

# ─── Dependencies ────────────────────────────────────────────────────────────
install:
	python3 -m venv .venv
	$(VENV)/pip install -r requirements.txt

# ─── Docker (RabbitMQ) ───────────────────────────────────────────────────────
up:
	docker-compose up -d

down:
	docker-compose down

ps:
	docker-compose ps

logs:
	docker-compose logs -f rabbitmq

# ─── Run the app ─────────────────────────────────────────────────────────────
api:
	$(VENV)/uvicorn main:app --reload --port 8000

worker:
	$(VENV)/celery -A worker worker --loglevel=info

flower:
	$(VENV)/celery -A worker flower --port=5555

# ─── Database Migrations ─────────────────────────────────────────────────────
migrate:
	$(VENV)/alembic upgrade head

revision:
	$(VENV)/alembic revision --autogenerate -m "$(msg)"

seed:
	$(VENV)/python3 seed.py

# ─── Tests ───────────────────────────────────────────────────────────────────
test-config:
	$(VENV)/python3 -c "\
from config.configuration import settings; \
print('DATABASE_URL :', settings.DATABASE_URL[:50], '...'); \
print('REDIS_URL    :', settings.REDIS_URL[:40], '...'); \
print('RABBIT_MQ_URL:', settings.RABBIT_MQ_URL); \
print('Config OK')"

test-db:
	$(VENV)/python3 -c "\
import asyncio; \
from core.database.db_context import engine; \
from sqlalchemy import text; \
async def test(): \
    async with engine.connect() as conn: \
        result = await conn.execute(text('SELECT 1')); \
        print('Database connection OK:', result.scalar()); \
asyncio.run(test())"
