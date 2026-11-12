from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://delno:delno@localhost:5433/delno"
    default_tenant_slug: str = "delno-demo"
    api_key: str | None = None

    jwt_secret: str = "change-me-in-production"
    jwt_expire_minutes: int = 60 * 24 * 7

    knowledge_base_url: str = "http://127.0.0.1:8021"
    knowledge_use_legacy_principals: bool = True
    messenger_base_url: str = ""
    api_public_base_url: str = ""
    # Office connectors (tools-first — empty = stub / not_configured)
    mailer_base_url: str = ""
    calendar_base_url: str = ""
    files_base_url: str = ""
    conference_base_url: str = ""
    outreach_base_url: str = ""
    office_webhook_token: str | None = None
    # Asterisk / dialer → DELNO telephony bridge
    telephony_webhook_token: str | None = None
    # E2.4 MAX Bot API (platform-api2)
    max_api_base_url: str = "https://platform-api2.max.ru"

    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None

    # Public DELNO site lead notifications (SMTP)
    lead_notify_to: str | None = None
    lead_smtp_host: str | None = None
    lead_smtp_port: int = 465
    lead_smtp_user: str | None = None
    lead_smtp_password: str | None = None
    lead_smtp_from: str | None = None

    # Host Asterisk SIP apply (Cloud4Box dogfood)
    asterisk_sip_apply_enabled: bool = False
    asterisk_sip_apply_url: str | None = None  # e.g. http://host.docker.internal:18099

    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"
    openai_realtime_model: str = "gpt-realtime-2.1-mini"
    openai_realtime_voice: str = "cedar"
    model_provider: str = "openai"
    # OpenAI egress: direct api.openai.com is geo-blocked from RU VPS —
    # route via SPB→Minsk→NL bridge (HTTP/SOCKS proxy) and/or compatible base URL.
    openai_base_url: str = "https://api.openai.com/v1"
    openai_http_proxy: str | None = None

    dadata_api_key: str | None = None
    dadata_secret_key: str | None = None

    # Widget public API rate limits (Commit 2)
    widget_rate_limit_per_minute: int = 60
    widget_rate_limit_messages_per_minute: int = 30
    widget_rate_limit_window_sec: int = 60

    # CORS — comma-separated origins; empty = regex fallback in main.py
    cors_allow_origins: str = ""
    cors_allow_credentials: bool = False
    # Onboarding file uploads (O3)
    onboarding_upload_dir: str = "/data/onboarding"
    onboarding_upload_max_bytes: int = 20 * 1024 * 1024
    # Per-tenant file store (F0+) — see docs/DELNO_TENANT_FILES_AND_PDN.md
    tenant_files_root: str = "/data/tenants"
    tenant_files_backend: str = "local"  # local | s3_ru
    tenant_files_region: str = "ru"

    # Hermes cabinet: surface tool/LLM failures in the chat reply (debug phase).
    # Set HERMES_DEBUG_FAILURES=false to hide the trailing «отладка (сбои)» block.
    hermes_debug_failures: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
