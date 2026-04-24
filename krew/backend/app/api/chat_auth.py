"""Chat authentication — employee login/verify/logout for the web chat UI."""
import hmac
import logging
import time
from collections import defaultdict

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.employee import Employee
from app.auth.jwt import create_chat_token, decode_token
from app.auth.chat_dependencies import get_chat_employee, ChatEmployee, _chat_bearer
from app.auth.token_blacklist import blacklist_token
from app.security.rate_limiter import check_chat_ip_rate_limit, get_redis

logger = logging.getLogger(__name__)

# ── Login lockout constants ─────────────────────────────────────────
_LOGIN_MAX_FAILURES = 5
_LOGIN_LOCKOUT_SECONDS = 900  # 15 minutes
_REDIS_KEY_PREFIX = "krew:login_fail:"

# ── In-memory fallback for when Redis is down ───────────────────────
_login_failures: dict[str, list[float]] = defaultdict(list)

router = APIRouter(prefix="/chat/auth", tags=["chat-auth"])


class LoginRequest(BaseModel):
    employee_number: str = Field(..., min_length=1, max_length=50)
    national_id_last4: str = Field(..., min_length=4, max_length=4, pattern=r"^\d{4}$")


class LoginResponse(BaseModel):
    token: str
    employee_id: str
    tenant_id: str
    name: str
    name_ar: str | None
    language: str


class VerifyResponse(BaseModel):
    employee_id: str
    name: str


async def _check_login_lockout(employee_number: str) -> None:
    """Raise 429 if the employee_number has exceeded failed login attempts.

    Uses Redis when available, falls back to in-memory dict.
    """
    r = await get_redis()
    if r is not None:
        try:
            key = f"{_REDIS_KEY_PREFIX}{employee_number}"
            count = await r.get(key)
            if count is not None and int(count) >= _LOGIN_MAX_FAILURES:
                raise HTTPException(
                    status_code=429,
                    detail="Too many failed attempts. Please try again later. / محاولات كثيرة. يرجى المحاولة لاحقا.",
                    headers={"Retry-After": str(_LOGIN_LOCKOUT_SECONDS)},
                )
            return
        except HTTPException:
            raise
        except Exception:
            logger.warning("Redis read failed for login lockout, falling back to in-memory")

    # In-memory fallback
    now = time.time()
    window_start = now - _LOGIN_LOCKOUT_SECONDS
    _login_failures[employee_number] = [
        t for t in _login_failures[employee_number] if t > window_start
    ]
    if len(_login_failures[employee_number]) >= _LOGIN_MAX_FAILURES:
        raise HTTPException(
            status_code=429,
            detail="Too many failed attempts. Please try again later. / محاولات كثيرة. يرجى المحاولة لاحقا.",
            headers={"Retry-After": str(_LOGIN_LOCKOUT_SECONDS)},
        )


async def _record_login_failure(employee_number: str) -> None:
    """Record a failed login attempt. Redis with in-memory fallback."""
    r = await get_redis()
    if r is not None:
        try:
            key = f"{_REDIS_KEY_PREFIX}{employee_number}"
            await r.incr(key)
            await r.expire(key, _LOGIN_LOCKOUT_SECONDS)
            return
        except Exception:
            logger.warning("Redis write failed for login lockout, falling back to in-memory")

    # In-memory fallback
    _login_failures[employee_number].append(time.time())


async def _clear_login_failures(employee_number: str) -> None:
    """Clear login failure count on successful login. Redis with in-memory fallback."""
    r = await get_redis()
    if r is not None:
        try:
            key = f"{_REDIS_KEY_PREFIX}{employee_number}"
            await r.delete(key)
            return
        except Exception:
            logger.warning("Redis delete failed for login lockout, falling back to in-memory")

    # In-memory fallback
    _login_failures.pop(employee_number, None)


@router.post("/login", response_model=LoginResponse)
async def chat_login(req: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Authenticate an employee for web chat using employee_number + last 4 of national_id."""
    # IP-based rate limit
    await check_chat_ip_rate_limit(request)

    # Per-employee-number lockout
    await _check_login_lockout(req.employee_number)

    result = await db.execute(
        select(Employee).where(
            Employee.employee_number == req.employee_number,
            Employee.status == "active",
        )
    )
    employee = result.scalar_one_or_none()

    # Constant-time comparison to prevent timing attacks.
    # Always compare even if employee is None so response time is uniform.
    expected = (
        employee.national_id[-4:]
        if employee and employee.national_id and len(employee.national_id) >= 4
        else "0000"
    )
    credentials_valid = employee is not None and hmac.compare_digest(
        expected.encode(), req.national_id_last4.encode()
    )

    if not credentials_valid:
        await _record_login_failure(req.employee_number)
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials. / بيانات الدخول غير صحيحة.",
        )

    # Clear lockout counter on successful login
    await _clear_login_failures(req.employee_number)

    token = create_chat_token(
        employee_id=employee.id,
        tenant_id=employee.tenant_id,
        name=employee.full_name,
    )

    # Build Arabic name safely — avoid "None" when last_name_ar is null
    name_ar = None
    if employee.first_name_ar:
        parts = [employee.first_name_ar]
        if employee.last_name_ar:
            parts.append(employee.last_name_ar)
        name_ar = " ".join(parts)

    return LoginResponse(
        token=token,
        employee_id=str(employee.id),
        tenant_id=str(employee.tenant_id),
        name=employee.full_name,
        name_ar=name_ar,
        language=employee.preferred_language,
    )


@router.get("/verify", response_model=VerifyResponse)
async def verify_chat_token(
    emp: ChatEmployee = Depends(get_chat_employee),
):
    """Verify an existing chat token is still valid."""
    return VerifyResponse(
        employee_id=str(emp.employee_id),
        name=emp.employee_name,
    )


@router.post("/logout")
async def chat_logout(
    emp: ChatEmployee = Depends(get_chat_employee),
    credentials: HTTPAuthorizationCredentials = Depends(_chat_bearer),
):
    """Logout — blacklist the chat token so it cannot be reused."""
    token = credentials.credentials
    try:
        payload = decode_token(token)
        jti = payload.get("jti")
        exp = payload.get("exp", 0)
        if jti:
            await blacklist_token(jti, int(exp))
    except Exception:
        # Token is already invalid or expired — logout succeeds regardless
        logger.debug("Token decode failed during logout — proceeding anyway")

    return {"status": "logged_out"}
