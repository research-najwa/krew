"""Chat-specific auth dependency — separate from admin auth."""
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, ExpiredSignatureError

from app.auth.jwt import decode_token
from app.auth.token_blacklist import is_blacklisted

# auto_error=False so unauthenticated requests get a clear 401 instead of
# FastAPI's default 403 when no Authorization header is present.
_chat_bearer = HTTPBearer(auto_error=False)


@dataclass
class ChatEmployee:
    """Minimal identity extracted from a chat JWT."""
    employee_id: UUID
    tenant_id: UUID
    employee_name: str


async def get_chat_employee(
    credentials: HTTPAuthorizationCredentials | None = Depends(_chat_bearer),
) -> ChatEmployee:
    """Validate a chat JWT and return the employee identity.

    This is intentionally decoupled from the admin get_current_user dependency
    so that chat tokens (type="chat") are never accepted by admin endpoints
    and vice-versa.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    try:
        payload = decode_token(token)
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if payload.get("type") != "chat":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check token blacklist (jti) — mirrors admin auth pattern
    jti = payload.get("jti")
    if jti and await is_blacklisted(jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        employee_id = UUID(payload["sub"])
        tenant_id = UUID(payload["tenant_id"])
    except (KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token claims",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return ChatEmployee(
        employee_id=employee_id,
        tenant_id=tenant_id,
        employee_name=payload.get("name", ""),
    )
