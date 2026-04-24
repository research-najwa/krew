"""Payslip model — monthly salary records for employee self-service."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Payslip(Base):
    __tablename__ = "payslips"
    __table_args__ = (
        UniqueConstraint("employee_id", "year", "month", name="uq_payslip_employee_year_month"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id"))

    year: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer)  # 1-12

    # Earnings
    basic_salary: Mapped[int] = mapped_column(Integer)  # SAR
    housing_allowance: Mapped[int] = mapped_column(Integer, default=0)
    transport_allowance: Mapped[int] = mapped_column(Integer, default=0)
    other_allowances: Mapped[int] = mapped_column(Integer, default=0)

    # Deductions
    gosi_employee: Mapped[int] = mapped_column(Integer, default=0)
    absent_deduction: Mapped[int] = mapped_column(Integer, default=0)
    other_deductions: Mapped[int] = mapped_column(Integer, default=0)

    # Totals
    gross_salary: Mapped[int] = mapped_column(Integer)
    total_deductions: Mapped[int] = mapped_column(Integer)
    net_salary: Mapped[int] = mapped_column(Integer)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    employee: Mapped["Employee"] = relationship()
