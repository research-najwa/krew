"""Input validation and sanitization utilities."""
import os
import re
import unicodedata

from fastapi import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

MAX_BODY_SIZE = 1 * 1024 * 1024  # 1 MB
MAX_UPLOAD_BODY_SIZE = 6 * 1024 * 1024  # 6 MB — allows 5 MB files + multipart overhead
UPLOAD_PATHS = {"/api/v1/documents/upload"}
ALLOWED_EXTENSIONS = {".txt", ".pdf", ".docx"}


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests exceeding 1 MB — checks both header and actual body."""

    async def dispatch(self, request: Request, call_next):
        # Use higher limit for document upload paths to allow 5 MB files
        if request.url.path in UPLOAD_PATHS:
            limit = MAX_UPLOAD_BODY_SIZE
        else:
            limit = MAX_BODY_SIZE

        # Check Content-Length header first (fast path)
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > limit:
                    return JSONResponse(
                        status_code=413,
                        content={
                            "detail": f"Request body too large. Maximum size is {limit // (1024 * 1024)} MB. / حجم الطلب كبير جدا."
                        },
                    )
            except ValueError:
                pass

        # For non-GET/HEAD/OPTIONS, also check actual body size (handles chunked encoding)
        if request.method in ("POST", "PUT", "PATCH"):
            body = await request.body()
            if len(body) > limit:
                return JSONResponse(
                    status_code=413,
                    content={
                        "detail": f"Request body too large. Maximum size is {limit // (1024 * 1024)} MB. / حجم الطلب كبير جدا."
                    },
                )

        return await call_next(request)


def validate_chat_message(message: str) -> str:
    """Validate and clean a chat message. Returns the stripped message.

    Raises HTTPException on invalid input.
    """
    if not message or not message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty / الرسالة لا يمكن أن تكون فارغة")

    cleaned = message.strip()

    if len(cleaned) > 4000:
        raise HTTPException(
            status_code=400,
            detail="Message too long. Maximum 4000 characters. / الرسالة طويلة جدا. الحد الأقصى 4000 حرف.",
        )

    return cleaned


def validate_string_field(value: str, field_name: str, max_length: int = 500) -> str:
    """Validate a generic string field. Returns the stripped value.

    Raises HTTPException on invalid input.
    """
    if not value or not value.strip():
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} cannot be empty",
        )

    cleaned = value.strip()

    if len(cleaned) > max_length:
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} too long. Maximum {max_length} characters.",
        )

    return cleaned


def sanitize_filename(filename: str) -> str:
    """Sanitize a filename: strip path traversal, remove unsafe chars, validate extension.

    Keeps Unicode (including Arabic) characters. Returns the cleaned filename.
    Raises HTTPException if the extension is not allowed.
    """
    if not filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    # Strip path components — prevent path traversal
    filename = os.path.basename(filename)

    # Remove null bytes
    filename = filename.replace("\x00", "")

    # Normalize unicode
    filename = unicodedata.normalize("NFC", filename)

    # Remove characters that are unsafe in filenames but keep Unicode/Arabic
    # Allow: word chars (including Unicode), hyphens, dots, spaces
    filename = re.sub(r"[^\w\s.\-]", "", filename, flags=re.UNICODE)

    # Collapse multiple dots/spaces
    filename = re.sub(r"\.{2,}", ".", filename)
    filename = re.sub(r"\s+", " ", filename)
    filename = filename.strip(". ")

    if not filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    # Validate extension
    _, ext = os.path.splitext(filename)
    ext = ext.lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{ext}' not allowed. Supported: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    return filename
