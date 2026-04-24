"""Token blacklist — Redis-backed with fail-closed behaviour in production.

When Redis is unavailable:
- In development (APP_ENV=development): falls back to per-process in-memory store.
- In production (blacklist_fail_mode=closed): raises HTTP 503 so tokens are NOT
  silently accepted. This prevents logout/password-change bypass in multi-worker
  deployments where in-memory state is not shared.
"""
import logging
import os
import time

from fastapi import HTTPException, status

from app.config import get_settings
from app.security.rate_limiter import get_redis

logger = logging.getLogger(__name__)

# In-memory fallbacks (used only in development mode)
_memory_blacklist: dict[str, int] = {}  # jti -> expiry timestamp
_memory_revoked_before: dict[str, int] = {}  # user_id -> revoked_before timestamp

_REVOKED_BEFORE_TTL = 7 * 24 * 3600  # 7 days


def _cleanup_memory_blacklist() -> None:
    """Remove expired entries from in-memory blacklist."""
    now = int(time.time())
    expired = [jti for jti, exp in _memory_blacklist.items() if exp <= now]
    for jti in expired:
        del _memory_blacklist[jti]


def _should_fail_closed() -> bool:
    """Return True if we should reject requests when Redis is unavailable."""
    settings = get_settings()
    return settings.app_env != "development" and settings.blacklist_fail_mode == "closed"


def _raise_service_unavailable(operation: str) -> None:
    """Raise HTTP 503 when Redis is down and fail-closed is active."""
    logger.critical(
        f"Token blacklist unavailable — Redis down, fail-closed active. "
        f"Operation: {operation}"
    )
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Authentication service temporarily unavailable. Please try again later.",
    )


def _warn_if_non_dev(operation: str) -> None:
    """Log CRITICAL if Redis is unavailable outside development."""
    settings = get_settings()
    if settings.app_env != "development":
        logger.critical(
            f"Token blacklist write failed — Redis unavailable. "
            f"Blacklist is not effective across workers. Operation: {operation}"
        )


async def blacklist_token(jti: str, exp_timestamp: int) -> bool:
    """Blacklist a single token by its jti. TTL = time until token expires.

    Returns True if this was a NEW blacklist entry, False if already existed.
    """
    ttl = max(exp_timestamp - int(time.time()), 1)

    try:
        r = await get_redis()
        if r is not None:
            # SET NX returns True if key was set (new entry), False if already existed
            was_new = await r.set(f"token:blacklist:{jti}", "1", ex=ttl, nx=True)
            return bool(was_new)
    except Exception as e:
        logger.warning(f"Redis blacklist_token failed: {e}")
        if _should_fail_closed():
            _raise_service_unavailable("blacklist_token")
        _warn_if_non_dev("blacklist_token")

    # In-memory fallback (development only if fail-closed is active)
    already_existed = jti in _memory_blacklist
    _memory_blacklist[jti] = exp_timestamp
    return not already_existed


async def is_blacklisted(jti: str) -> bool:
    """Check if a token jti has been blacklisted."""
    try:
        r = await get_redis()
        if r is not None:
            result = await r.exists(f"token:blacklist:{jti}")
            return bool(result)
    except Exception as e:
        logger.warning(f"Redis is_blacklisted check failed: {e}")
        if _should_fail_closed():
            _raise_service_unavailable("is_blacklisted")

    # In-memory fallback (development only if fail-closed is active)
    _cleanup_memory_blacklist()
    return jti in _memory_blacklist


async def blacklist_all_user_tokens(user_id: str) -> None:
    """Revoke all tokens for a user by setting a revoked_before timestamp."""
    now = int(time.time())

    try:
        r = await get_redis()
        if r is not None:
            await r.set(f"token:revoked_before:{user_id}", str(now), ex=_REVOKED_BEFORE_TTL)
            return
    except Exception as e:
        logger.warning(f"Redis blacklist_all_user_tokens failed: {e}")
        if _should_fail_closed():
            _raise_service_unavailable("blacklist_all_user_tokens")
        _warn_if_non_dev("blacklist_all_user_tokens")

    # In-memory fallback (development only if fail-closed is active)
    _memory_revoked_before[user_id] = now


async def is_token_revoked_for_user(user_id: str, iat: int) -> bool:
    """Check if a token was issued before the user's revoked_before timestamp.

    Uses <= so tokens issued in the same second as revocation are also invalidated.
    """
    try:
        r = await get_redis()
        if r is not None:
            revoked_before = await r.get(f"token:revoked_before:{user_id}")
            if revoked_before is not None:
                return iat <= int(revoked_before)
            return False
    except Exception as e:
        logger.warning(f"Redis is_token_revoked_for_user check failed: {e}")
        if _should_fail_closed():
            _raise_service_unavailable("is_token_revoked_for_user")

    # In-memory fallback (development only if fail-closed is active)
    revoked_before = _memory_revoked_before.get(user_id)
    if revoked_before is not None:
        return iat <= revoked_before
    return False
