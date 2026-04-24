"""Seed data for testing ToolCard UI — approved leaves (calendar) + employee documents.

Run AFTER seed.py and seed_demo_data.py.
Idempotent: skips if marker data already exists.
"""
import asyncio
import sys
from pathlib import Path
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from app.database import async_session
from app.models.tenant import Tenant
from app.models.employee import Employee, Department
from app.models.leave import LeaveRequest, LeaveType, LeaveStatus
from app.models.document import Document, DocumentCategory
from app.models.employee_document import EmployeeDocument, DocumentType, VerificationStatus


async def seed():
    async with async_session() as db:
        result = await db.execute(select(Tenant).limit(1))
        tenant = result.scalar_one_or_none()
        if not tenant:
            print("No tenant found. Run seed.py first.")
            return
        tenant_id = tenant.id

        # Load employees
        emp_result = await db.execute(
            select(Employee).where(Employee.tenant_id == tenant_id).order_by(Employee.employee_number)
        )
        emps = {e.employee_number: e for e in emp_result.scalars().all()}

        ahmed = emps.get("EMP-001")   # VP Engineering
        fatimah = emps.get("EMP-002") # HR Manager
        omar = emps.get("EMP-003")    # Backend Dev
        khalid = emps.get("EMP-005")  # QA Engineer
        noura = emps.get("EMP-006")   # Data Analyst

        if not ahmed:
            print("Ahmed (EMP-001) not found. Run seed.py first.")
            return

        # Check idempotency — look for a specific leave we'll create
        existing = await db.execute(
            select(LeaveRequest).where(
                LeaveRequest.employee_id == ahmed.id,
                LeaveRequest.start_date == date(2026, 4, 13),
            )
        )
        if existing.scalar_one_or_none():
            print("Card demo data already seeded. Skipping.")
            return

        # ── Approved leaves for team calendar (current week + next week) ──
        # Today is April 11, 2026 (Saturday). Work week = Sun Apr 12 – Thu Apr 16
        approved_leaves = []

        # Omar on leave Sun-Tue (Apr 12-14)
        if omar:
            approved_leaves.append(LeaveRequest(
                employee_id=omar.id,
                approver_id=ahmed.id,
                leave_type=LeaveType.annual,
                start_date=date(2026, 4, 12),
                end_date=date(2026, 4, 14),
                business_days=3,
                reason="Family visit to Jeddah",
                status=LeaveStatus.approved,
                approved_by=ahmed.id,
                approved_at=datetime.now(timezone.utc) - timedelta(days=5),
                created_by_agent="deema",
                created_via_channel="web",
            ))

        # Khalid on leave Wed-Thu (Apr 15-16)
        if khalid:
            approved_leaves.append(LeaveRequest(
                employee_id=khalid.id,
                approver_id=ahmed.id,
                leave_type=LeaveType.sick,
                start_date=date(2026, 4, 15),
                end_date=date(2026, 4, 16),
                business_days=2,
                reason="Medical appointment",
                status=LeaveStatus.approved,
                approved_by=ahmed.id,
                approved_at=datetime.now(timezone.utc) - timedelta(days=2),
                created_by_agent="deema",
                created_via_channel="web",
            ))

        # Noura full week next week (Apr 19-23)
        if noura:
            approved_leaves.append(LeaveRequest(
                employee_id=noura.id,
                approver_id=ahmed.id,
                leave_type=LeaveType.annual,
                start_date=date(2026, 4, 19),
                end_date=date(2026, 4, 23),
                business_days=5,
                reason="Annual vacation",
                status=LeaveStatus.approved,
                approved_by=ahmed.id,
                approved_at=datetime.now(timezone.utc) - timedelta(days=7),
                created_by_agent="deema",
                created_via_channel="web",
            ))

        # Ahmed himself has a leave request (pending) for testing "my leave requests"
        approved_leaves.append(LeaveRequest(
            employee_id=ahmed.id,
            approver_id=fatimah.id if fatimah else ahmed.id,
            leave_type=LeaveType.annual,
            start_date=date(2026, 4, 13),
            end_date=date(2026, 4, 14),
            business_days=2,
            reason="Personal errand",
            status=LeaveStatus.pending,
            created_by_agent="deema",
            created_via_channel="web",
        ))

        for lr in approved_leaves:
            db.add(lr)

        # ── Employee Documents for Ahmed (EMP-001) ──
        doc_records = [
            {
                "doc_type": DocumentType.national_id,
                "label": "Saudi National ID",
                "label_ar": "الهوية الوطنية",
                "filename": "ahmed_national_id.pdf",
                "expires_at": date(2028, 6, 15),
                "status": VerificationStatus.verified,
            },
            {
                "doc_type": DocumentType.passport,
                "label": "Passport",
                "label_ar": "جواز السفر",
                "filename": "ahmed_passport.pdf",
                "expires_at": date(2026, 5, 20),  # Expiring soon!
                "status": VerificationStatus.verified,
            },
            {
                "doc_type": DocumentType.contract,
                "label": "Employment Contract",
                "label_ar": "عقد العمل",
                "filename": "ahmed_contract_2023.pdf",
                "expires_at": None,
                "status": VerificationStatus.verified,
            },
            {
                "doc_type": DocumentType.gosi_cert,
                "label": "GOSI Certificate",
                "label_ar": "شهادة التأمينات الاجتماعية",
                "filename": "ahmed_gosi_cert.pdf",
                "expires_at": date(2026, 12, 31),
                "status": VerificationStatus.verified,
            },
            {
                "doc_type": DocumentType.medical_insurance,
                "label": "Medical Insurance Card",
                "label_ar": "بطاقة التأمين الطبي",
                "filename": "ahmed_medical_insurance.pdf",
                "expires_at": date(2026, 6, 1),  # Expiring in ~2 months
                "status": VerificationStatus.verified,
            },
            {
                "doc_type": DocumentType.education_cert,
                "label": "BSc Computer Science — KFUPM",
                "label_ar": "بكالوريوس علوم حاسب — جامعة الملك فهد",
                "filename": "ahmed_degree_cert.pdf",
                "expires_at": None,
                "status": VerificationStatus.verified,
            },
            {
                "doc_type": DocumentType.driving_license,
                "label": "Saudi Driving License",
                "label_ar": "رخصة القيادة",
                "filename": "ahmed_driving_license.pdf",
                "expires_at": date(2026, 4, 25),  # Expiring very soon!
                "status": VerificationStatus.pending,
            },
            {
                "doc_type": DocumentType.bank_letter,
                "label": "Bank Account Letter — Al Rajhi",
                "label_ar": "خطاب حساب بنكي — الراجحي",
                "filename": "ahmed_bank_letter.pdf",
                "expires_at": None,
                "status": VerificationStatus.verified,
            },
        ]

        for d in doc_records:
            # Create the parent Document record (file metadata stub)
            doc = Document(
                id=uuid4(),
                tenant_id=tenant_id,
                uploaded_by=ahmed.id,
                filename=d["filename"],
                original_filename=d["filename"],
                content_type="application/pdf",
                file_size=1024 * 50,  # 50KB stub
                storage_path=f"/uploads/{tenant_id}/{d['filename']}",
                category=DocumentCategory.employee_document,
                resource_type="employee",
                resource_id=ahmed.id,
            )
            db.add(doc)
            await db.flush()

            # Create the EmployeeDocument record
            emp_doc = EmployeeDocument(
                tenant_id=tenant_id,
                employee_id=ahmed.id,
                document_type=d["doc_type"],
                label=d["label"],
                label_ar=d["label_ar"],
                document_id=doc.id,
                original_filename=d["filename"],
                file_size=doc.file_size,
                mime_type=doc.content_type,
                expires_at=d["expires_at"],
                verification_status=d["status"],
                uploaded_by=ahmed.id,
                uploaded_via="seed",
            )
            db.add(emp_doc)

        await db.commit()

        print("Card demo data seeded successfully!")
        print()
        print("Team calendar (approved leaves):")
        print("  Omar     — Apr 12-14 (Sun-Tue) annual")
        print("  Khalid   — Apr 15-16 (Wed-Thu) sick")
        print("  Noura    — Apr 19-23 (Sun-Thu next week) annual")
        print("  Ahmed    — Apr 13-14 (pending, own request)")
        print()
        print(f"Documents for Ahmed (EMP-001): {len(doc_records)} documents")
        print("  Expiring soon: Passport (May 20), Medical (Jun 1), Driving License (Apr 25)")
        print()
        print("Test prompts:")
        print('  "Who is on leave this week?" → calendar view with Omar & Khalid bars')
        print('  "List my documents" → 8 documents with expiry badges')
        print('  "Do I have any expiring documents?" → 3 docs flagged')


if __name__ == "__main__":
    asyncio.run(seed())
