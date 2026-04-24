"""Daily document expiry check — creates notifications for employees with expiring documents."""
import logging
from datetime import date, timedelta, datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee
from app.models.employee_document import EmployeeDocument, DocumentType, EXPIRING_DOCUMENT_TYPES
from app.models.notification import Notification, NotificationCategory, NotificationPriority

logger = logging.getLogger(__name__)

# Arabic labels for document types
DOCUMENT_TYPE_AR = {
    DocumentType.iqama: "الإقامة",
    DocumentType.medical_insurance: "التأمين الطبي",
    DocumentType.passport: "جواز السفر",
    DocumentType.driving_license: "رخصة القيادة",
    DocumentType.national_id: "الهوية الوطنية",
    DocumentType.contract: "العقد",
    DocumentType.gosi_cert: "شهادة التأمينات",
    DocumentType.education_cert: "الشهادة العلمية",
    DocumentType.bank_letter: "خطاب البنك",
    DocumentType.other: "مستند آخر",
}

DOCUMENT_TYPE_EN = {
    DocumentType.iqama: "Iqama",
    DocumentType.medical_insurance: "Medical Insurance",
    DocumentType.passport: "Passport",
    DocumentType.driving_license: "Driving License",
    DocumentType.national_id: "National ID",
    DocumentType.contract: "Contract",
    DocumentType.gosi_cert: "GOSI Certificate",
    DocumentType.education_cert: "Education Certificate",
    DocumentType.bank_letter: "Bank Letter",
    DocumentType.other: "Other Document",
}

# Notification windows: (days_before_expiry, priority)
NOTIFICATION_WINDOWS = [
    (30, NotificationPriority.low),
    (14, NotificationPriority.normal),
    (7, NotificationPriority.high),
    (1, NotificationPriority.high),
]


async def check_expiring_documents(db: AsyncSession, tenant_id=None) -> int:
    """Check for documents expiring at 30, 14, 7, and 1 day windows.

    Creates Notification records for affected employees.
    If tenant_id is provided, only checks that tenant's documents.
    Returns the total number of notifications created.
    """
    today = date.today()
    total_created = 0

    for days_ahead, priority in NOTIFICATION_WINDOWS:
        target_date = today + timedelta(days=days_ahead)

        # Find documents expiring on this exact date
        filters = [
            EmployeeDocument.is_deleted.is_(False),
            EmployeeDocument.expires_at == target_date,
            EmployeeDocument.document_type.in_(
                [dt for dt in EXPIRING_DOCUMENT_TYPES]
            ),
        ]
        if tenant_id is not None:
            filters.append(EmployeeDocument.tenant_id == tenant_id)
        query = (
            select(EmployeeDocument, Employee)
            .join(Employee, EmployeeDocument.employee_id == Employee.id)
            .where(*filters)
        )
        result = await db.execute(query)
        rows = result.all()

        for doc, emp in rows:
            # Idempotency: skip if notification already created today for this doc+window
            existing_notif = await db.execute(
                select(func.count(Notification.id)).where(
                    Notification.resource_type == "employee_document",
                    Notification.resource_id == doc.id,
                    Notification.priority == priority,
                    func.date(Notification.created_at) == today,
                )
            )
            if existing_notif.scalar_one() > 0:
                continue

            type_ar = DOCUMENT_TYPE_AR.get(doc.document_type, doc.document_type.value)
            type_en = DOCUMENT_TYPE_EN.get(doc.document_type, doc.document_type.value)

            if days_ahead == 1:
                title = f"Document expiring tomorrow: {type_en}"
                title_ar = f"مستند ينتهي غداً: {type_ar}"
                body = (
                    f"Your {type_en} document expires tomorrow ({target_date.isoformat()}). "
                    "Please renew it as soon as possible and upload the updated document."
                )
                body_ar = (
                    f"مستند {type_ar} ينتهي غداً ({target_date.isoformat()}). "
                    "يرجى تجديده في أقرب وقت ممكن ورفع المستند المحدث."
                )
            else:
                title = f"Document expiring in {days_ahead} days: {type_en}"
                title_ar = f"مستند ينتهي خلال {days_ahead} يوم: {type_ar}"
                body = (
                    f"Your {type_en} document will expire on {target_date.isoformat()} "
                    f"({days_ahead} days from today). Please plan to renew it before expiry."
                )
                body_ar = (
                    f"مستند {type_ar} سينتهي بتاريخ {target_date.isoformat()} "
                    f"(خلال {days_ahead} يوم). يرجى التخطيط لتجديده قبل انتهاء الصلاحية."
                )

            notification = Notification(
                tenant_id=doc.tenant_id,
                employee_id=doc.employee_id,
                title=title,
                title_ar=title_ar,
                body=body,
                body_ar=body_ar,
                category=NotificationCategory.document,
                priority=priority,
                resource_type="employee_document",
                resource_id=doc.id,
            )
            db.add(notification)
            total_created += 1

        if rows:
            logger.info(
                "Created %d expiry notifications for %d-day window (target: %s)",
                len(rows), days_ahead, target_date,
            )

    if total_created > 0:
        await db.commit()

    logger.info("Document expiry check complete: %d notifications created", total_created)
    return total_created
