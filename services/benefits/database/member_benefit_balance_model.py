import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Float, Integer, DateTime, UniqueConstraint, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.database.db_context import Base


class MemberBenefitBalance(Base):
    __tablename__ = "member_benefit_balances"
    __table_args__ = (
        UniqueConstraint(
            "member_number", "benefit_code", "policy_year",
            name="uq_member_benefit_year"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    member_number: Mapped[str] = mapped_column(
        String(50), ForeignKey("members.member_number", ondelete="CASCADE"),
        nullable=False, index=True
    )
    benefit_code: Mapped[str] = mapped_column(
        String(50), ForeignKey("benefit_types.code", ondelete="CASCADE"),
        nullable=False, index=True
    )
    policy_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    annual_limit: Mapped[float] = mapped_column(Float, nullable=False)
    used_amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    remaining_amount: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
