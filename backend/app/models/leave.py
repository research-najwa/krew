"""Leave management — high-frequency agent interaction."""
import uuid
from datetime import datetime, date
from sqlalchemy import String, DateTime, Date, ForeignKey, Integer, Boolean, Text, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

import enum


class LeaveType(str, enum.Enum):
    annual = "annual"
    sick = "sick"
    emergency = "emergency"
    maternity = "maternity"
    paternity = "paternity"
    hajj = "hajj"  # Saudi-specific
    bereavement = "bereavement"
    unpaid = "unpaid"


class LeaveStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    cancelled = "cancelled"


class LeaveBalance(Base):
    """Annual leave entitlements per employee per type."""
    __tablename__ = "leave_balances"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id"))
    leave_type: Mapped[LeaveType] = mapped_column(SAEnum(LeaveType))
    year: Mapped[int] = mapped_column(Integer)
    total_days: Mapped[int] = mapped_column(Integer)
    used_days: Mapped[int] = mapped_column(Integer, default=0)

    employee: Mapped["Employee"] = relationship(back_populates="leave_balances")

    @property
    def remaining_days(self) -> int:
        return self.total_days - self.used_days


class LeaveRequest(Base):
    """Individual leave request — created by Deema agent via conversation."""
    __tablename__ = "leave_requests"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id"))
    approver_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("employees.id"))
    leave_type: Mapped[LeaveType] = mapped_column(SAEnum(LeaveType))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    business_days: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str | None] = mapped_column(Text)
    status: Mapped[LeaveStatus] = mapped_column(SAEnum(LeaveStatus), default=LeaveStatus.pending)
    created_by_agent: Mapped[str] = mapped_column(String(50), default="deema")
    created_via_channel: Mapped[str] = mapped_column(String(20), default="whatsapp")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Approval workflow fields
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    auto_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    advance_notice_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    labor_law_article: Mapped[str | None] = mapped_column(String(50), nullable=True)

    employee: Mapped["Employee"] = relationship(
        back_populates="leave_requests", foreign_keys=[employee_id]
    )
