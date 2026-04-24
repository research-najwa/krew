"""Employee and department models — core of the lightweight SOR."""
import uuid
from datetime import datetime, date
from sqlalchemy import String, DateTime, Date, ForeignKey, Integer, Boolean, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

import enum


class EmployeeStatus(str, enum.Enum):
    active = "active"
    onboarding = "onboarding"
    on_leave = "on_leave"
    offboarding = "offboarding"
    terminated = "terminated"


class WorkMode(str, enum.Enum):
    onsite = "onsite"
    remote = "remote"
    hybrid = "hybrid"


class Gender(str, enum.Enum):
    male = "male"
    female = "female"


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    name: Mapped[str] = mapped_column(String(255))
    name_ar: Mapped[str | None] = mapped_column(String(255))
    manager_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("employees.id", use_alter=True))
    headcount_budget: Mapped[int | None] = mapped_column(Integer)
    cost_budget_sar: Mapped[int | None] = mapped_column(Integer)  # annual budget in SAR

    tenant: Mapped["Tenant"] = relationship(back_populates="departments")
    employees: Mapped[list["Employee"]] = relationship(
        back_populates="department", foreign_keys="Employee.department_id"
    )


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    department_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("departments.id"))

    # Identity
    employee_number: Mapped[str | None] = mapped_column(String(50))
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    first_name_ar: Mapped[str | None] = mapped_column(String(100))
    last_name_ar: Mapped[str | None] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(20))
    national_id: Mapped[str | None] = mapped_column(String(20))  # Saudi ID / Iqama

    # Role
    job_title: Mapped[str] = mapped_column(String(255))
    job_title_ar: Mapped[str | None] = mapped_column(String(255))
    manager_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("employees.id"))

    # Employment
    status: Mapped[EmployeeStatus] = mapped_column(
        SAEnum(EmployeeStatus), default=EmployeeStatus.active
    )
    hire_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    is_saudi: Mapped[bool] = mapped_column(default=True)  # for Saudization/Nitaqat tracking
    salary_sar: Mapped[int | None] = mapped_column(Integer)  # monthly in SAR
    gosi_registered: Mapped[bool] = mapped_column(default=False)

    # Demographics
    gender: Mapped[Gender | None] = mapped_column(SAEnum(Gender), nullable=True)

    # Probation & contract
    probation_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    probation_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    contract_type: Mapped[str] = mapped_column(String(50), default="full_time")

    # Work arrangement
    work_mode: Mapped[WorkMode] = mapped_column(
        SAEnum(WorkMode), default=WorkMode.onsite
    )
    wfh_days_per_week: Mapped[int | None] = mapped_column(Integer)  # for hybrid: how many days remote
    work_location: Mapped[str | None] = mapped_column(String(255))  # office name or city

    # Channels — which channels this employee uses to talk to Krew
    whatsapp_number: Mapped[str | None] = mapped_column(String(20))
    slack_user_id: Mapped[str | None] = mapped_column(String(50))
    teams_user_id: Mapped[str | None] = mapped_column(String(50))

    # Preferences
    preferred_language: Mapped[str] = mapped_column(String(5), default="ar")
    preferred_channel: Mapped[str] = mapped_column(String(20), default="whatsapp")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    tenant: Mapped["Tenant"] = relationship(back_populates="employees")
    department: Mapped["Department"] = relationship(
        back_populates="employees", foreign_keys=[department_id]
    )
    leave_balances: Mapped[list["LeaveBalance"]] = relationship(back_populates="employee")
    leave_requests: Mapped[list["LeaveRequest"]] = relationship(
        back_populates="employee", foreign_keys="LeaveRequest.employee_id"
    )
    conversations: Mapped[list["Conversation"]] = relationship(back_populates="employee")

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @property
    def is_on_probation(self) -> bool:
        """Returns True if today < probation_end_date and not probation_completed."""
        if self.probation_completed:
            return False
        if self.probation_end_date is None:
            return False
        return date.today() < self.probation_end_date

    @property
    def tenure_years(self) -> float:
        """Years since hire_date as a float."""
        if not self.hire_date:
            return 0.0
        delta = date.today() - self.hire_date
        return delta.days / 365.25
