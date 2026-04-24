"""Seed recruitment demo data — job postings and candidates for Mohammad agent.

Run AFTER seed.py and seed_demo_data.py (requires existing tenant + departments).
Idempotent: skips if recruitment data already exists.
"""
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from app.database import async_session
from app.models.tenant import Tenant
from app.models.employee import Department
from app.models.candidate import (
    Candidate,
    CandidateStage,
    JobPosting,
    PostingStatus,
)


async def seed_recruitment():
    async with async_session() as db:
        # Find tenant
        result = await db.execute(select(Tenant).limit(1))
        tenant = result.scalar_one_or_none()
        if not tenant:
            print("No tenant found. Run seed.py first.")
            return
        tenant_id = tenant.id

        # Check if recruitment data already exists
        result = await db.execute(
            select(JobPosting).where(JobPosting.tenant_id == tenant_id).limit(1)
        )
        if result.scalar_one_or_none():
            print("Recruitment data already seeded. Skipping.")
            return

        # Get departments
        dept_result = await db.execute(
            select(Department).where(Department.tenant_id == tenant_id)
        )
        depts = {d.name: d for d in dept_result.scalars().all()}

        eng_dept = depts.get("Engineering")
        hr_dept = depts.get("Human Resources")
        sales_dept = depts.get("Sales")

        if not eng_dept or not hr_dept:
            print("Required departments (Engineering, Human Resources) not found. Run seed.py first.")
            return

        # ── Job Postings ──────────────────────────────────────────
        posting_1_id = uuid4()  # Senior Software Engineer — open, many candidates
        posting_2_id = uuid4()  # HR Business Partner — open, few candidates
        posting_3_id = uuid4()  # Data Analyst — on_hold
        posting_4_id = uuid4()  # Sales Executive — closed, 1 hired

        postings = [
            JobPosting(
                id=posting_1_id,
                tenant_id=tenant_id,
                department_id=eng_dept.id,
                title="Senior Software Engineer",
                title_ar="مهندس برمجيات أول",
                description=(
                    "We are looking for a Senior Software Engineer to join our Engineering team "
                    "in Riyadh. The ideal candidate will have strong experience with Python, "
                    "FastAPI, cloud services (AWS/GCP), and building scalable microservices. "
                    "You will lead backend architecture decisions and mentor junior developers."
                ),
                requirements=(
                    "5+ years of software engineering experience\n"
                    "Strong Python and FastAPI knowledge\n"
                    "Experience with PostgreSQL and Redis\n"
                    "Cloud experience (AWS or GCP)\n"
                    "Excellent problem-solving skills\n"
                    "Bachelor's degree in Computer Science or related field\n"
                    "Fluent in English; Arabic is a plus"
                ),
                salary_min_sar=22000,
                salary_max_sar=35000,
                status=PostingStatus.open,
                created_at=datetime(2026, 2, 15, 9, 0),
            ),
            JobPosting(
                id=posting_2_id,
                tenant_id=tenant_id,
                department_id=hr_dept.id,
                title="HR Business Partner",
                title_ar="شريك أعمال الموارد البشرية",
                description=(
                    "Seeking an HR Business Partner to support our growing teams. "
                    "You will work closely with department heads to align HR strategies "
                    "with business objectives, manage employee relations, and drive "
                    "talent development initiatives in line with Saudi labor regulations."
                ),
                requirements=(
                    "3+ years HR experience in Saudi Arabia\n"
                    "Knowledge of Saudi Labor Law and GOSI\n"
                    "Experience with HR systems (SAP SuccessFactors preferred)\n"
                    "Strong communication in Arabic and English\n"
                    "Bachelor's degree in HR or Business Administration\n"
                    "SHRM or CIPD certification is a plus"
                ),
                salary_min_sar=18000,
                salary_max_sar=28000,
                status=PostingStatus.open,
                created_at=datetime(2026, 3, 20, 9, 0),
            ),
            JobPosting(
                id=posting_3_id,
                tenant_id=tenant_id,
                department_id=eng_dept.id,
                title="Data Analyst",
                title_ar="محلل بيانات",
                description=(
                    "Looking for a Data Analyst to transform raw data into actionable insights. "
                    "You will build dashboards, create reports, and support data-driven "
                    "decision-making across the organization."
                ),
                requirements=(
                    "2+ years of data analysis experience\n"
                    "Proficiency in SQL and Python (pandas, numpy)\n"
                    "Experience with visualization tools (Tableau, Power BI, or Metabase)\n"
                    "Strong analytical and presentation skills\n"
                    "Bachelor's degree in Statistics, CS, or related field"
                ),
                salary_min_sar=14000,
                salary_max_sar=22000,
                status=PostingStatus.on_hold,
                created_at=datetime(2026, 1, 10, 9, 0),
            ),
            JobPosting(
                id=posting_4_id,
                tenant_id=tenant_id,
                department_id=sales_dept.id if sales_dept else eng_dept.id,
                title="Sales Executive",
                title_ar="تنفيذي مبيعات",
                description=(
                    "We needed a Sales Executive to expand our B2B client base in the Saudi market. "
                    "This role required building relationships with enterprise clients and closing deals."
                ),
                requirements=(
                    "3+ years B2B sales experience in Saudi market\n"
                    "Proven track record of meeting/exceeding targets\n"
                    "Strong network in Saudi business community\n"
                    "Fluent Arabic and English\n"
                    "Bachelor's degree"
                ),
                salary_min_sar=12000,
                salary_max_sar=18000,
                status=PostingStatus.closed,
                created_at=datetime(2025, 11, 1, 9, 0),
            ),
        ]

        for p in postings:
            db.add(p)
        await db.flush()

        # ── Candidates ────────────────────────────────────────────

        # Pre-built screening notes for seeded candidates
        sara_notes = json.dumps({
            "fit_score": 85,
            "strengths": [
                "5+ years Python/FastAPI experience",
                "Led team of 4 at Elm Company",
                "Bilingual (AR/EN)",
            ],
            "gaps": [
                "No cloud certification",
                "Limited frontend experience",
            ],
            "experience_relevance": "high",
            "skills_match_pct": 82,
            "recommendation": "proceed_to_interview",
            "summary": "Strong backend engineer with Saudi tech company experience. Recommend interview.",
            "summary_ar": "مهندسة برمجيات قوية بخبرة في شركات تقنية سعودية. يوصى بالمقابلة.",
        }, ensure_ascii=False)

        faisal_notes = json.dumps({
            "fit_score": 78,
            "strengths": [
                "4 years Python experience",
                "AWS certified",
                "Strong in microservices",
            ],
            "gaps": [
                "No leadership experience yet",
                "Limited database optimization skills",
            ],
            "experience_relevance": "medium",
            "skills_match_pct": 74,
            "recommendation": "review_further",
            "summary": "Decent technical skills with room to grow into senior role. Worth a deeper look.",
            "summary_ar": "مهارات تقنية جيدة مع إمكانية التطور. يستحق مراجعة أعمق.",
        }, ensure_ascii=False)

        nora_notes = json.dumps({
            "fit_score": 91,
            "strengths": [
                "7 years full-stack experience at Tawuniya",
                "Led migration to microservices architecture",
                "KFUPM graduate, AWS Solutions Architect certified",
                "Bilingual with excellent communication",
            ],
            "gaps": [
                "Slightly above salary range expectations",
            ],
            "experience_relevance": "high",
            "skills_match_pct": 93,
            "recommendation": "proceed_to_interview",
            "summary": "Top candidate. Extensive experience, strong credentials, perfect technical fit.",
            "summary_ar": "أفضل مرشحة. خبرة واسعة وشهادات قوية وتوافق تقني ممتاز.",
        }, ensure_ascii=False)

        khalid_notes = json.dumps({
            "fit_score": 62,
            "strengths": [
                "3 years Java experience",
                "Fast learner per references",
            ],
            "gaps": [
                "No Python experience",
                "No cloud experience",
                "Would need significant ramp-up time",
            ],
            "experience_relevance": "low",
            "skills_match_pct": 45,
            "recommendation": "likely_not_a_fit",
            "summary": "Limited overlap with requirements. Java background but no Python/cloud skills.",
            "summary_ar": "تداخل محدود مع المتطلبات. خلفية جافا بدون مهارات بايثون أو سحابة.",
        }, ensure_ascii=False)

        layla_notes = json.dumps({
            "fit_score": 74,
            "strengths": [
                "4 years HR experience in Riyadh",
                "Knowledge of Saudi Labor Law",
                "CIPD Level 5 certified",
            ],
            "gaps": [
                "No HRBP experience specifically",
                "Limited systems experience",
            ],
            "experience_relevance": "medium",
            "skills_match_pct": 70,
            "recommendation": "review_further",
            "summary": "Solid HR generalist looking to step into HRBP role. Worth interviewing.",
            "summary_ar": "أخصائية موارد بشرية جيدة تسعى للانتقال لدور شريك أعمال. تستحق المقابلة.",
        }, ensure_ascii=False)

        reem_notes = json.dumps({
            "fit_score": 80,
            "strengths": [
                "3 years data analysis at SABIC",
                "Expert in SQL and Tableau",
                "King Saud University graduate",
            ],
            "gaps": [
                "Limited Python experience",
                "No cloud data tools experience",
            ],
            "experience_relevance": "high",
            "skills_match_pct": 76,
            "recommendation": "proceed_to_interview",
            "summary": "Strong data analyst with SABIC experience and excellent visualization skills.",
            "summary_ar": "محللة بيانات قوية بخبرة في سابك ومهارات تصور ممتازة.",
        }, ensure_ascii=False)

        haya_notes = json.dumps({
            "fit_score": 88,
            "strengths": [
                "7 years B2B sales in Saudi market",
                "Exceeded targets 3 consecutive years",
                "Strong enterprise client network",
            ],
            "gaps": [
                "No SaaS experience",
            ],
            "experience_relevance": "high",
            "skills_match_pct": 85,
            "recommendation": "proceed_to_interview",
            "summary": "Excellent sales professional with deep Saudi market knowledge. Hired.",
            "summary_ar": "محترفة مبيعات ممتازة بمعرفة عميقة بالسوق السعودي. تم توظيفها.",
        }, ensure_ascii=False)

        candidates = [
            # Posting 1: Senior Software Engineer (6 candidates)
            Candidate(
                id=uuid4(),
                job_posting_id=posting_1_id,
                name="Ahmed Al-Rashid",
                email="ahmed.r@email.com",
                phone="+966501234567",
                resume_url=None,
                stage=CandidateStage.applied,
                ai_match_score=None,
                ai_screening_notes=None,
                created_at=datetime(2026, 2, 20, 10, 0),
            ),
            Candidate(
                id=uuid4(),
                job_posting_id=posting_1_id,
                name="Sara Al-Dosari",
                email="sara.d@email.com",
                phone="+966502345678",
                resume_url="https://drive.google.com/resume/sara-aldosari.pdf",
                stage=CandidateStage.screened,
                ai_match_score=85.0,
                ai_screening_notes=sara_notes,
                created_at=datetime(2026, 2, 22, 14, 0),
            ),
            Candidate(
                id=uuid4(),
                job_posting_id=posting_1_id,
                name="Faisal Al-Otaibi",
                email="faisal.o@email.com",
                phone="+966503456789",
                resume_url="https://drive.google.com/resume/faisal-alotaibi.pdf",
                stage=CandidateStage.shortlisted,
                ai_match_score=78.0,
                ai_screening_notes=faisal_notes,
                created_at=datetime(2026, 2, 25, 9, 0),
            ),
            Candidate(
                id=uuid4(),
                job_posting_id=posting_1_id,
                name="Nora Al-Qahtani",
                email="nora.q@email.com",
                phone="+966504567890",
                resume_url="https://drive.google.com/resume/nora-alqahtani.pdf",
                stage=CandidateStage.interview_scheduled,
                ai_match_score=91.0,
                ai_screening_notes=nora_notes,
                created_at=datetime(2026, 3, 1, 11, 0),
            ),
            Candidate(
                id=uuid4(),
                job_posting_id=posting_1_id,
                name="Khalid Al-Harbi",
                email="khalid.h@email.com",
                phone="+966505678901",
                resume_url="https://drive.google.com/resume/khalid-alharbi.pdf",
                stage=CandidateStage.screened,
                ai_match_score=62.0,
                ai_screening_notes=khalid_notes,
                created_at=datetime(2026, 3, 5, 15, 0),
            ),
            Candidate(
                id=uuid4(),
                job_posting_id=posting_1_id,
                name="Maha Al-Zahrani",
                email="maha.z@email.com",
                phone="+966506789012",
                resume_url=None,
                stage=CandidateStage.applied,
                ai_match_score=None,
                ai_screening_notes=None,
                created_at=datetime(2026, 3, 10, 8, 0),
            ),
            # Posting 2: HR Business Partner (2 candidates)
            Candidate(
                id=uuid4(),
                job_posting_id=posting_2_id,
                name="Omar Al-Ghamdi",
                email="omar.g@email.com",
                phone="+966507890123",
                resume_url=None,
                stage=CandidateStage.applied,
                ai_match_score=None,
                ai_screening_notes=None,
                created_at=datetime(2026, 3, 21, 10, 0),
            ),
            Candidate(
                id=uuid4(),
                job_posting_id=posting_2_id,
                name="Layla Al-Shammari",
                email="layla.s@email.com",
                phone="+966508901234",
                resume_url="https://drive.google.com/resume/layla-alshammari.pdf",
                stage=CandidateStage.screened,
                ai_match_score=74.0,
                ai_screening_notes=layla_notes,
                created_at=datetime(2026, 3, 22, 9, 0),
            ),
            # Posting 3: Data Analyst (3 candidates)
            Candidate(
                id=uuid4(),
                job_posting_id=posting_3_id,
                name="Turki Al-Mutairi",
                email="turki.m@email.com",
                phone="+966509012345",
                resume_url=None,
                stage=CandidateStage.applied,
                ai_match_score=None,
                ai_screening_notes=None,
                created_at=datetime(2026, 1, 15, 14, 0),
            ),
            Candidate(
                id=uuid4(),
                job_posting_id=posting_3_id,
                name="Reem Al-Anazi",
                email="reem.a@email.com",
                phone="+966510123456",
                resume_url="https://drive.google.com/resume/reem-alanazi.pdf",
                stage=CandidateStage.screened,
                ai_match_score=80.0,
                ai_screening_notes=reem_notes,
                created_at=datetime(2026, 1, 20, 11, 0),
            ),
            Candidate(
                id=uuid4(),
                job_posting_id=posting_3_id,
                name="Yousef Al-Dossary",
                email="yousef.d@email.com",
                phone="+966511234567",
                resume_url=None,
                stage=CandidateStage.applied,
                ai_match_score=None,
                ai_screening_notes=None,
                created_at=datetime(2026, 1, 25, 16, 0),
            ),
            # Posting 4: Sales Executive (1 hired candidate)
            Candidate(
                id=uuid4(),
                job_posting_id=posting_4_id,
                name="Haya Al-Salem",
                email="haya.s@email.com",
                phone="+966512345678",
                resume_url="https://drive.google.com/resume/haya-alsalem.pdf",
                stage=CandidateStage.hired,
                ai_match_score=88.0,
                ai_screening_notes=haya_notes,
                created_at=datetime(2025, 11, 10, 9, 0),
            ),
        ]

        for c in candidates:
            db.add(c)

        await db.commit()

        print("Recruitment demo data seeded successfully!")
        print()
        print("Job Postings:")
        for p in postings:
            print(f"  {p.title} ({p.title_ar}) | {p.status.value} | {p.salary_min_sar:,}-{p.salary_max_sar:,} SAR")
        print()
        print(f"Candidates: {len(candidates)} total")
        print(f"  Posting 1 (Sr SW Eng): 6 candidates — 2 applied, 2 screened, 1 shortlisted, 1 interview_scheduled")
        print(f"  Posting 2 (HR BP):     2 candidates — 1 applied, 1 screened")
        print(f"  Posting 3 (Data):      3 candidates — 2 applied, 1 screened")
        print(f"  Posting 4 (Sales):     1 candidate  — 1 hired (for time-to-hire stat)")
        print()
        print("Demo scenarios ready:")
        print("  1. 'وش وضع التوظيف عندنا؟' — Pipeline summary")
        print("  2. 'اكتب لي وصف وظيفي لمهندس برمجيات أول' — AI JD generation")
        print("  3. 'عطني تفاصيل وظيفة مهندس البرمجيات' — Posting details with candidates")
        print("  4. 'افحص لي أحمد على وظيفة مهندس البرمجيات' — AI candidate screening")
        print("  5. 'جدول مقابلة لأحمد يوم الأحد الجاي' — Interview scheduling")
        print("  6. 'ابحث عن مرشحين لوظيفة مهندس برمجيات' — Web search")


if __name__ == "__main__":
    asyncio.run(seed_recruitment())
