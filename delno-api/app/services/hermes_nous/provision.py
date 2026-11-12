"""Provision per-tenant HERMES_HOME skeleton + runtime map in tenant.settings."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.tenant import TenantContext
from app.models.tenant import Tenant

# Templates live next to hermes_runtime in the repo / image.
_TEMPLATES = Path(__file__).resolve().parents[3] / "hermes_runtime" / "templates" / "home"


def _settings(tenant: Tenant) -> dict[str, Any]:
    return dict(tenant.settings) if isinstance(tenant.settings, dict) else {}


def hermes_home_path(tenant_id: UUID) -> Path:
    root = Path(get_settings().tenant_files_root)
    return root / str(tenant_id) / "hermes"


def ensure_tenant_hermes_home(
    db: Session,
    ctx: TenantContext,
    *,
    runtime_base_url: str | None = None,
    api_server_key_env: str = "HERMES_API_SERVER_KEY",
) -> dict[str, Any]:
    """Create HERMES_HOME dirs + seed SOUL/config if missing. Idempotent."""
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    home = hermes_home_path(ctx.tenant_id)
    home.mkdir(parents=True, exist_ok=True)
    for sub in ("memories", "skills", "cron", "sessions"):
        (home / sub).mkdir(exist_ok=True)

    if _TEMPLATES.is_dir():
        for name in ("config.yaml", "SOUL.md", "AGENTS.md"):
            src = _TEMPLATES / name
            dst = home / name
            if src.is_file() and not dst.exists():
                shutil.copy2(src, dst)

    # Inject MCP stub pointing at DELNO (URL only — token per run at bridge time)
    config_path = home / "config.yaml"
    if config_path.is_file():
        text = config_path.read_text(encoding="utf-8")
        if "delno_office:" not in text:
            mcp_url = f"{_public_mcp_base()}/v1/mcp"
            block = (
                "\nmcp_servers:\n"
                "  delno_office:\n"
                f'    url: "{mcp_url}"\n'
                "    headers:\n"
                '      Authorization: "Bearer ${DELNO_RUN_TOKEN}"\n'
            )
            # Replace empty mcp_servers: {} if present
            if "mcp_servers: {}" in text:
                text = text.replace("mcp_servers: {}", block.strip())
            else:
                text = text.rstrip() + "\n" + block
            config_path.write_text(text, encoding="utf-8")

    base = (runtime_base_url or os.environ.get("HERMES_NOUS_RUNTIME_URL") or "").strip().rstrip("/")
    record = {
        "engine": "nous_hermes_agent",
        "pin": "v0.23.1",
        "hermes_home": str(home),
        "runtime_base_url": base or None,
        "api_server_key_env": api_server_key_env,
        "profile_name": f"tenant_{tenant.slug}",
        "self_setup_policy": {
            "agent_may_edit": ["SOUL.md", "skills/", "cron/", "memories/"],
            "agent_must_not_edit": ["mcp_servers.url", "vault", "egress", ".env secrets"],
        },
        "telephony": "out_of_scope_for_this_runtime",
    }
    settings = _settings(tenant)
    nous = dict(settings.get("hermes_nous") or {})
    nous["runtime"] = record
    settings["hermes_nous"] = nous
    tenant.settings = settings
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return record


def tenant_runtime_record(db: Session, ctx: TenantContext) -> dict[str, Any] | None:
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one_or_none()
    if not tenant:
        return None
    blob = _settings(tenant).get("hermes_nous")
    if not isinstance(blob, dict):
        return None
    runtime = blob.get("runtime")
    return dict(runtime) if isinstance(runtime, dict) else None


def _public_mcp_base() -> str:
    settings = get_settings()
    base = (settings.api_public_base_url or "").strip().rstrip("/")
    return base or "http://127.0.0.1:18020"
