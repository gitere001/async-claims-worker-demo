import uuid
from datetime import datetime, timezone, date
from enum import Enum as PyEnum

from sqlalchemy import String, Date, DateTime, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.database.db_context import Base


class MemberStatus(PyEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    SUSPENDED = "SUSPENDED"


class Member(Base):
    __tablename__ = "members"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    member_number: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=True, index=True
    )
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    date_of_birth: Mapped[date] = mapped_column(Date, nullable=False)
    policy_number: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=True, index=True
    )
    product_code: Mapped[str] = mapped_column(
        String(50), ForeignKey("products.code"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        Enum(MemberStatus), nullable=False, default=MemberStatus.ACTIVE, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
