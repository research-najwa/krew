"""HMAC signature verification for WhatsApp and Slack webhooks."""
import asyncio
import hashlib
import hmac
import json
import logging
import time
from typing import Optional

import redis.asyncio as redis
from fastapi import HTTPException, Request

from app.config import get_settings

logger = logging.getLogger("krew.security")
settings = get_settings()

# ── Replay protection: seen-signature cache ──────────────────────
_seen_signatures: dict[str, float] = {}
_seen_last_cleanup: float = 0.0
_REPLAY_WINDOW_SECONDS = 300  # 5 minutes
_replay_lock = asyncio.Lock()  # protects _seen_signatures and _seen_last_cleanup


async def _check_replay_memory(signature: str) -> bool:
    """In-memory replay check. Returns True if this is a replay (already seen)."""
    global _seen_last_cleanup
    async with _replay_lock:
        now = time.time()

        # Periodic cleanup of expired entries
        if now - _seen_last_cleanup > 60:
            _seen_last_cleanup = now
            cutoff = now - _REPLAY_WINDOW_SECONDS
            stale = [k for k, ts in _seen_signatures.items() if ts < cutoff]
            for k in stale:
                del _seen_signatures[k]

        if signature in _seen_signatures:
            return True

        _seen_signatures[signature] = now
        return False


async def _check_replay_redis(signature_hash: str) -> bool:
    """Redis-based replay check with TTL. Returns True if replay detected."""
    try:
        from app.security.rate_limiter import get_redis
        r = await get_redis()
        if r is not None:
            key = f"webhook:seen:{signature_hash}"
            # SET with NX returns True only if key was newly set
            was_new = await r.set(key, "1", nx=True, ex=_REPLAY_WINDOW_SECONDS)
            return not was_new  # if was_new is False/None, it's a replay
    except Exception as e:
        logger.warning(f"Redis replay check failed, falling back to in-memory: {e}")
    # Fall back to in-memory check
    return await _check_replay_memory(signature_hash)


async def verify_whatsapp_signature(request: Request) -> bytes:
    """Validate X-Hub-Signature-256 using whatsapp_app_secret.

    Returns the raw body bytes for downstream parsing.
    Skips verification only in development mode when webhook_skip_verification is explicitly True.
    """
    body = await request.body()

    # Skip only in dev when explicitly opted in via webhook_skip_verification
    if (
        settings.app_env == "development"
        and settings.webhook_skip_verification
        and not settings.whatsapp_app_secret
    ):
        logger.warning("SECURITY: WhatsApp webhook signature verification DISABLED (development mode, explicit skip)")
        return body

    # In non-dev, the secret must be configured (enforced at startup in main.py)
    if not settings.whatsapp_app_secret:
        logger.error("WhatsApp app secret not configured")
        raise HTTPException(status_code=500, detail="Webhook verification not configured")

    signature_header = request.headers.get("X-Hub-Signature-256", "")
    if not signature_header:
        logger.warning("WhatsApp webhook missing X-Hub-Signature-256 header")
        raise HTTPException(status_code=401, detail="Missing signature")

    # Header format: "sha256=<hex_digest>"
    if not signature_header.startswith("sha256="):
        raise HTTPException(status_code=401, detail="Invalid signature format")

    expected_sig = signature_header[7:]  # strip "sha256="
    computed_sig = hmac.new(
        settings.whatsapp_app_secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(computed_sig, expected_sig):
        logger.warning("WhatsApp webhook signature mismatch")
        raise HTTPException(status_code=401, detail="Invalid signature")

    # ── Replay protection ────────────────────────────────────────
    # Try to extract timestamp from WhatsApp payload for time-based check
    replay_detected = False
    try:
        payload = json.loads(body)
        # WhatsApp Cloud API includes timestamp in message entries
        entries = payload.get("entry", [])
        for entry in entries:
            changes = entry.get("changes", [])
            for change in changes:
                value = change.get("value", {})
                # Check both messages and statuses for timestamp validity
                items = value.get("messages", []) + value.get("statuses", [])
                for item in items:
                    ts_str = item.get("timestamp")
                    if ts_str:
                        ts = int(ts_str)
                        if abs(time.time() - ts) > _REPLAY_WINDOW_SECONDS:
                            logger.warning("WhatsApp webhook timestamp too old (possible replay)")
                            replay_detected = True
                            break
                if replay_detected:
                    break
            if replay_detected:
                break
    except (json.JSONDecodeError, ValueError, TypeError):
        pass

    if replay_detected:
        raise HTTPException(status_code=401, detail="Request too old")

    # Also check signature hash to prevent exact payload replay within window
    sig_hash = hashlib.sha256(expected_sig.encode()).hexdigest()
    if await _check_replay_redis(sig_hash):
        logger.warning("WhatsApp webhook replay detected (duplicate signature)")
        raise HTTPException(status_code=401, detail="Duplicate request")

    return body


async def verify_slack_signature(request: Request) -> bytes:
    """Validate X-Slack-Signature with replay protection (5 min window).

    Returns the raw body bytes for downstream parsing.
    Skips verification only in development mode when webhook_skip_verification is explicitly True.
    """
    body = await request.body()

    # Skip only in dev when explicitly opted in via webhook_skip_verification
    if (
        settings.app_env == "development"
        and settings.webhook_skip_verification
        and not settings.slack_signing_secret
    ):
        logger.warning("SECURITY: Slack webhook signature verification DISABLED (development mode, explicit skip)")
        return body

    # In non-dev, the secret must be configured (enforced at startup in main.py)
    if not settings.slack_signing_secret:
        logger.error("Slack signing secret not configured")
        raise HTTPException(status_code=500, detail="Webhook verification not configured")

    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")

    if not timestamp or not signature:
        logger.warning("Slack webhook missing signature headers")
        raise HTTPException(status_code=401, detail="Missing signature headers")

    # Replay protection: reject requests older than 5 minutes
    try:
        ts = int(timestamp)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid timestamp")

    if abs(time.time() - ts) > 300:
        logger.warning("Slack webhook timestamp too old (possible replay)")
        raise HTTPException(status_code=401, detail="Request too old")

    # Compute expected signature: v0=HMAC-SHA256(secret, "v0:{timestamp}:{body}")
    try:
        body_str = body.decode('utf-8')
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="Invalid request body encoding")
    sig_basestring = f"v0:{timestamp}:{body_str}"
    computed_sig = "v0=" + hmac.new(
        settings.slack_signing_secret.encode("utf-8"),
        sig_basestring.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(computed_sig, signature):
        logger.warning("Slack webhook signature mismatch")
        raise HTTPException(status_code=401, detail="Invalid signature")

    return body
