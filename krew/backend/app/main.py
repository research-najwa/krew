"""Krew Backend — AI HR Department API."""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.api import webhooks, dashboard, employees, policies, chat, admin, escalations, auth, audit, leave_approvals
from app.api import notifications, documents, hr_policies
from app.api import reports, nitaqat, onboarding, chat_auth, manager
from app.api import gosi, mudad, attendance, employee_documents, teams
from app.api import suggestions
from app.security.rate_limiter import get_redis, close_redis, RateLimitMiddleware
from app.security.input_validator import BodySizeLimitMiddleware
from app.security.headers import SecurityHeadersMiddleware

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parents[1] / "static"

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("🚀 Krew backend starting...")
    print(f"   Environment: {settings.app_env}")
    print(f"   LLM model: {settings.llm_model}")
    if settings.app_env != "development" and settings.jwt_secret == "change-this":
        raise RuntimeError("FATAL: jwt_secret must be changed from default in non-development environments")
    # Verify webhook secrets are configured in non-development environments
    if settings.app_env != "development":
        if not settings.whatsapp_app_secret:
            raise RuntimeError("FATAL: whatsapp_app_secret must be set in non-development environments")
        if not settings.slack_signing_secret:
            raise RuntimeError("FATAL: slack_signing_secret must be set in non-development environments")
    else:
        # In development, warn if secrets are missing
        if not settings.whatsapp_app_secret:
            if settings.webhook_skip_verification:
                logger.warning("SECURITY WARNING: WhatsApp webhook signature verification is DISABLED (development mode, webhook_skip_verification=True)")
            else:
                logger.warning("WhatsApp app secret not set. Webhook signature verification will reject requests unless webhook_skip_verification=True.")
        if not settings.slack_signing_secret:
            if settings.webhook_skip_verification:
                logger.warning("SECURITY WARNING: Slack webhook signature verification is DISABLED (development mode, webhook_skip_verification=True)")
            else:
                logger.warning("Slack signing secret not set. Webhook signature verification will reject requests unless webhook_skip_verification=True.")
    # Warn if no trusted proxies configured in production
    if settings.app_env != "development" and not settings.trusted_proxies.strip():
        logger.warning(
            "No trusted_proxies configured — X-Forwarded-For headers will be ignored. "
            "Set TRUSTED_PROXIES if behind a load balancer."
        )
    # Warn about missing webhook API keys
    if settings.app_env != "development":
        if not settings.whatsapp_webhook_api_key:
            logger.warning(
                "SECURITY WARNING: whatsapp_webhook_api_key is not configured. "
                "WhatsApp webhook endpoint will return 500."
            )
        if not settings.slack_webhook_api_key:
            logger.warning(
                "SECURITY WARNING: slack_webhook_api_key is not configured. "
                "Slack webhook endpoint will return 500."
            )
    # Warn about missing CORS origins in non-dev
    cors_list = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    if settings.app_env != "development" and not cors_list:
        logger.warning(
            "SECURITY WARNING: No CORS origins configured (cors_origins is empty). "
            "Cross-origin requests will be rejected."
        )
    # Create uploads directory structure
    uploads_dir = Path(settings.upload_dir if hasattr(settings, 'upload_dir') else "uploads")
    uploads_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Upload directory: {uploads_dir.resolve()}")
    # Initialize Redis for rate limiting (non-fatal if unavailable)
    try:
        await get_redis()
    except Exception as e:
        logger.warning(f"Redis unavailable at startup: {e}")
    yield
    # Shutdown
    await close_redis()
    print("Krew backend shutting down.")


app = FastAPI(
    title="Krew API",
    description="AI HR Department — 18 virtual employees, 5 divisions",
    version="0.1.0",
    lifespan=lifespan,
)

# Middleware order: last-added runs first in Starlette.
# SecurityHeaders is added first so it runs last (wraps response on the way out).
# CORS is added last so it wraps everything (including 429 responses).

# Parse and validate CORS origins
_cors_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
_blocked_origins = {"*", "null"}
_found_blocked = _blocked_origins & set(_cors_origins)
if settings.app_env != "development" and _found_blocked:
    raise RuntimeError(
        f"FATAL: Dangerous CORS origin(s) {_found_blocked} not allowed in non-development environments. "
        "Set cors_origins to specific origins."
    )

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(BodySizeLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    # allow_credentials=False because the API uses Bearer token auth (Authorization
    # header), not cookies. Credentials mode is unnecessary and would restrict us
    # from using wildcard sub-settings in the future.
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Tenant-ID", "X-API-Key", "Accept", "Accept-Language"],
    expose_headers=["Retry-After"],
    max_age=600,
)

# Routes
app.include_router(webhooks.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")
app.include_router(employees.router, prefix="/api/v1")
app.include_router(policies.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(escalations.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
app.include_router(audit.router, prefix="/api/v1")
app.include_router(leave_approvals.router, prefix="/api/v1")
app.include_router(notifications.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")
app.include_router(hr_policies.router, prefix="/api/v1")
app.include_router(reports.router, prefix="/api/v1")
app.include_router(nitaqat.router, prefix="/api/v1")
app.include_router(onboarding.router, prefix="/api/v1")
app.include_router(chat_auth.router, prefix="/api/v1")
app.include_router(manager.router, prefix="/api/v1")
app.include_router(gosi.router, prefix="/api/v1")
app.include_router(mudad.router, prefix="/api/v1")
app.include_router(attendance.router, prefix="/api/v1")
app.include_router(employee_documents.router, prefix="/api/v1")
app.include_router(teams.router, prefix="/api/v1")
app.include_router(suggestions.router, prefix="/api/v1")


@app.get("/")
async def root():
    return {
        "name": "Krew",
        "tagline": "Your AI HR Department",
        "version": "0.1.0",
        "agents": ["Deema", "Waleed", "Mohammad", "Yara", "Norah", "Sarah"],
        "status": "operational",
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/chat")
async def chat_page():
    return FileResponse(STATIC_DIR / "chat.html")


@app.get("/admin")
async def admin_page():
    return FileResponse(STATIC_DIR / "admin" / "index.html")


@app.get("/admin/legacy")
async def admin_legacy_page():
    return FileResponse(STATIC_DIR / "admin.html")


# Mount admin static JS files so module imports resolve
app.mount("/admin/js", StaticFiles(directory=str(STATIC_DIR / "admin" / "js")), name="admin-js")
