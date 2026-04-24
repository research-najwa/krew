"""Auth API — login, token refresh, user management for admin panel."""
import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.admin_user import AdminUser, AdminRole
from app.auth.passwords import hash_password, verify_password, hash_password_async, verify_password_async
from app.auth.jwt import create_access_token, create_refresh_token, decode_token
from app.auth.dependencies import get_current_user, require_role, require_tenant

from jose import JWTError, ExpiredSignatureError
from app.security.rate_limiter import check_login_rate_limit
from app.auth.token_blacklist import blacklist_token, is_blacklisted, blacklist_all_user_tokens, is_token_revoked_for_user
from app.security.audit import emit_audit_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


# ── Request / Response schemas ─────────────────────────────────────


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: "UserInfo"


class UserInfo(BaseModel):
    id: str
    email: str
    full_name: str
    full_name_ar: str | None
    role: str
    tenant_id: str | None
    is_active: bool


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class RefreshResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class CreateAdminRequest(BaseModel):
    email: str
    full_name: str
    full_name_ar: str | None = None
    password: str
    role: AdminRole = AdminRole.hr_specialist
    tenant_id: UUID | None = None


class AdminUserOut(BaseModel):
    id: str
    email: str
    full_name: str
    full_name_ar: str | None
    role: str
    tenant_id: str | None
    is_active: bool
    last_login_at: str | None
    created_at: str


# ── Endpoints ──────────────────────────────────────────────────────


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Authenticate with email + password, receive JWT tokens."""
    email = body.email.strip().lower()
    await check_login_rate_limit(request, email)

    result = await db.execute(select(AdminUser).where(AdminUser.email == email))
    user = result.scalar_one_or_none()

    if not user:
        await emit_audit_event(
            db, action="auth.login_failed", actor_email=email,
            detail={"reason": "invalid_credentials"}, request=request,
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # Check active status before running expensive bcrypt verify
    if not user.is_active:
        await emit_audit_event(
            db, action="auth.login_failed", actor_id=str(user.id),
            actor_email=email, tenant_id=str(user.tenant_id) if user.tenant_id else None,
            detail={"reason": "invalid_credentials"}, request=request,
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not await verify_password_async(body.password, user.hashed_password):
        await emit_audit_event(
            db, action="auth.login_failed", actor_id=str(user.id),
            actor_email=email, tenant_id=str(user.tenant_id) if user.tenant_id else None,
            detail={"reason": "invalid_credentials"}, request=request,
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # Update last login
    user.last_login_at = datetime.now(timezone.utc)

    await emit_audit_event(
        db, action="auth.login", actor_id=str(user.id),
        actor_email=user.email, tenant_id=str(user.tenant_id) if user.tenant_id else None,
        resource_type="user", resource_id=str(user.id), request=request,
    )
    await db.commit()

    access_token = create_access_token(user.id, user.email, user.role.value, user.tenant_id)
    refresh_token = create_refresh_token(user.id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=_user_to_info(user),
    )


@router.post("/refresh", response_model=RefreshResponse)
async def refresh(body: RefreshRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Exchange a refresh token for new access + refresh tokens (token rotation)."""
    try:
        payload = decode_token(body.refresh_token)
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has expired",
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token claims",
        )

    # Atomically blacklist the old refresh token (SET NX for race prevention)
    old_jti = payload.get("jti")
    if old_jti:
        old_exp = payload.get("exp", 0)
        was_new = await blacklist_token(old_jti, int(old_exp))
        if not was_new:
            # Token was already blacklisted — this is a reuse attempt
            await blacklist_all_user_tokens(user_id)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token reuse detected. All sessions have been revoked.",
            )

    # Check per-user revocation (e.g. password change invalidates all tokens)
    token_iat = payload.get("iat", 0)
    if await is_token_revoked_for_user(user_id, int(token_iat)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="All sessions have been revoked. Please log in again.",
        )

    result = await db.execute(select(AdminUser).where(AdminUser.id == UUID(user_id)))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or deactivated",
        )

    access_token = create_access_token(user.id, user.email, user.role.value, user.tenant_id)
    new_refresh_token = create_refresh_token(user.id)

    await emit_audit_event(
        db, action="auth.token_refresh", actor_id=str(user.id),
        actor_email=user.email, tenant_id=str(user.tenant_id) if user.tenant_id else None,
        resource_type="user", resource_id=str(user.id), request=request,
    )
    await db.commit()

    return RefreshResponse(access_token=access_token, refresh_token=new_refresh_token)


@router.post("/logout")
async def logout(
    body: LogoutRequest,
    request: Request,
    current_user: AdminUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Logout — blacklist both access and refresh tokens."""
    # Blacklist the access token (from Authorization header)
    credentials = request.headers.get("Authorization", "")
    if credentials.startswith("Bearer "):
        access_token_str = credentials[7:]
        try:
            access_payload = decode_token(access_token_str)
            access_jti = access_payload.get("jti")
            access_exp = access_payload.get("exp", 0)
            if access_jti:
                await blacklist_token(access_jti, int(access_exp))
        except Exception as e:
            logger.warning(f"Failed to blacklist access token: {e}")

    # Blacklist the refresh token — but only if it belongs to the current user
    try:
        refresh_payload = decode_token(body.refresh_token)
        refresh_sub = refresh_payload.get("sub")
        if refresh_sub == str(current_user.id):
            refresh_jti = refresh_payload.get("jti")
            refresh_exp = refresh_payload.get("exp", 0)
            if refresh_jti:
                await blacklist_token(refresh_jti, int(refresh_exp))
        else:
            logger.warning(
                f"Logout: refresh token sub '{refresh_sub}' does not match "
                f"current user '{current_user.id}' — ignoring refresh token blacklist"
            )
    except Exception:
        pass  # Best-effort for refresh token

    await emit_audit_event(
        db, action="auth.logout", actor_id=str(current_user.id),
        actor_email=current_user.email,
        tenant_id=str(current_user.tenant_id) if current_user.tenant_id else None,
        resource_type="user", resource_id=str(current_user.id), request=request,
    )
    await db.commit()

    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserInfo)
async def me(current_user: AdminUser = Depends(get_current_user)):
    """Return the current authenticated user's info."""
    return _user_to_info(current_user)


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
    current_user: AdminUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Change the current user's password."""
    if not await verify_password_async(body.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    if len(body.new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be at least 8 characters",
        )

    current_user.hashed_password = await hash_password_async(body.new_password)
    current_user.updated_at = datetime.now(timezone.utc)

    # Invalidate all existing sessions
    await blacklist_all_user_tokens(str(current_user.id))

    await emit_audit_event(
        db, action="auth.password_change", actor_id=str(current_user.id),
        actor_email=current_user.email,
        tenant_id=str(current_user.tenant_id) if current_user.tenant_id else None,
        resource_type="user", resource_id=str(current_user.id), request=request,
    )
    await db.commit()

    return {"message": "Password changed successfully"}


@router.post("/users", response_model=AdminUserOut)
async def create_admin_user(
    body: CreateAdminRequest,
    request: Request,
    current_user: AdminUser = Depends(require_role(AdminRole.tenant_admin)),
    db: AsyncSession = Depends(get_db),
):
    """Create a new admin user. Requires tenant_admin or higher."""
    # Validate password length
    if len(body.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters",
        )

    # Role hierarchy enforcement: cannot create equal or higher role (except super_admin)
    from app.auth.dependencies import _ROLE_RANK
    creator_rank = _ROLE_RANK.get(current_user.role, -1)
    target_rank = _ROLE_RANK.get(body.role, 99)
    if current_user.role != AdminRole.super_admin and target_rank >= creator_rank:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot create a user with equal or higher role",
        )

    # Determine tenant_id based on creator's role
    if current_user.role == AdminRole.super_admin:
        # super_admin can assign any tenant
        tenant_id = body.tenant_id
    else:
        # tenant_admin: always use own tenant, ignore body.tenant_id
        tenant_id = current_user.tenant_id

    # Check email uniqueness
    email = body.email.strip().lower()
    existing = await db.execute(select(AdminUser).where(AdminUser.email == email))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    user = AdminUser(
        email=email,
        full_name=body.full_name,
        full_name_ar=body.full_name_ar,
        hashed_password=await hash_password_async(body.password),
        role=body.role,
        tenant_id=tenant_id,
        is_active=True,
    )
    db.add(user)
    await db.flush()

    await emit_audit_event(
        db, action="user.create", actor_id=str(current_user.id),
        actor_email=current_user.email,
        tenant_id=str(tenant_id) if tenant_id else None,
        resource_type="user", resource_id=str(user.id),
        detail={"email": email, "role": body.role.value}, request=request,
    )
    await db.commit()
    await db.refresh(user)

    return _user_to_out(user)


@router.get("/users", response_model=list[AdminUserOut])
async def list_admin_users(
    current_user: AdminUser = Depends(require_role(AdminRole.tenant_admin)),
    db: AsyncSession = Depends(get_db),
):
    """List admin users. super_admin sees all, tenant_admin sees own tenant only."""
    query = select(AdminUser).order_by(AdminUser.created_at.desc())

    if current_user.role != AdminRole.super_admin:
        # tenant_admin sees only their own tenant's users
        query = query.where(AdminUser.tenant_id == current_user.tenant_id)

    result = await db.execute(query)
    users = result.scalars().all()

    return [_user_to_out(u) for u in users]


# ── Helpers ────────────────────────────────────────────────────────


def _user_to_info(user: AdminUser) -> UserInfo:
    return UserInfo(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        full_name_ar=user.full_name_ar,
        role=user.role.value,
        tenant_id=str(user.tenant_id) if user.tenant_id else None,
        is_active=user.is_active,
    )


def _user_to_out(user: AdminUser) -> AdminUserOut:
    return AdminUserOut(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        full_name_ar=user.full_name_ar,
        role=user.role.value,
        tenant_id=str(user.tenant_id) if user.tenant_id else None,
        is_active=user.is_active,
        last_login_at=user.last_login_at.isoformat() if user.last_login_at else None,
        created_at=user.created_at.isoformat(),
    )
