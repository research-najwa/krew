"""Security headers middleware — adds hardening headers to every response."""
import logging

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds security headers to every HTTP response."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=()"
        )

        # CSP: 'unsafe-inline' is required because chat.html and admin.html use inline
        # <script> blocks. This is a known trade-off — the inline scripts are our own
        # static HTML pages, not user-generated content. When the frontend is refactored
        # to use external script files, replace 'unsafe-inline' with nonce-based CSP.
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "img-src 'self' data:; "
            "font-src 'self' https://fonts.gstatic.com; "
            "connect-src 'self'; "
            "frame-ancestors 'none'"
        )

        # Disable legacy XSS auditor (can introduce side-channel leaks in old browsers)
        response.headers["X-XSS-Protection"] = "0"
        # Prevent cross-domain policy files from granting access
        response.headers["X-Permitted-Cross-Domain-Policies"] = "none"

        if settings.app_env != "development":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )

        return response
