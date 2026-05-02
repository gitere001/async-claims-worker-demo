import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Float, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database.db_context import Base


class ProductBenefit(Base):
    __tablename__ = "product_benefits"
    __table_args__ = (
        UniqueConstraint("product_code", "benefit_code", name="uq_product_benefit"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    product_code: Mapped[str] = mapped_column(
        String(50), ForeignKey("products.code", ondelete="CASCADE"), nullable=False, index=True
    )
    benefit_code: Mapped[str] = mapped_column(
        String(50), ForeignKey("benefit_types.code", ondelete="CASCADE"), nullable=False, index=True
    )
    annual_limit: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    product: Mapped["Product"] = relationship("Product", back_populates="benefits")
