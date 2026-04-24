"""Webhook API key verification — validates X-API-Key header on inbound webhooks."""
import hmac
import logging

from fastapi import HTTPException, Request

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_CHANNEL_KEY_MAP = {
    "whatsapp": lambda: settings.whatsapp_webhook_api_key,
    "slack": lambda: settings.slack_webhook_api_key,
}


async def verify_webhook_api_key(request: Request, channel: str) -> None:
    """Verify the X-API-Key header against the configured key for the channel.

    - In development with no key configured: skip silently.
    - In non-dev with no key configured: return HTTP 500.
    - Missing or wrong key: return HTTP 401.
    """
    key_getter = _CHANNEL_KEY_MAP.get(channel)
    if not key_getter:
        raise HTTPException(status_code=400, detail="Unsupported webhook channel")

    configured_key = key_getter()

    if not configured_key:
        if settings.app_env == "development":
            return  # Skip silently in development
        raise HTTPException(
            status_code=500,
            detail=f"Webhook API key not configured for {channel}",
        )

    provided_key = request.headers.get("X-API-Key", "")
    if not provided_key:
        raise HTTPException(
            status_code=401,
            detail="Missing X-API-Key header",
        )

    if not hmac.compare_digest(provided_key, configured_key):
        raise HTTPException(
            status_code=401,
            detail="Invalid API key",
        )
