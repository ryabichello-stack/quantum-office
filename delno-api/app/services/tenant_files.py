"""Per-tenant file path isolation (F0).

All on-disk / object keys for a tenant MUST resolve under
`tenants/{tenant_id}/…`. Callers never accept raw client paths.
See docs/DELNO_TENANT_FILES_AND_PDN.md.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any

from app.core.config import get_settings

SAFE_REL_RE = re.compile(r"^[A-Za-z0-9._\- /()]+$")
ALLOWED_ZONES = frozenset({"uploads", "knowledge", "telephony", "mail", "exports", "tmp"})


class TenantFileError(ValueError):
    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        super().__init__(message or code)


def tenants_root() -> Path:
    settings = get_settings()
    raw = (getattr(settings, "tenant_files_root", None) or "").strip()
    if raw:
        return Path(raw)
    # Prefer dedicated root; fall back next to onboarding dir parent.
    onboarding = Path(getattr(settings, "onboarding_upload_dir", "/data/onboarding"))
    return onboarding.parent / "tenants"


def tenant_prefix(tenant_id: uuid.UUID | str) -> Path:
    tid = str(tenant_id)
    try:
        uuid.UUID(tid)
    except ValueError as exc:
        raise TenantFileError("invalid_tenant_id") from exc
    return tenants_root() / tid


def resolve_tenant_path(
    tenant_id: uuid.UUID | str,
    *,
    zone: str,
    relative: str = "",
    create_parents: bool = False,
) -> Path:
    """Resolve a path inside the tenant tree; reject traversal / odd zones."""
    zone_clean = (zone or "").strip().strip("/")
    if zone_clean not in ALLOWED_ZONES:
        raise TenantFileError("invalid_zone", f"zone must be one of {sorted(ALLOWED_ZONES)}")

    rel = (relative or "").replace("\\", "/").lstrip("/")
    if rel:
        if ".." in rel.split("/"):
            raise TenantFileError("path_traversal")
        if rel.startswith("/") or ":" in rel.split("/")[0]:
            raise TenantFileError("absolute_path_forbidden")
        if not SAFE_REL_RE.match(rel):
            raise TenantFileError("unsafe_relative_path")

    base = tenant_prefix(tenant_id) / zone_clean
    target = (base / rel).resolve() if rel else base.resolve()
    base_resolved = base.resolve()
    # Ensure target stays under tenants/{id}/{zone}
    try:
        target.relative_to(base_resolved)
    except ValueError as exc:
        raise TenantFileError("path_escape") from exc

    root_resolved = tenant_prefix(tenant_id).resolve()
    try:
        target.relative_to(root_resolved)
    except ValueError as exc:
        raise TenantFileError("path_escape") from exc

    if create_parents:
        if rel:
            target.parent.mkdir(parents=True, exist_ok=True)
        else:
            target.mkdir(parents=True, exist_ok=True)
    return target


def object_key(tenant_id: uuid.UUID | str, *, zone: str, name: str) -> str:
    """S3-style key: t/{tenant_id}/{zone}/{name} — validates via resolve_tenant_path."""
    resolve_tenant_path(tenant_id, zone=zone, relative=name)
    tid = str(uuid.UUID(str(tenant_id)))
    zone_clean = zone.strip().strip("/")
    name_clean = name.replace("\\", "/").lstrip("/")
    return f"t/{tid}/{zone_clean}/{name_clean}"


def residency_status() -> dict[str, Any]:
    """Platform signal for Hermes / health: where files are expected to live."""
    settings = get_settings()
    region = (getattr(settings, "tenant_files_region", None) or "ru").strip().lower()
    store = (getattr(settings, "tenant_files_backend", None) or "local").strip().lower()
    foreign_llm = bool(getattr(settings, "openai_api_key", None) or getattr(settings, "openai_http_proxy", None))
    return {
        "ok": region.startswith("ru"),
        "region": region,
        "backend": store,
        "root": str(tenants_root()),
        "policy": "docs/DELNO_TENANT_FILES_AND_PDN.md",
        "foreign_llm_configured": foreign_llm,
        "message_ru": (
            "Файлы тенантов — контур РФ; сырой текст в зарубежный LLM только после "
            "обезличивания или с явным согласием (см. Политику)."
            if region.startswith("ru")
            else "Регион хранения файлов не РФ — нарушение целевой политики резидентности."
        ),
    }
