"""Per-tenant vault directory layout (E1.9)."""

from __future__ import annotations

import os
from pathlib import Path


def vault_root() -> Path:
    env = (os.getenv("BRAIN_VAULT_ROOT") or os.getenv("BRAIN_VAULT_PATH") or "").strip()
    if env:
        p = Path(env)
        return p if p.is_absolute() else Path(__file__).resolve().parents[2] / p
    return Path(__file__).resolve().parents[2] / "vault"


def tenant_vault_root(tenant_slug: str) -> Path:
    """Isolated vault tree: vault/{tenant_slug}/"""
    slug = (tenant_slug or "").strip() or "default"
    return vault_root() / slug


def resolve_vault_path(tenant_id: str, explicit: Path | None = None) -> Path:
    if explicit is not None:
        return explicit
    tenant_path = tenant_vault_root(tenant_id)
    if tenant_path.exists():
        return tenant_path
    legacy = vault_root() / "quantum-brain"
    if legacy.exists():
        return legacy
    return tenant_path
