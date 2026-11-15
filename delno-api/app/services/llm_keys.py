"""Per-company LLM key: bring-your-own or the platform key.

The raw key is never written to logs, events, or profile metadata.
BYOK is stored only in that tenant's settings and, when placed, in that
profile's .env so the Hermes process can prefer it over the shared worker env.
Platform-key companies do not get a copy of the platform key in their profile.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.tenant import TenantContext
from app.models.tenant import Tenant

KEY_BYOK = "byok"
KEY_PLATFORM = "platform"
KEY_MISSING = "missing"


def _llm_blob(tenant: Tenant) -> dict[str, Any]:
    settings = tenant.settings if isinstance(tenant.settings, dict) else {}
    raw = settings.get("llm")
    return dict(raw) if isinstance(raw, dict) else {}


def byok_key(tenant: Tenant) -> str:
    blob = _llm_blob(tenant)
    direct = str(blob.get("openai_api_key") or "").strip()
    if direct:
        return direct
    settings = tenant.settings if isinstance(tenant.settings, dict) else {}
    secrets = settings.get("secrets") if isinstance(settings.get("secrets"), dict) else {}
    boxed = secrets.get("openai") if isinstance(secrets, dict) else None
    if isinstance(boxed, dict):
        return str(boxed.get("api_key") or boxed.get("password") or "").strip()
    return ""


def resolve_openai_key(db: Session | None, tenant_or_ctx: Tenant | TenantContext | None) -> tuple[str, str]:
    """Return (key, source). Source is byok | platform | missing. Key may be empty."""
    tenant: Tenant | None = None
    if isinstance(tenant_or_ctx, Tenant):
        tenant = tenant_or_ctx
    elif tenant_or_ctx is not None and db is not None:
        tenant = db.query(Tenant).filter(Tenant.id == tenant_or_ctx.tenant_id).one_or_none()
    if tenant is not None:
        own = byok_key(tenant)
        if own:
            return own, KEY_BYOK
    platform = (get_settings().openai_api_key or "").strip()
    if platform:
        return platform, KEY_PLATFORM
    return "", KEY_MISSING


def chat_for_tenant(
    db: Session,
    ctx: TenantContext,
    provider: Any = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Chat completion with this company's key. Does not echo the key.

    Pass the already-resolved provider so tests and callers keep one object.
    """
    from app.services.model_provider import OpenAIProvider, get_model_provider

    key, source = resolve_openai_key(db, ctx)
    if provider is None:
        provider = get_model_provider()
    # Platform key missing, but this company brought one — use it.
    if source == KEY_BYOK and getattr(provider, "name", "") == "stub":
        provider = OpenAIProvider()
    out = provider.chat_completion(api_key=key or None, **kwargs)
    if isinstance(out, dict):
        out["key_source"] = source
        out.pop("api_key", None)
    return out if isinstance(out, dict) else {"ok": False, "error": "bad_provider", "key_source": source}
