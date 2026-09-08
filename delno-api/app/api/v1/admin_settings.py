"""Platform admin — server .env secrets."""

from __future__ import annotations

from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import require_platform_admin
from app.core.db import get_db
from app.core.tenant import TenantContext
from app.models.user import User
from app.services.audit import write_audit
from app.services.events import emit_event
from app.services.platform_env import (
    env_file_status,
    list_secret_fields,
    update_env_values,
)
from app.services.openai_catalog import fetch_openai_options

router = APIRouter(prefix="/admin/platform-secrets", tags=["admin-settings"])


class PlatformSecretsUpdate(BaseModel):
    values: dict[str, str] = Field(default_factory=dict)


@router.get("")
def get_platform_secrets(
    admin: User = Depends(require_platform_admin),
) -> dict:
    """Masked list of platform env keys (never returns full secret values)."""
    status = env_file_status()
    options = fetch_openai_options()
    return {
        "env_file": status,
        "groups": list_secret_fields(),
        "options": {
            "source": options["source"],
            "fetched_at": options["fetched_at"],
            "fetch_error": options.get("fetch_error"),
            "chat_models": options["chat_models"],
            "realtime_models": options["realtime_models"],
            "realtime_voices": options["realtime_voices"],
        },
        "updated_by": str(admin.id),
    }


@router.post("/options/refresh")
def refresh_platform_secret_options(
    admin: User = Depends(require_platform_admin),
) -> dict:
    """Re-fetch OpenAI model lists (cached 5 min otherwise)."""
    options = fetch_openai_options(force_refresh=True)
    return {
        "source": options["source"],
        "fetched_at": options["fetched_at"],
        "fetch_error": options.get("fetch_error"),
        "chat_models": options["chat_models"],
        "realtime_models": options["realtime_models"],
        "realtime_voices": options["realtime_voices"],
    }


@router.patch("")
def patch_platform_secrets(
    body: PlatformSecretsUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_platform_admin),
) -> dict:
    """Update selected keys in the server .env file."""
    status = env_file_status()
    if not status.get("writable"):
        raise HTTPException(status_code=503, detail="env_not_writable")

    filtered = {k: v for k, v in body.values.items() if v is not None}
    changed, error = update_env_values(filtered)
    if error:
        if error.startswith("unknown_keys"):
            raise HTTPException(status_code=400, detail=error)
        raise HTTPException(status_code=500, detail=error)

    ctx = TenantContext(
        tenant_id=admin.tenant_id,
        tenant_slug="platform",
        user_id=admin.id,
        role=admin.role,
    )
    write_audit(
        db,
        ctx,
        action="admin.platform_secrets.update",
        actor="platform_admin",
        resource="platform.env",
        new_value={"keys": changed},
        result="ok" if changed else "noop",
    )
    emit_event(
        db,
        tenant_id=admin.tenant_id,
        event_type="admin.platform_secrets.updated",
        category="operational",
        source="admin.platform_secrets",
        payload={"keys": changed, "admin_id": str(admin.id)},
    )
    db.commit()

    return {
        "ok": True,
        "changed": changed,
        "env_file": env_file_status(),
        "groups": list_secret_fields(),
    }
