from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool
from config.configuration import settings

# API engine — connection pool keeps connections warm so Neon never cold-starts
# and the dialect probe queries (pg_catalog.version etc.) only run once.
# FastAPI runs in a single event loop so pooling is safe here.
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=True,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
)

# Worker engine — NullPool required for Celery tasks.
# Each asyncio.run() creates a new event loop; a pooled connection bound to the
# previous loop raises "Future attached to a different loop".
worker_engine = create_async_engine(
    settings.DATABASE_URL,
    echo=True,
    poolclass=NullPool,
)

AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

WorkerSessionLocal = async_sessionmaker(
    worker_engine, class_=AsyncSession, expire_on_commit=False
)


class Base(DeclarativeBase):
    pass


class DatabaseContext:
    async def __aenter__(self):
        self.session = AsyncSessionLocal()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            await self.session.rollback()
        else:
            await self.session.commit()
        await self.session.close()


# Import all models here so SQLAlchemy registers every table in its metadata.
# Without this, FK references to tables from unimported models raise NoReferencedTableError.
def _register_models() -> None:
    # claim_model imports Base from here so it cannot be imported again — it is
    # already in sys.modules by the time this runs and will finish loading on its own.
    # We only need to force-load models that nothing else imports automatically.
    from repositories.members.database.member_model import Member  # noqa: F401
    from repositories.providers.database.provider_model import ServiceProvider  # noqa: F401
    from repositories.benefits.database.benefit_type_model import BenefitType  # noqa: F401
    from repositories.benefits.database.product_model import Product  # noqa: F401
    from repositories.benefits.database.product_benefit_model import ProductBenefit  # noqa: F401
    from repositories.benefits.database.member_benefit_balance_model import MemberBenefitBalance  # noqa: F401
    from repositories.tasks.database.failed_task_model import FailedTask  # noqa: F401


_register_models()
