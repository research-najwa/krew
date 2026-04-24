"""Notification delivery dispatcher — routes notifications to email, WhatsApp, Slack."""
import html
import logging
import uuid
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import async_session
from app.models.employee import Employee
from app.models.notification import Notification, NotificationChannel

logger = logging.getLogger(__name__)
settings = get_settings()


class NotificationDispatcher:
    """Dispatches notification delivery to the appropriate channel."""

    def __init__(self, db: AsyncSession, tenant_id: uuid.UUID | None = None):
        self.db = db
        self.tenant_id = tenant_id

    async def dispatch(self, notification_id: uuid.UUID) -> None:
        """Load notification and route to the appropriate channel for delivery."""
        filters = [Notification.id == notification_id]
        if self.tenant_id is not None:
            filters.append(Notification.tenant_id == self.tenant_id)
        result = await self.db.execute(
            select(Notification).where(*filters)
        )
        notification = result.scalar_one_or_none()
        if not notification:
            logger.error("Notification %s not found for dispatch", notification_id)
            return

        # Load employee (always filter by the notification's tenant)
        emp_filters = [Employee.id == notification.employee_id]
        if notification.tenant_id is not None:
            emp_filters.append(Employee.tenant_id == notification.tenant_id)
        result = await self.db.execute(
            select(Employee).where(*emp_filters)
        )
        employee = result.scalar_one_or_none()
        if not employee:
            await self._mark_failed(notification, "Employee not found")
            return

        channel = notification.channel

        # in_app needs no external delivery — mark delivered immediately
        if channel == NotificationChannel.in_app:
            await self._mark_delivered(notification)
            return

        try:
            if channel == NotificationChannel.email:
                await self._send_email(notification, employee)
            elif channel == NotificationChannel.whatsapp:
                await self._send_whatsapp(notification, employee)
            elif channel == NotificationChannel.slack:
                await self._send_slack(notification, employee)
            else:
                await self._mark_failed(notification, f"Unknown channel: {channel}")
        except Exception as exc:
            logger.exception("Dispatch failed for notification %s", notification_id)
            await self._mark_failed(notification, str(exc))

    async def _send_email(self, notification: Notification, employee: Employee) -> None:
        """Send notification via email using aiosmtplib."""
        if not settings.smtp_host:
            logger.warning(
                "SMTP not configured — skipping email delivery for notification %s",
                notification.id,
            )
            await self._mark_failed(notification, "SMTP not configured")
            return

        import aiosmtplib

        # Build bilingual HTML body
        title_line = html.escape(notification.title)
        if notification.title_ar:
            title_line = f"{html.escape(notification.title_ar)} / {html.escape(notification.title)}"

        body_line = html.escape(notification.body)
        if notification.body_ar:
            body_line = f"{html.escape(notification.body_ar)}<br/><br/>{html.escape(notification.body)}"

        html_content = f"""
        <html dir="auto">
        <body style="font-family: 'Inter', Arial, sans-serif; max-width: 600px; margin: auto; padding: 20px;">
            <h2 style="color: #1a1a2e;">{title_line}</h2>
            <p style="color: #333; line-height: 1.6;">{body_line}</p>
            <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;"/>
            <p style="color: #999; font-size: 12px;">Krew HR — Saudi Arabia</p>
        </body>
        </html>
        """

        msg = MIMEMultipart("alternative")
        msg["Subject"] = title_line
        msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
        msg["To"] = employee.email
        msg.attach(MIMEText(html_content, "html", "utf-8"))

        try:
            await aiosmtplib.send(
                msg,
                hostname=settings.smtp_host,
                port=settings.smtp_port,
                username=settings.smtp_username or None,
                password=settings.smtp_password or None,
                start_tls=True,
            )
            await self._mark_delivered(notification)
            logger.info("Email sent for notification %s to %s", notification.id, employee.email)
        except Exception as exc:
            raise RuntimeError(f"Email send failed: {exc}") from exc

    async def _send_whatsapp(self, notification: Notification, employee: Employee) -> None:
        """Send notification via Meta Cloud API (WhatsApp)."""
        if not settings.whatsapp_access_token:
            logger.warning(
                "WhatsApp token not configured — skipping delivery for notification %s",
                notification.id,
            )
            await self._mark_failed(notification, "WhatsApp token not configured")
            return

        if not employee.whatsapp_number:
            await self._mark_failed(notification, "Employee has no WhatsApp number")
            return

        # Prefer Arabic body, fall back to English
        body_text = self._escape_whatsapp(notification.body_ar or notification.body)
        phone_id = settings.whatsapp_phone_number_id
        url = f"https://graph.facebook.com/v18.0/{phone_id}/messages"

        payload = {
            "messaging_product": "whatsapp",
            "to": employee.whatsapp_number,
            "type": "text",
            "text": {"body": body_text},
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                url,
                json=payload,
                headers={"Authorization": f"Bearer {settings.whatsapp_access_token}"},
            )

        if resp.status_code in (200, 201):
            await self._mark_delivered(notification)
            logger.info("WhatsApp sent for notification %s to %s", notification.id, employee.whatsapp_number)
        else:
            raise RuntimeError(
                f"WhatsApp API error {resp.status_code}: {resp.text}"
            )

    async def _send_slack(self, notification: Notification, employee: Employee) -> None:
        """Send notification via Slack Web API."""
        if not settings.slack_bot_token:
            logger.warning(
                "Slack token not configured — skipping delivery for notification %s",
                notification.id,
            )
            await self._mark_failed(notification, "Slack bot token not configured")
            return

        if not employee.slack_user_id:
            await self._mark_failed(notification, "Employee has no Slack user ID")
            return

        # Prefer Arabic, fall back to English
        title_text = self._escape_slack_mrkdwn(notification.title_ar or notification.title)
        body_text = self._escape_slack_mrkdwn(notification.body_ar or notification.body)
        message = f"*{title_text}*\n{body_text}"

        url = "https://slack.com/api/chat.postMessage"
        payload = {
            "channel": employee.slack_user_id,
            "text": message,
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                url,
                json=payload,
                headers={"Authorization": f"Bearer {settings.slack_bot_token}"},
            )

        data = resp.json()
        if resp.status_code == 200 and data.get("ok"):
            await self._mark_delivered(notification)
            logger.info("Slack sent for notification %s to %s", notification.id, employee.slack_user_id)
        else:
            error = data.get("error", resp.text)
            raise RuntimeError(f"Slack API error: {error}")

    @staticmethod
    def _escape_whatsapp(text: str) -> str:
        """Escape WhatsApp formatting metacharacters."""
        for ch in ("*", "_", "~"):
            text = text.replace(ch, f"\u200b{ch}")
        return text

    @staticmethod
    def _escape_slack_mrkdwn(text: str) -> str:
        """Escape Slack mrkdwn metacharacters."""
        for ch in ("*", "_", "~", ">", "@", "#"):
            text = text.replace(ch, f"\u200b{ch}")
        return text

    async def _mark_delivered(self, notification: Notification) -> None:
        """Mark notification as successfully delivered."""
        notification.delivery_status = "delivered"
        notification.delivered_at = datetime.now(timezone.utc)
        notification.delivery_attempts = (notification.delivery_attempts or 0) + 1
        await self.db.commit()

    async def _mark_failed(self, notification: Notification, error: str) -> None:
        """Mark notification delivery as failed."""
        notification.delivery_status = "failed"
        notification.delivery_error = error
        notification.delivery_attempts = (notification.delivery_attempts or 0) + 1
        await self.db.commit()

    async def retry_failed(self, max_attempts: int = 3) -> int:
        """Retry failed notifications that haven't exceeded max attempts.

        Returns count of notifications retried.
        """
        filters = [
            Notification.delivery_status == "failed",
            Notification.delivery_attempts < max_attempts,
        ]
        if self.tenant_id is not None:
            filters.append(Notification.tenant_id == self.tenant_id)
        result = await self.db.execute(
            select(Notification).where(*filters)
        )
        failed = list(result.scalars().all())

        retried = 0
        for notification in failed:
            # Reset status to pending before retrying
            notification.delivery_status = "pending"
            notification.delivery_error = None
            await self.db.commit()

            await self.dispatch(notification.id)
            retried += 1

        return retried


async def dispatch_notification(notification_id: uuid.UUID) -> None:
    """Standalone function for use as a BackgroundTask.

    Creates its own DB session so it can run independently of the request lifecycle.
    """
    async with async_session() as db:
        # Load the notification's tenant_id so the dispatcher can scope queries
        result = await db.execute(
            select(Notification.tenant_id).where(Notification.id == notification_id)
        )
        row = result.one_or_none()
        tenant_id = row[0] if row else None

        dispatcher = NotificationDispatcher(db, tenant_id=tenant_id)
        try:
            await dispatcher.dispatch(notification_id)
        except Exception:
            logger.exception("Background dispatch failed for notification %s", notification_id)
