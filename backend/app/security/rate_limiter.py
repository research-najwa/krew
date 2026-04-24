"""Redis-backed sliding-window rate limiter."""
import asyncio
import ipaddress
import logging
import secrets
import time
from collections import defaultdict
from typing import Optional

import redis.asyncio as redis
from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_redis_pool: Optional[redis.Redis] = None

# ── In-memory fallback for when Redis is down ────────────────────
# dict of key -> list of timestamps (sliding window)
_memory_counters: dict[str, list[float]] = defaultdict(list)
_memory_last_cleanup: float = 0.0
_MEMORY_CLEANUP_INTERVAL = 30  # seconds between full cleanups
_memory_lock = asyncio.Lock()  # protects _memory_counters and _memory_last_cleanup

# ── Trusted proxy parsing ────────────────────────────────────────
_trusted_proxy_networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []


def _parse_trusted_proxies() -> None:
    """Parse TRUSTED_PROXIES setting into network objects (called once at import)."""
    global _trusted_proxy_networks
    raw = settings.trusted_proxies.strip()
    if not raw:
        return
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        try:
            _trusted_proxy_networks.append(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            logger.warning(f"Invalid trusted proxy entry, skipping: {entry}")


_parse_trusted_proxies()


def _is_trusted_proxy(ip_str: str) -> bool:
    """Check if an IP address falls within any trusted proxy network."""
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return any(addr in net for net in _trusted_proxy_networks)


async def get_redis() -> Optional[redis.Redis]:
    """Return (and lazily create) the singleton Redis connection pool."""
    global _redis_pool
    if _redis_pool is None:
        try:
            _redis_pool = redis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            await _redis_pool.ping()
            logger.info("Redis connected for rate limiting")
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}")
            _redis_pool = None
    return _redis_pool


async def close_redis() -> None:
    """Close the Redis connection pool on shutdown."""
    global _redis_pool
    if _redis_pool is not None:
        await _redis_pool.close()
        _redis_pool = None
        logger.info("Redis connection closed")


async def _check_memory_rate_limit(key: str, max_requests: int, window_seconds: int) -> bool:
    """In-memory sliding window fallback when Redis is unavailable.

    Returns True if request is allowed, False if rate-limited.
    """
    global _memory_last_cleanup
    async with _memory_lock:
        now = time.time()

        # Periodic cleanup of stale keys to prevent memory growth
        if now - _memory_last_cleanup > _MEMORY_CLEANUP_INTERVAL:
            _memory_last_cleanup = now
            # Use 900s staleness threshold — matches the longest window (login)
            # so counters are not prematurely evicted during Redis downtime.
            stale_keys = [
                k for k, timestamps in _memory_counters.items()
                if not timestamps or timestamps[-1] < now - 900
            ]
            for k in stale_keys:
                del _memory_counters[k]

        window_start = now - window_seconds
        timestamps = _memory_counters[key]
        # Remove expired entries
        _memory_counters[key] = [t for t in timestamps if t > window_start]
        _memory_counters[key].append(now)
        return len(_memory_counters[key]) <= max_requests


async def _check_rate_limit(
    key: str, max_requests: int, window_seconds: int, *, critical: bool = False
) -> bool:
    """Sliding window rate limit using Redis sorted sets.

    Returns True if the request is allowed, False if rate-limited.

    When Redis is unavailable:
    - If rate_limit_fail_mode is "closed" and critical=True: raises 503
    - Otherwise: falls back to in-memory counter
    """
    r = await get_redis()
    if r is None:
        if settings.rate_limit_fail_mode == "closed" and critical:
            raise HTTPException(
                status_code=503,
                detail="Service temporarily unavailable. Please try again later. / الخدمة غير متوفرة مؤقتا. يرجى المحاولة لاحقا.",
            )
        # Use in-memory fallback
        return await _check_memory_rate_limit(key, max_requests, window_seconds)

    try:
        now = time.time()
        window_start = now - window_seconds
        pipe = r.pipeline()
        pipe.zremrangebyscore(key, 0, window_start)
        member = f"{now}:{secrets.token_hex(4)}"
        pipe.zadd(key, {member: now})
        pipe.zcard(key)
        pipe.expire(key, window_seconds + 1)
        results = await pipe.execute()
        count = results[2]
        return count <= max_requests
    except Exception as e:
        logger.warning(f"Rate limit check failed: {e}")
        # Reset pool so next call re-connects
        global _redis_pool
        _redis_pool = None
        if settings.rate_limit_fail_mode == "closed" and critical:
            raise HTTPException(
                status_code=503,
                detail="Service temporarily unavailable. Please try again later. / الخدمة غير متوفرة مؤقتا. يرجى المحاولة لاحقا.",
            )
        return await _check_memory_rate_limit(key, max_requests, window_seconds)


def _raise_rate_limit(retry_after: int = 60) -> HTTPException:
    """Build a 429 HTTPException with bilingual detail and Retry-After."""
    raise HTTPException(
        status_code=429,
        detail="Too many requests. Please try again later. / طلبات كثيرة. يرجى المحاولة لاحقا.",
        headers={"Retry-After": str(retry_after)},
    )


async def check_login_rate_limit(request: Request, email: str) -> None:
    """5 login attempts per email per 15 minutes."""
    key = f"rl:login:{email.lower().strip()}"
    allowed = await _check_rate_limit(key, max_requests=5, window_seconds=900, critical=True)
    if not allowed:
        _raise_rate_limit(retry_after=900)


async def check_chat_rate_limit(employee_id: str) -> None:
    """20 chat messages per employee per minute."""
    key = f"rl:chat:{employee_id}"
    allowed = await _check_rate_limit(key, max_requests=20, window_seconds=60)
    if not allowed:
        _raise_rate_limit(retry_after=60)


async def check_chat_ip_rate_limit(request: Request) -> None:
    """60 chat messages per IP per minute — secondary limit keyed on trusted IP."""
    client_ip = _get_client_ip(request)
    key = f"rl:chat_ip:{client_ip}"
    allowed = await _check_rate_limit(key, max_requests=60, window_seconds=60)
    if not allowed:
        _raise_rate_limit(retry_after=60)


async def check_webhook_rate_limit(request: Request) -> None:
    """60 webhook requests per IP per minute."""
    client_ip = _get_client_ip(request)
    key = f"rl:webhook:{client_ip}"
    allowed = await _check_rate_limit(key, max_requests=60, window_seconds=60)
    if not allowed:
        _raise_rate_limit(retry_after=60)


async def check_global_rate_limit(request: Request) -> None:
    """100 requests per IP per minute."""
    client_ip = _get_client_ip(request)
    key = f"rl:global:{client_ip}"
    allowed = await _check_rate_limit(key, max_requests=100, window_seconds=60)
    if not allowed:
        _raise_rate_limit(retry_after=60)


def _get_client_ip(request: Request) -> str:
    """Extract client IP, only trusting X-Forwarded-For from known proxies."""
    direct_ip = request.client.host if request.client else "unknown"

    # Only trust X-Forwarded-For if the immediate connection is from a trusted proxy
    if _trusted_proxy_networks and _is_trusted_proxy(direct_ip):
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            # First IP in the chain is the original client
            return forwarded.split(",")[0].strip()

    return direct_ip


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Global rate limit middleware — skips health/root endpoints."""

    SKIP_PATHS = {"/", "/health"}

    async def dispatch(self, request: Request, call_next):
        # Skip WebSocket upgrades — BaseHTTPMiddleware can't handle them
        if request.scope.get("type") == "websocket":
            return await call_next(request)
        if request.url.path in self.SKIP_PATHS:
            return await call_next(request)

        try:
            await check_global_rate_limit(request)
        except HTTPException as e:
            return JSONResponse(
                status_code=e.status_code,
                content={"detail": e.detail},
                headers=e.headers or {},
            )
        except Exception as e:
            logger.warning(f"Rate limit middleware error: {e}")
            # Fail closed: reject on unexpected errors
            if settings.rate_limit_fail_mode == "closed":
                return JSONResponse(
                    status_code=503,
                    content={"detail": "Service temporarily unavailable."},
                )

        return await call_next(request)
