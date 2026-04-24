"""HR Policy service — CRUD lifecycle, versioning, acknowledgments, and RAG embedding."""
import logging
import uuid
from datetime import datetime, date, timezone

from fastapi import HTTPException
from sqlalchemy import select, func, and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.hr_policy import HRPolicy, PolicyAcknowledgment, PolicyCategory, PolicyStatus
from app.models.employee import Employee, EmployeeStatus

logger = logging.getLogger(__name__)

# Finding 4: Per-tenant publish cooldown tracking (tenant_id -> last publish UTC timestamp)
_publish_cooldowns: dict[uuid.UUID, datetime] = {}
PUBLISH_COOLDOWN_SECONDS = 300  # 5 minutes


class PolicyService:
    """Manages HR policy CRUD, publishing lifecycle, and employee acknowledgments."""

    def __init__(self, db: AsyncSession, tenant_id: uuid.UUID):
        self.db = db
        self.tenant_id = tenant_id

    async def create_draft(
        self,
        title: str,
        title_ar: str | None,
        content: str,
        content_ar: str | None,
        category: str | PolicyCategory,
        effective_date: date,
        created_by: uuid.UUID | None = None,
    ) -> HRPolicy:
        """Create a new draft policy."""
        if isinstance(category, str):
            category = PolicyCategory(category)

        policy = HRPolicy(
            tenant_id=self.tenant_id,
            title=title,
            title_ar=title_ar,
            content=content,
            content_ar=content_ar,
            category=category,
            status=PolicyStatus.draft,
            effective_date=effective_date,
            created_by=created_by,
        )
        self.db.add(policy)
        await self.db.flush()
        logger.info("Draft policy created: id=%s title=%s", policy.id, title)
        return policy

    async def update_draft(self, policy_id: uuid.UUID, **updates) -> HRPolicy:
        """Update a draft policy. Only drafts can be updated."""
        policy = await self._get_policy_or_404(policy_id)
        if policy.status != PolicyStatus.draft:
            raise HTTPException(
                status_code=400,
                detail="Only draft policies can be edited.",
            )

        allowed_fields = {
            "title", "title_ar", "content", "content_ar",
            "category", "effective_date",
        }
        for field, value in updates.items():
            if field in allowed_fields:
                if field == "category" and isinstance(value, str):
                    value = PolicyCategory(value)
                setattr(policy, field, value)

        policy.updated_at = datetime.now(timezone.utc)  # Finding 21
        await self.db.flush()
        return policy

    async def publish(self, policy_id: uuid.UUID) -> HRPolicy:
        """Publish a draft policy. Enforces a 5-minute cooldown between publishes per tenant."""
        policy = await self._get_policy_or_404(policy_id)
        if policy.status != PolicyStatus.draft:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot publish a {policy.status.value} policy. Only drafts can be published.",
            )

        # Finding 4: Per-tenant publish cooldown to prevent notification bombing
        now = datetime.now(timezone.utc)
        last_publish = _publish_cooldowns.get(self.tenant_id)
        if last_publish:
            elapsed = (now - last_publish).total_seconds()
            if elapsed < PUBLISH_COOLDOWN_SECONDS:
                remaining = int(PUBLISH_COOLDOWN_SECONDS - elapsed)
                raise HTTPException(
                    status_code=429,
                    detail=f"Please wait {remaining} seconds before publishing another policy. / يرجى الانتظار {remaining} ثانية قبل نشر سياسة أخرى.",
                )

        policy.status = PolicyStatus.published
        policy.published_at = now
        policy.updated_at = now
        await self.db.flush()

        # Record publish time for cooldown enforcement
        _publish_cooldowns[self.tenant_id] = now

        # Generate RAG embedding (best-effort, do not block publish)
        # Finding 8: Log warning for cost monitoring
        logger.warning("Generating embedding for policy %s — monitor for excessive usage", policy_id)
        try:
            await self.generate_embedding(policy_id)
        except Exception as e:
            logger.warning("Failed to generate embedding for policy %s: %s", policy_id, e)

        # Finding 24: Notify all active employees in the tenant about new policy
        try:
            from app.services.notification import NotificationService
            notif_svc = NotificationService(self.db, self.tenant_id)

            emp_result = await self.db.execute(
                select(Employee.id).where(
                    Employee.tenant_id == self.tenant_id,
                    Employee.status == EmployeeStatus.active,
                )
            )
            employee_ids = [row[0] for row in emp_result.all()]

            if employee_ids:
                await notif_svc.send_bulk(
                    employee_ids=employee_ids,
                    title=f"New Policy Published: {policy.title}",
                    title_ar=f"سياسة جديدة منشورة: {policy.title_ar or policy.title}",
                    body=f"A new policy '{policy.title}' has been published. Please review and acknowledge.",
                    body_ar=f"تم نشر سياسة جديدة '{policy.title_ar or policy.title}'. يرجى المراجعة والتأكيد.",
                    category="policy",
                    resource_type="hr_policy",
                    resource_id=policy.id,
                )
        except Exception as e:
            logger.warning("Failed to send policy publish notifications: %s", e)

        logger.info("Policy published: id=%s title=%s", policy.id, policy.title)
        return policy

    async def archive(self, policy_id: uuid.UUID) -> HRPolicy:
        """Archive a published policy. Finding 17: Only published policies can be archived."""
        policy = await self._get_policy_or_404(policy_id)
        if policy.status != PolicyStatus.published:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot archive a {policy.status.value} policy. Only published policies can be archived.",
            )

        policy.status = PolicyStatus.archived
        policy.archived_at = datetime.now(timezone.utc)  # Finding 21
        policy.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        logger.info("Policy archived: id=%s", policy.id)
        return policy

    async def create_new_version(self, policy_id: uuid.UUID) -> HRPolicy:
        """Create a new draft version from a published policy."""
        parent = await self._get_policy_or_404(policy_id)
        if parent.status != PolicyStatus.published:
            raise HTTPException(
                status_code=400,
                detail="Can only create a new version from a published policy.",
            )

        new_policy = HRPolicy(
            tenant_id=self.tenant_id,
            title=parent.title,
            title_ar=parent.title_ar,
            content=parent.content,
            content_ar=parent.content_ar,
            category=parent.category,
            status=PolicyStatus.draft,
            version=parent.version + 1,
            parent_id=parent.id,
            effective_date=parent.effective_date,
            created_by=parent.created_by,
        )
        self.db.add(new_policy)
        # Finding 20: Handle race condition on duplicate version creation
        try:
            await self.db.flush()
        except IntegrityError:
            await self.db.rollback()
            raise HTTPException(
                status_code=409,
                detail="A new version is already being created for this policy.",
            )
        logger.info(
            "New version created: id=%s version=%d parent=%s",
            new_policy.id, new_policy.version, policy_id,
        )
        return new_policy

    async def list_policies(
        self,
        category: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[HRPolicy]:
        """List policies with optional filters, tenant-scoped."""
        query = (
            select(HRPolicy)
            .where(HRPolicy.tenant_id == self.tenant_id)
            .order_by(HRPolicy.created_at.desc())
            .offset(offset)
            .limit(limit)
        )

        if category:
            try:
                cat_enum = PolicyCategory(category)
                query = query.where(HRPolicy.category == cat_enum)
            except ValueError:
                pass
        if status:
            try:
                status_enum = PolicyStatus(status)
                query = query.where(HRPolicy.status == status_enum)
            except ValueError:
                pass

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_policy(self, policy_id: uuid.UUID) -> HRPolicy:
        """Fetch a single policy by ID."""
        return await self._get_policy_or_404(policy_id)

    async def acknowledge(
        self,
        policy_id: uuid.UUID,
        employee_id: uuid.UUID,
        ip_address: str | None = None,
    ) -> PolicyAcknowledgment:
        """Record an employee's acknowledgment of a policy."""
        policy = await self._get_policy_or_404(policy_id)
        if policy.status != PolicyStatus.published:
            raise HTTPException(
                status_code=400,
                detail="Can only acknowledge published policies.",
            )

        ack = PolicyAcknowledgment(
            tenant_id=self.tenant_id,
            policy_id=policy_id,
            employee_id=employee_id,
            ip_address=ip_address,
        )
        self.db.add(ack)
        # Finding 14: Handle race condition on duplicate acknowledgment
        try:
            await self.db.flush()
        except IntegrityError:
            await self.db.rollback()
            raise HTTPException(
                status_code=409,
                detail="You have already acknowledged this policy.",
            )
        return ack

    async def get_acknowledgment_status(self, policy_id: uuid.UUID) -> dict:
        """Count acknowledged vs total active employees for a policy."""
        # Finding 23: Count acknowledgments only from active employees
        ack_count_result = await self.db.execute(
            select(func.count(PolicyAcknowledgment.id))
            .join(Employee, PolicyAcknowledgment.employee_id == Employee.id)
            .where(
                PolicyAcknowledgment.policy_id == policy_id,
                PolicyAcknowledgment.tenant_id == self.tenant_id,
                Employee.status == EmployeeStatus.active,
            )
        )
        acknowledged = ack_count_result.scalar_one()

        # Count total active employees in tenant
        total_result = await self.db.execute(
            select(func.count(Employee.id)).where(
                Employee.tenant_id == self.tenant_id,
                Employee.status == EmployeeStatus.active,
            )
        )
        total = total_result.scalar_one()

        return {
            "policy_id": str(policy_id),
            "acknowledged": acknowledged,
            "total_active_employees": total,
            "pending": max(0, total - acknowledged),  # Finding 23: floor at 0
        }

    async def get_pending_acknowledgments(self, employee_id: uuid.UUID) -> list[HRPolicy]:
        """Get published policies not yet acknowledged by this employee."""
        # Finding 10: Add tenant_id filter to the subquery
        acked_subq = (
            select(PolicyAcknowledgment.policy_id)
            .where(
                PolicyAcknowledgment.employee_id == employee_id,
                PolicyAcknowledgment.tenant_id == self.tenant_id,
            )
            .scalar_subquery()
        )

        result = await self.db.execute(
            select(HRPolicy).where(
                HRPolicy.tenant_id == self.tenant_id,
                HRPolicy.status == PolicyStatus.published,
                HRPolicy.id.notin_(acked_subq),
            )
            .order_by(HRPolicy.published_at.desc())
        )
        return list(result.scalars().all())

    async def generate_embedding(self, policy_id: uuid.UUID) -> None:
        """Generate RAG embedding for a policy using the existing ingestor.

        Finding 9: Use the public ingest_document method instead of private methods.
        """
        policy = await self._get_policy_or_404(policy_id)

        # Combine English and Arabic content for embedding
        content_parts = [policy.content]
        if policy.content_ar:
            content_parts.append(policy.content_ar)
        full_content = "\n\n".join(content_parts)

        if not full_content.strip():
            logger.warning("Policy %s has no content for embedding", policy_id)
            return

        try:
            from app.rag.ingest import PolicyIngestor
            ingestor = PolicyIngestor(self.db)
            await ingestor.ingest_document(
                tenant_id=self.tenant_id,
                title=policy.title,
                category=policy.category.value,
                content=full_content,
                source_filename=f"hr_policy_{policy.id}",
            )
            logger.info("Generated embedding for HR policy %s", policy_id)
        except Exception as e:
            logger.error("Failed to generate embeddings for policy %s: %s", policy_id, e)
            raise

    async def _get_policy_or_404(self, policy_id: uuid.UUID) -> HRPolicy:
        """Fetch a policy by ID with tenant isolation, or raise 404."""
        result = await self.db.execute(
            select(HRPolicy).where(
                HRPolicy.id == policy_id,
                HRPolicy.tenant_id == self.tenant_id,
            )
        )
        policy = result.scalar_one_or_none()
        if not policy:
            raise HTTPException(status_code=404, detail="Policy not found.")
        return policy
