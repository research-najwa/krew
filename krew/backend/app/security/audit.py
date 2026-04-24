"""Audit event emitter — best-effort, never raises.

Uses a dedicated database session so audit writes are committed independently
of the caller's transaction. This ensures audit events are not lost if the
caller's transaction rolls back.
"""
import logging
from uuid import UUID

from fastapi import Request

from app.models.audit_log import AuditLog
from app.database import async_session

logger = logging.getLogger(__name__)


async def emit_audit_event(
    db,  # kept for backward-compatible signature but not used for writes
    *,
    action: str,
    actor_id: str | None = None,
    actor_email: str | None = None,
    tenant_id: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    detail: dict | None = None,
    request: Request | None = None,
) -> None:
    """Record an audit event. Best-effort: logs warning on failure, never raises."""
    try:
        ip_address = None
        user_agent = None
        if request is not None:
            ip_address = request.client.host if request.client else None
            user_agent = request.headers.get("user-agent")
            if user_agent and len(user_agent) > 512:
                user_agent = user_agent[:512]

        entry = AuditLog(
            tenant_id=UUID(tenant_id) if tenant_id else None,
            actor_id=UUID(actor_id) if actor_id else None,
            actor_email=actor_email,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            detail=detail,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        async with async_session() as audit_db:
            audit_db.add(entry)
            await audit_db.commit()
    except Exception as e:
        logger.warning(f"Failed to emit audit event '{action}': {e}")
