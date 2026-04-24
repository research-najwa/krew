"""Recruiting pipeline — managed by Mohammad agent."""
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, Integer, Text, Float, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

import enum


class PostingStatus(str, enum.Enum):
    draft = "draft"
    open = "open"
    closed = "closed"
    on_hold = "on_hold"


class CandidateStage(str, enum.Enum):
    applied = "applied"
    screened = "screened"
    shortlisted = "shortlisted"
    interview_scheduled = "interview_scheduled"
    interviewed = "interviewed"
    offer_sent = "offer_sent"
    hired = "hired"
    rejected = "rejected"
    withdrawn = "withdrawn"


class JobPosting(Base):
    __tablename__ = "job_postings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    department_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("departments.id"))
    title: Mapped[str] = mapped_column(String(255))
    title_ar: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    requirements: Mapped[str | None] = mapped_column(Text)
    salary_min_sar: Mapped[int | None] = mapped_column(Integer)
    salary_max_sar: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[PostingStatus] = mapped_column(
        SAEnum(PostingStatus), default=PostingStatus.draft
    )
    ai_readiness_score: Mapped[float | None] = mapped_column(Float)  # from Agent Factory
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    candidates: Mapped[list["Candidate"]] = relationship(back_populates="job_posting")


class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    job_posting_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("job_postings.id"))
    name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(20))
    resume_url: Mapped[str | None] = mapped_column(String(500))
    stage: Mapped[CandidateStage] = mapped_column(
        SAEnum(CandidateStage), default=CandidateStage.applied
    )
    ai_match_score: Mapped[float | None] = mapped_column(Float)  # 0-100
    ai_screening_notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    job_posting: Mapped["JobPosting"] = relationship(back_populates="candidates")
    interviews: Mapped[list["Interview"]] = relationship(back_populates="candidate")
