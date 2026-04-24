"""Nitaqat configuration — per-tenant Saudization thresholds and tracking."""
import uuid
import enum
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, Integer, Float, ForeignKey, Boolean, UniqueConstraint, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class NitaqatBand(str, enum.Enum):
    platinum = "platinum"
    green_high = "green_high"
    green_low = "green_low"
    yellow = "yellow"
    red = "red"


class CompanySizeCategory(str, enum.Enum):
    micro = "micro"        # 1-5
    small = "small"        # 6-49
    medium = "medium"      # 50-499
    large = "large"        # 500-2999
    giant = "giant"        # 3000+


class NitaqatConfig(Base):
    """Per-tenant Nitaqat configuration.

    Stores the tenant's industry, size category, and custom band thresholds.
    One row per tenant — upserted on first configuration.
    """
    __tablename__ = "nitaqat_configs"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_nitaqat_config_tenant"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))

    # Company classification
    industry: Mapped[str] = mapped_column(String(255), default="general")
    industry_ar: Mapped[str | None] = mapped_column(String(255), nullable=True)
    size_category: Mapped[CompanySizeCategory] = mapped_column(
        SAEnum(CompanySizeCategory), default=CompanySizeCategory.small
    )

    # Thresholds (percentages) — configurable per tenant
    # Default simplified thresholds; real ones vary by industry/size
    platinum_threshold: Mapped[float] = mapped_column(Float, default=40.0)
    green_high_threshold: Mapped[float] = mapped_column(Float, default=26.0)
    green_low_threshold: Mapped[float] = mapped_column(Float, default=17.0)
    yellow_threshold: Mapped[float] = mapped_column(Float, default=6.0)
    # Below yellow_threshold = Red

    # Target ratio — what the company is aiming for (can differ from band minimum)
    target_saudization_pct: Mapped[float] = mapped_column(Float, default=26.0)

    # Alert thresholds
    alert_when_below_target: Mapped[bool] = mapped_column(Boolean, default=True)
    alert_buffer_pct: Mapped[float] = mapped_column(Float, default=2.0)
    # Alert when ratio drops within buffer_pct of the next lower band boundary

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    tenant = relationship("Tenant")
