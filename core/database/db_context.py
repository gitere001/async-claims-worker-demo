from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool
from config.configuration import settings

# NullPool is required for Celery workers: each asyncio.run() call creates a new
# event loop, and a persistent connection pool binds connections to the old loop,
# causing "Future attached to a different loop" errors.
engine = create_async_engine(settings.DATABASE_URL, echo=True, poolclass=NullPool)

AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
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
    from services.members.database.member_model import Member  # noqa: F401
    from services.providers.database.provider_model import ServiceProvider  # noqa: F401
    from services.benefits.database.benefit_type_model import BenefitType  # noqa: F401
    from services.benefits.database.product_model import Product  # noqa: F401
    from services.benefits.database.product_benefit_model import ProductBenefit  # noqa: F401
    from services.benefits.database.member_benefit_balance_model import MemberBenefitBalance  # noqa: F401


_register_models()
