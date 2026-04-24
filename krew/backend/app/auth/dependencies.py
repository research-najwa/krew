"""FastAPI dependency functions for auth, RBAC, and tenant isolation."""
from uuid import UUID
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from jose import JWTError, ExpiredSignatureError

from app.database import get_db
from app.models.admin_user import AdminUser, AdminRole
from app.models.tenant import Tenant
from app.auth.jwt import decode_token
from app.auth.token_blacklist import is_blacklisted, is_token_revoked_for_user

bearer_scheme = HTTPBearer(auto_error=True)

_ROLE_RANK = {
    AdminRole.hr_specialist: 0,
    AdminRole.hr_manager: 1,
    AdminRole.tenant_admin: 2,
    AdminRole.super_admin: 3,
}


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    db: AsyncSession = Depends(get_db),
) -> AdminUser:
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

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check token blacklist (jti)
    jti = payload.get("jti")
    if jti and await is_blacklisted(jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token claims",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if all tokens for this user have been revoked
    iat = payload.get("iat")
    if iat and await is_token_revoked_for_user(user_id, int(iat)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    result = await db.execute(select(AdminUser).where(AdminUser.id == UUID(user_id)))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or deactivated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def has_minimum_role(user: AdminUser, minimum_role: AdminRole) -> bool:
    """Check if a user meets the minimum role requirement.

    Public helper so API routers don't need to access _ROLE_RANK directly.
    """
    user_rank = _ROLE_RANK.get(user.role, -1)
    required_rank = _ROLE_RANK.get(minimum_role, 99)
    return user_rank >= required_rank


def require_role(minimum_role: AdminRole):
    async def _check_role(current_user: AdminUser = Depends(get_current_user)) -> AdminUser:
        user_rank = _ROLE_RANK.get(current_user.role, -1)
        required_rank = _ROLE_RANK.get(minimum_role, 99)
        if user_rank < required_rank:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required: {minimum_role.value}",
            )
        return current_user
    return _check_role


def require_tenant():
    async def _resolve_tenant(
        current_user: AdminUser = Depends(get_current_user),
        x_tenant_id: str | None = Header(None, alias="X-Tenant-ID"),
        db: AsyncSession = Depends(get_db),
    ) -> UUID:
        if current_user.role == AdminRole.super_admin:
            if not x_tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="X-Tenant-ID header required for super_admin",
                )
            try:
                tenant_uuid = UUID(x_tenant_id)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid X-Tenant-ID",
                )
            result = await db.execute(select(Tenant).where(Tenant.id == tenant_uuid))
            if not result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Tenant not found",
                )
            return tenant_uuid
        else:
            if not current_user.tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="User has no tenant assignment",
                )
            return current_user.tenant_id
    return _resolve_tenant
