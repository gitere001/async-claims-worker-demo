import asyncio
from datetime import date, datetime, timezone
from sqlalchemy import text
from core.database.db_context import AsyncSessionLocal
from repositories.members.database.member_model import Member, MemberStatus
from repositories.providers.database.provider_model import ServiceProvider, ProviderStatus
from repositories.benefits.database.benefit_type_model import BenefitType
from repositories.benefits.database.product_model import Product, ProductStatus
from repositories.benefits.database.product_benefit_model import ProductBenefit
from repositories.benefits.database.member_benefit_balance_model import MemberBenefitBalance

POLICY_YEAR = 2024

# ─── Benefit Types ────────────────────────────────────────────────────────────
BENEFIT_TYPES = [
    BenefitType(code="OUTPATIENT",  name="Outpatient"),
    BenefitType(code="INPATIENT",   name="Inpatient"),
    BenefitType(code="DENTAL",      name="Dental"),
    BenefitType(code="OPTICAL",     name="Optical"),
    BenefitType(code="PHARMACY",    name="Pharmacy"),
]

# ─── Products (Insurance Plans) ───────────────────────────────────────────────
PRODUCTS = [
    Product(code="BASIC",    name="Basic Plan",    status=ProductStatus.ACTIVE),
    Product(code="PREMIUM",  name="Premium Plan",  status=ProductStatus.ACTIVE),
    Product(code="ENHANCED", name="Enhanced Plan", status=ProductStatus.ACTIVE),
]

# ─── Product Benefits (what each plan covers and at what limit) ───────────────
PRODUCT_BENEFITS = [
    # BASIC PLAN
    ProductBenefit(product_code="BASIC", benefit_code="OUTPATIENT", annual_limit=30_000),
    ProductBenefit(product_code="BASIC", benefit_code="INPATIENT",  annual_limit=150_000),
    ProductBenefit(product_code="BASIC", benefit_code="PHARMACY",   annual_limit=10_000),

    # PREMIUM PLAN
    ProductBenefit(product_code="PREMIUM", benefit_code="OUTPATIENT", annual_limit=80_000),
    ProductBenefit(product_code="PREMIUM", benefit_code="INPATIENT",  annual_limit=500_000),
    ProductBenefit(product_code="PREMIUM", benefit_code="DENTAL",     annual_limit=20_000),
    ProductBenefit(product_code="PREMIUM", benefit_code="OPTICAL",    annual_limit=15_000),
    ProductBenefit(product_code="PREMIUM", benefit_code="PHARMACY",   annual_limit=30_000),

    # ENHANCED PLAN
    ProductBenefit(product_code="ENHANCED", benefit_code="OUTPATIENT", annual_limit=150_000),
    ProductBenefit(product_code="ENHANCED", benefit_code="INPATIENT",  annual_limit=1_000_000),
    ProductBenefit(product_code="ENHANCED", benefit_code="DENTAL",     annual_limit=50_000),
    ProductBenefit(product_code="ENHANCED", benefit_code="OPTICAL",    annual_limit=30_000),
    ProductBenefit(product_code="ENHANCED", benefit_code="PHARMACY",   annual_limit=60_000),
]

# ─── Members ──────────────────────────────────────────────────────────────────
MEMBERS = [
    Member(
        member_number="1524100",
        first_name="James",
        last_name="Gitere",
        date_of_birth=date(1990, 5, 15),
        policy_number="POL-2024-001",
        product_code="PREMIUM",
        status=MemberStatus.ACTIVE,
    ),
    Member(
        member_number="1524101",
        first_name="Sarah",
        last_name="Wanjiku",
        date_of_birth=date(1985, 8, 22),
        policy_number="POL-2024-002",
        product_code="ENHANCED",
        status=MemberStatus.ACTIVE,
    ),
    Member(
        member_number="1524102",
        first_name="Peter",
        last_name="Kamau",
        date_of_birth=date(1978, 3, 10),
        policy_number="POL-2024-003",
        product_code="BASIC",
        status=MemberStatus.INACTIVE,
    ),
    Member(
        member_number="1524103",
        first_name="Grace",
        last_name="Muthoni",
        date_of_birth=date(1995, 11, 30),
        policy_number="POL-2024-004",
        product_code="PREMIUM",
        status=MemberStatus.ACTIVE,
    ),
]

# ─── Service Providers ────────────────────────────────────────────────────────
PROVIDERS = [
    ServiceProvider(provider_code="METROPOLITAN-01", name="Metropolitan Hospital Nairobi", status=ProviderStatus.ACTIVE),
    ServiceProvider(provider_code="VETERAN-01",       name="Veteran's Hospital",            status=ProviderStatus.ACTIVE),
    ServiceProvider(provider_code="NAIROBI-WEST-01",  name="Nairobi West Hospital",         status=ProviderStatus.ACTIVE),
    ServiceProvider(provider_code="KENYATTA-01",      name="Kenyatta National Hospital",    status=ProviderStatus.ACTIVE),
]

# ─── Member Benefit Balances (full limits at start of year) ───────────────────
def make_balances():
    plan_benefits = {
        "PREMIUM":  [("OUTPATIENT", 80_000), ("INPATIENT", 500_000), ("DENTAL", 20_000), ("OPTICAL", 15_000), ("PHARMACY", 30_000)],
        "ENHANCED": [("OUTPATIENT", 150_000), ("INPATIENT", 1_000_000), ("DENTAL", 50_000), ("OPTICAL", 30_000), ("PHARMACY", 60_000)],
        "BASIC":    [("OUTPATIENT", 30_000), ("INPATIENT", 150_000), ("PHARMACY", 10_000)],
    }
    balances = []
    for member in MEMBERS:
        if member.status == MemberStatus.INACTIVE:
            continue
        for benefit_code, limit in plan_benefits[member.product_code]:
            balances.append(MemberBenefitBalance(
                member_number=member.member_number,
                benefit_code=benefit_code,
                policy_year=POLICY_YEAR,
                annual_limit=limit,
                used_amount=0.0,
                remaining_amount=limit,
                updated_at=datetime.now(timezone.utc),
            ))
    return balances


async def seed():
    # Clear all tables in dependency order before inserting
    # This makes the seed idempotent — safe to run multiple times
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(text("TRUNCATE TABLE member_benefit_balances CASCADE"))
            await session.execute(text("TRUNCATE TABLE claim_items CASCADE"))
            await session.execute(text("TRUNCATE TABLE claims CASCADE"))
            await session.execute(text("TRUNCATE TABLE members CASCADE"))
            await session.execute(text("TRUNCATE TABLE product_benefits CASCADE"))
            await session.execute(text("TRUNCATE TABLE service_providers CASCADE"))
            await session.execute(text("TRUNCATE TABLE products CASCADE"))
            await session.execute(text("TRUNCATE TABLE benefit_types CASCADE"))

    async with AsyncSessionLocal() as session:
        async with session.begin():
            session.add_all(BENEFIT_TYPES)
            session.add_all(PRODUCTS)

    async with AsyncSessionLocal() as session:
        async with session.begin():
            session.add_all(PRODUCT_BENEFITS)
            session.add_all(PROVIDERS)

    async with AsyncSessionLocal() as session:
        async with session.begin():
            session.add_all(MEMBERS)

    async with AsyncSessionLocal() as session:
        async with session.begin():
            session.add_all(make_balances())

    print(f"  {len(BENEFIT_TYPES)} benefit types")
    print(f"  {len(PRODUCTS)} products")
    print(f"  {len(PRODUCT_BENEFITS)} product benefits")
    print(f"  {len(PROVIDERS)} service providers")
    print(f"  {len(MEMBERS)} members")
    print(f"  {len(make_balances())} member benefit balances")
    print("Seed complete.")


if __name__ == "__main__":
    asyncio.run(seed())
