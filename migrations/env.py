import asyncio
import os
from logging.config import fileConfig

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy import pool
from alembic import context

load_dotenv()

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override URL from .env — credentials never live in alembic.ini
config.set_main_option("sqlalchemy.url", os.getenv("DATABASE_URL"))

# Import every model so Alembic can see all tables
from core.database.db_context import Base
from repositories.claims.database.claim_model import Claim, ClaimItem                              # noqa
from repositories.members.database.member_model import Member                                      # noqa
from repositories.providers.database.provider_model import ServiceProvider                         # noqa
from repositories.benefits.database.benefit_type_model import BenefitType                         # noqa
from repositories.benefits.database.product_model import Product                                   # noqa
from repositories.benefits.database.product_benefit_model import ProductBenefit                    # noqa
from repositories.benefits.database.member_benefit_balance_model import MemberBenefitBalance       # noqa

target_metadata = Base.metadata


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations():
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
