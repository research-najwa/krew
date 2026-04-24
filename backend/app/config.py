from pydantic import field_validator
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://krew:krew_secret@localhost:5432/krew"
    database_url_sync: str = "postgresql://krew:krew_secret@localhost:5432/krew"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # AI
    anthropic_api_key: str = ""
    llm_model: str = "claude-sonnet-4-6"
    llm_max_tokens: int = 4096

    # Web search (for recruitment sourcing)
    tavily_api_key: str = ""

    # Embeddings
    openai_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536

    # Email / SMTP
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = "noreply@krew.sa"
    smtp_from_name: str = "Krew HR"

    # Channels
    whatsapp_phone_number_id: str = ""
    whatsapp_access_token: str = ""
    whatsapp_verify_token: str = "krew-webhook-verify"
    whatsapp_app_secret: str = ""
    slack_bot_token: str = ""
    slack_signing_secret: str = ""

    # Auth
    jwt_secret: str = "change-this"
    jwt_algorithm: str = "HS256"
    jwt_expiry_hours: int = 24

    # File uploads
    upload_dir: str = "uploads"

    # App
    app_env: str = "production"  # Default to production so security is ON; set APP_ENV=development explicitly for dev mode
    app_port: int = 8000
    cors_origins: str = "http://localhost:3000,https://krew.sa"

    # Security — rate limiting
    trusted_proxies: str = ""  # comma-separated CIDRs/IPs, e.g. "10.0.0.0/8,172.16.0.0/12"
    rate_limit_fail_mode: str = "closed"  # "closed" (reject on Redis down) or "open"
    blacklist_fail_mode: str = "closed"  # "closed" (reject on Redis down) or "open" (in-memory fallback)

    # Government integrations — GOSI & Mudad (empty = stub mode)
    gosi_api_url: str = ""
    gosi_api_key: str = ""
    mudad_api_url: str = ""
    mudad_api_key: str = ""

    # Security — webhook API keys
    whatsapp_webhook_api_key: str = ""
    slack_webhook_api_key: str = ""

    # Security — webhooks
    webhook_skip_verification: bool = False  # must be explicitly True to skip in development

    @field_validator("database_url", mode="after")
    @classmethod
    def ensure_async_driver(cls, v: str) -> str:
        if v.startswith("postgresql://"):
            v = v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
