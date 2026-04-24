"""Interview service — business logic for AI screening interviews (Mohammad M2)."""
import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.interview import Interview, InterviewStatus, InterviewType

logger = logging.getLogger(__name__)


class InterviewService:
    def __init__(self, db: AsyncSession, tenant_id: UUID):
        self.db = db
        self.tenant_id = tenant_id

    async def get_active_interview(
        self,
        candidate_id: UUID | None = None,
        conversation_id: UUID | None = None,
    ) -> Interview | None:
        """Find an in-progress interview by candidate or conversation."""
        if candidate_id is None and conversation_id is None:
            return None

        query = select(Interview).where(
            Interview.tenant_id == self.tenant_id,
            Interview.status == InterviewStatus.in_progress,
        )
        if candidate_id:
            query = query.where(Interview.candidate_id == candidate_id)
        if conversation_id:
            query = query.where(Interview.conversation_id == conversation_id)
        query = query.order_by(Interview.created_at.desc()).limit(1)
        query = query.with_for_update()  # Prevent race condition on check-then-create
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def create_interview(
        self,
        candidate_id: UUID,
        job_posting_id: UUID,
        conversation_id: UUID | None,
        questions: list[dict],
    ) -> Interview:
        """Create a new Interview record with generated questions."""
        interview = Interview(
            tenant_id=self.tenant_id,
            candidate_id=candidate_id,
            job_posting_id=job_posting_id,
            conversation_id=conversation_id,
            interview_type=InterviewType.ai_screening,
            status=InterviewStatus.in_progress,
            questions=questions,
            answers=[],
            current_question_index=0,
            total_questions=len(questions),
        )
        self.db.add(interview)
        await self.db.commit()
        await self.db.refresh(interview)
        return interview

    async def submit_answer(
        self, interview_id: UUID, answer: str
    ) -> dict:
        """Store answer, advance index. Returns status dict with next_question or completion signal."""
        result = await self.db.execute(
            select(Interview).where(
                Interview.id == interview_id,
                Interview.tenant_id == self.tenant_id,
            ).with_for_update()
        )
        interview = result.scalar_one_or_none()
        if not interview:
            return {"error": True, "message": "Interview not found."}

        if interview.status != InterviewStatus.in_progress:
            return {"error": True, "message": "Interview is not in progress."}

        # Append answer
        answers = list(interview.answers or [])
        answers.append({
            "index": interview.current_question_index,
            "answer": answer,
            "submitted_at": datetime.utcnow().isoformat(),
        })
        interview.answers = answers
        interview.current_question_index += 1

        is_last = interview.current_question_index >= interview.total_questions

        if is_last:
            # Signal completion — scoring is handled by the agent
            interview.status = InterviewStatus.completed
            interview.completed_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(interview)

        if is_last:
            return {
                "completed": True,
                "interview_id": str(interview.id),
                "total_answers": len(answers),
            }

        # Return next question (bounds check to prevent IndexError)
        questions = interview.questions or []
        if interview.current_question_index >= len(questions):
            return {"error": True, "message": "Question index out of bounds."}

        next_q = questions[interview.current_question_index]
        return {
            "completed": False,
            "interview_id": str(interview.id),
            "question_number": interview.current_question_index + 1,
            "total_questions": interview.total_questions,
            "next_question": next_q,
        }

    async def complete_interview(
        self, interview_id: UUID, scorecard: dict, overall_score: float,
        overwrite: bool = False,
    ) -> Interview:
        """Mark interview completed with scorecard."""
        result = await self.db.execute(
            select(Interview).where(
                Interview.id == interview_id,
                Interview.tenant_id == self.tenant_id,
            )
        )
        interview = result.scalar_one_or_none()
        if not interview:
            raise ValueError("Interview not found")

        # Guard: do not overwrite an existing scorecard unless explicitly requested
        if interview.scorecard is not None and not overwrite:
            logger.info("Scorecard already exists for interview %s — skipping.", interview_id)
            return interview

        interview.scorecard = scorecard
        interview.overall_score = overall_score
        if interview.status != InterviewStatus.completed:
            interview.status = InterviewStatus.completed
            interview.completed_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(interview)
        return interview

    async def cancel_interview(self, interview_id: UUID) -> Interview | None:
        """Cancel an in-progress interview."""
        result = await self.db.execute(
            select(Interview).where(
                Interview.id == interview_id,
                Interview.tenant_id == self.tenant_id,
            )
        )
        interview = result.scalar_one_or_none()
        if not interview:
            return None
        interview.status = InterviewStatus.cancelled
        await self.db.commit()
        await self.db.refresh(interview)
        return interview

    async def get_interviews_for_candidate(
        self, candidate_id: UUID
    ) -> list[Interview]:
        """All interviews for a candidate."""
        result = await self.db.execute(
            select(Interview).where(
                Interview.candidate_id == candidate_id,
                Interview.tenant_id == self.tenant_id,
            ).order_by(Interview.created_at.desc())
        )
        return list(result.scalars().all())
