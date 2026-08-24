"""Tenant package bootstrap helpers (Stage 8 lite)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

TENANTS_ROOT = Path(__file__).resolve().parent / "config" / "tenants"
SEED = "quantum-labs"


def list_tenants() -> list[str]:
    if not TENANTS_ROOT.is_dir():
        return []
    return sorted(p.name for p in TENANTS_ROOT.iterdir() if p.is_dir())


def bootstrap_tenant(tenant_id: str, *, force: bool = False) -> dict[str, Any]:
    tid = (tenant_id or "").strip().lower().replace(" ", "-")
    if not tid or tid == SEED:
        raise ValueError("invalid_tenant_id")
    src = TENANTS_ROOT / SEED
    dst = TENANTS_ROOT / tid
    if not src.is_dir():
        raise FileNotFoundError("seed_tenant_missing")
    if dst.exists() and not force:
        return {"ok": True, "exists": True, "tenant_id": tid, "path": str(dst)}
    if dst.exists() and force:
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    # stamp tenant_id inside json files
    for path in dst.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and "tenant_id" in data:
            data["tenant_id"] = tid
            path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
    return {
        "ok": True,
        "created": True,
        "tenant_id": tid,
        "path": str(dst),
        "files": sorted(p.name for p in dst.glob("*.json")),
    }
