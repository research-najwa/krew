"""Multi-tenant model. Every company using Krew is a tenant."""
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

import enum


class PlanTier(str, enum.Enum):
    starter = "starter"
    growth = "growth"
    enterprise = "enterprise"


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    name_ar: Mapped[str | None] = mapped_column(String(255))
    domain: Mapped[str | None] = mapped_column(String(255))
    plan: Mapped[PlanTier] = mapped_column(SAEnum(PlanTier), default=PlanTier.starter)
    employee_count: Mapped[int] = mapped_column(default=0)
    cr_number: Mapped[str | None] = mapped_column(String(20))  # Saudi commercial registration
    gosi_number: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    employees: Mapped[list["Employee"]] = relationship(back_populates="tenant")
    departments: Mapped[list["Department"]] = relationship(back_populates="tenant")
    policies: Mapped[list["Policy"]] = relationship(back_populates="tenant")
    conversations: Mapped[list["Conversation"]] = relationship(back_populates="tenant")
