"""Ingest legacy FAQ markdown into brain private index (assistant-safe channel).

Stable section IDs (by source + title) so edits update in place.
Stale sections from the same source are deprecated (not left as duplicates).
Unchanged bodies skip re-chunk/re-embed via repository body_hash short-circuit.
"""

from __future__ import annotations

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
    # vault freeze is historical snapshot — only use if live files missing
    legacy = Path(__file__).resolve().parents[2] / "vault" / "legacy" / "quantum_labs.v1.md"
    paths.append(legacy)
    return paths


def resolve_faq_path(path: Path | None = None) -> Path | None:
    if path is not None:
        return path if path.exists() else None
    for p in _default_md_paths():
        if p.exists():
            return p
    return None


def ingest_legacy_faq(
    repo: BrainRepository,
    *,
    tenant_id: str,
    path: Path | None = None,
) -> dict[str, Any]:
    md_path = resolve_faq_path(path)
    if md_path is None:
        return {"ok": False, "error": "faq_md_not_found"}

    text = md_path.read_text(encoding="utf-8", errors="replace")
    # Split by H2 (and top-level H1 parts that act as sections)
    parts = re.split(r"(?m)(?=^##\s+)", text)
    created = 0
    updated = 0
    unchanged = 0
    keep_ids: set[str] = set()
    source = str(md_path.resolve())
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
        # Stable id: same section title from same file → same doc forever
        doc_id = slug_id("faq", md_path.name, title)
        keep_ids.add(doc_id)
        result = repo.upsert_document(
            doc_id=doc_id,
            tenant_id=tenant_id,
            title=title,
            doc_type="faq",
            body=block,
            visibility="company",
            acl=acl,
            classification={"level": "internal", "contains_personal_data": False},
            channels=["office-assistant"],
            source=source,
            index_zone="private",
            ai_processing={
                "external_embedding_allowed": True,
                "local_processing_required": False,
            },
        )
        if result.get("unchanged"):
            unchanged += 1
        elif result.get("version", 1) <= 1:
            created += 1
        else:
            updated += 1

    # Drop old hash-based / removed sections from this source (and legacy path aliases)
    deprecated = repo.deprecate_documents_not_in(
        tenant_id=tenant_id,
        source=source,
        keep_ids=keep_ids,
        doc_type="faq",
    )
    # Also deprecate FAQ rows that still point at an older unresolved path for same basename
    for alt in _default_md_paths():
        if not alt.exists():
            continue
        alt_s = str(alt.resolve())
        if alt_s == source:
            continue
        deprecated += repo.deprecate_documents_not_in(
            tenant_id=tenant_id,
            source=alt_s,
            keep_ids=set(),  # entire alternate snapshot superseded
            doc_type="faq",
        )
        deprecated += repo.deprecate_documents_not_in(
            tenant_id=tenant_id,
            source=str(alt),
            keep_ids=set(),
            doc_type="faq",
        )

    repo.set_ingest_state(
        "faq:last",
        f"path={md_path};sections={len(keep_ids)};created={created};"
        f"updated={updated};unchanged={unchanged};deprecated={deprecated}",
    )
    return {
        "ok": True,
        "sections": len(keep_ids),
        "created": created,
        "updated": updated,
        "unchanged": unchanged,
        "deprecated": deprecated,
        "path": str(md_path),
    }
