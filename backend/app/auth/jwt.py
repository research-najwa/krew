"""JWT token creation and decoding."""
import uuid
from datetime import datetime, timedelta, timezone
from uuid import UUID

from jose import jwt, JWTError, ExpiredSignatureError

from app.config import get_settings

REFRESH_TOKEN_EXPIRE_DAYS = 7
CHAT_TOKEN_EXPIRE_HOURS = 12


def create_chat_token(employee_id: UUID, tenant_id: UUID, name: str) -> str:
    """Create a JWT for employee chat authentication.

    Uses type="chat" to distinguish from admin access tokens (type="access").
    """
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(employee_id),
        "tenant_id": str(tenant_id),
        "name": name,
        "type": "chat",
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + timedelta(hours=CHAT_TOKEN_EXPIRE_HOURS),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: UUID, email: str, role: str, tenant_id: UUID | None) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "tenant_id": str(tenant_id) if tenant_id else None,
        "type": "access",
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + timedelta(hours=settings.jwt_expiry_hours),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: UUID) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
