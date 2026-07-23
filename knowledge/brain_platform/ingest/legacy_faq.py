"""Ingest legacy FAQ markdown into brain private index (assistant-safe channel)."""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any

from brain_platform.db.repository import BrainRepository, slug_id


def _default_md_paths() -> list[Path]:
    paths = []
    env = (os.getenv("KNOWLEDGE_QUANTUM_LABS_PATH") or "").strip()
    if env:
        paths.append(Path(env))
    bundled = Path(__file__).resolve().parents[2] / "content" / "quantum_labs.md"
    paths.append(bundled)
    legacy = Path(__file__).resolve().parents[2] / "vault" / "legacy" / "quantum_labs.v1.md"
    paths.append(legacy)
    return paths


def ingest_legacy_faq(
    repo: BrainRepository,
    *,
    tenant_id: str,
    path: Path | None = None,
) -> dict[str, Any]:
    md_path = path
    if md_path is None:
        for p in _default_md_paths():
            if p.exists():
                md_path = p
                break
    if md_path is None or not md_path.exists():
        return {"ok": False, "error": "faq_md_not_found"}

    text = md_path.read_text(encoding="utf-8", errors="replace")
    # Split by H2
    parts = re.split(r"(?m)(?=^##\s+)", text)
    created = 0
    acl = {
        "allow_users": [],
        "allow_groups": ["group:management", "group:sales", "group:ops"],
        "allow_services": [
            "service:cursor-admin",
            "service:text-secretary",
            "service:voice-office",
        ],
        "deny_users": [],
        "deny_groups": [],
    }
    for block in parts:
        block = block.strip()
        if not block:
            continue
        first = block.splitlines()[0].lstrip("# ").strip()
        title = first or "FAQ section"
        doc_id = slug_id("faq", title, hashlib.sha1(block.encode()).hexdigest()[:8])
        repo.upsert_document(
            doc_id=doc_id,
            tenant_id=tenant_id,
            title=title,
            doc_type="faq",
            body=block,
            visibility="company",
            acl=acl,
            classification={"level": "internal", "contains_personal_data": False},
            channels=["office-assistant"],
            source=str(md_path),
            index_zone="private",
        )
        created += 1

    # Also keep a published-style public-safe stub? No — FAQ stays private until manual publish.
    repo.set_ingest_state("faq:last", f"path={md_path};sections={created}")
    return {"ok": True, "sections": created, "path": str(md_path)}
