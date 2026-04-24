"""Compliance tracking — managed by Yara agent. Saudi labor law focus."""
import uuid
from datetime import datetime, date
from sqlalchemy import String, DateTime, Date, ForeignKey, Text, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

import enum


class ComplianceSeverity(str, enum.Enum):
    info = "info"
    warning = "warning"
    critical = "critical"


class ComplianceRecord(Base):
    """Tracks compliance status across jurisdictions."""
    __tablename__ = "compliance_records"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    category: Mapped[str] = mapped_column(String(100))  # gosi, nitaqat, wps, labor_law...
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text)
    is_compliant: Mapped[bool] = mapped_column(default=True)
    last_checked: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    next_deadline: Mapped[date | None] = mapped_column(Date)


class ComplianceAlert(Base):
    """Alerts raised by Yara when regulations change or deadlines approach."""
    __tablename__ = "compliance_alerts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    severity: Mapped[ComplianceSeverity] = mapped_column(SAEnum(ComplianceSeverity))
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text)
    regulation_reference: Mapped[str | None] = mapped_column(String(500))
    recommended_action: Mapped[str | None] = mapped_column(Text)
    is_resolved: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)
