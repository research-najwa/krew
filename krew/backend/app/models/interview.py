"""Interview records — managed by Mohammad agent for AI screening interviews."""
import uuid
import enum
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, Integer, Text, Float, Enum as SAEnum, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class InterviewStatus(str, enum.Enum):
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"


class InterviewType(str, enum.Enum):
    ai_screening = "ai_screening"      # M2-01: Mohammad conducts AI interview
    human = "human"                     # Future: human interview records
    zoom_analysis = "zoom_analysis"     # M3-01: Zoom transcript analysis


class Interview(Base):
    __tablename__ = "interviews"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidates.id"), index=True)
    job_posting_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("job_postings.id"))
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversations.id"), nullable=True, index=True
    )
    interview_type: Mapped[InterviewType] = mapped_column(
        SAEnum(InterviewType), default=InterviewType.ai_screening
    )
    status: Mapped[InterviewStatus] = mapped_column(
        SAEnum(InterviewStatus), default=InterviewStatus.in_progress
    )

    # Interview content (JSON columns for flexibility)
    questions: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Structure: [
    #   {"index": 0, "question": "...", "question_ar": "...", "category": "technical|behavioral|situational|culture_fit"},
    #   ...
    # ]

    answers: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Structure: [
    #   {"index": 0, "answer": "...", "submitted_at": "ISO timestamp"},
    #   ...
    # ]

    current_question_index: Mapped[int] = mapped_column(Integer, default=0)
    total_questions: Mapped[int] = mapped_column(Integer, default=0)

    # Scorecard (populated on completion)
    scorecard: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    overall_score: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0-100

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    candidate: Mapped["Candidate"] = relationship(back_populates="interviews")
    job_posting: Mapped["JobPosting"] = relationship()
