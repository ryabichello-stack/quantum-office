"""Ingest vault/quantum-brain markdown shards (frontmatter ACL)."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from brain_platform.db.repository import BrainRepository, slug_id

try:
    from brain_platform.vault_paths import resolve_vault_path
except ImportError:  # pragma: no cover
    resolve_vault_path = None  # type: ignore

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None  # type: ignore


SKIP_NAMES = {"readme.md"}
SKIP_DIR_PARTS = {"_meta", ".git"}


def default_vault_path() -> Path:
    env = (os.getenv("BRAIN_VAULT_PATH") or "").strip()
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2] / "vault" / "quantum-brain"


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---"):
        return {}, text
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, flags=re.S)
    if not m:
        return {}, text
    raw, body = m.group(1), m.group(2)
    meta: dict[str, Any] = {}
    if yaml is not None:
        try:
            loaded = yaml.safe_load(raw) or {}
            if isinstance(loaded, dict):
                meta = loaded
        except Exception:
            meta = {}
    return meta, body


def ingest_vault(
    repo: BrainRepository,
    *,
    tenant_id: str,
    vault_path: Path | None = None,
    limit: int = 500,
) -> dict[str, Any]:
    root = vault_path or (resolve_vault_path(tenant_id) if resolve_vault_path else default_vault_path())
    if not root.exists():
        return {"ok": False, "error": f"vault_missing:{root}"}

    files = sorted(root.rglob("*.md"))
    created = updated = unchanged = skipped = 0
    keep_ids: set[str] = set()
    ingested: list[str] = []

    for path in files:
        if len(ingested) >= limit:
            break
        if any(part in SKIP_DIR_PARTS for part in path.parts):
            skipped += 1
            continue
        if path.name.lower() in SKIP_NAMES:
            skipped += 1
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        meta, body = _parse_frontmatter(text)
        body = body.strip()
        if len(body) < 40:
            skipped += 1
            continue

        title = next(
            (ln.lstrip("# ").strip() for ln in body.splitlines() if ln.startswith("#")),
            path.stem,
        )
        rel = str(path.relative_to(root))
        doc_id = slug_id("vault", rel, title)
        keep_ids.add(doc_id)

        visibility = str(meta.get("visibility") or "company")
        classification = meta.get("classification") or {"level": "internal"}
        channels = meta.get("channels") or ["office-assistant"]
        publication = meta.get("publication") or {}
        ai_processing = meta.get("ai_processing") or {}
        tenant = str(meta.get("tenant_id") or tenant_id)
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

        result = repo.upsert_document(
            doc_id=doc_id,
            tenant_id=tenant,
            title=title,
            doc_type="vault",
            body=body,
            visibility=visibility,
            acl=acl,
            classification=classification if isinstance(classification, dict) else {"level": "internal"},
            channels=list(channels) if isinstance(channels, list) else ["office-assistant"],
            source=f"vault:{rel}",
            index_zone="private",
            publication=publication if isinstance(publication, dict) else {},
            ai_processing=ai_processing if isinstance(ai_processing, dict) else {},
        )
        ingested.append(rel)
        if result.get("unchanged"):
            unchanged += 1
        elif result.get("version", 1) <= 1:
            created += 1
        else:
            updated += 1

    # Deprecate vault docs removed from tree (same source prefix)
    deprecated = 0
    rows = repo.conn.execute(
        "SELECT id, source FROM documents WHERE tenant_id = ? AND type = 'vault' AND status = 'active'",
        (tenant_id,),
    ).fetchall()
    for r in rows:
        if r["id"] not in keep_ids and str(r["source"] or "").startswith("vault:"):
            repo.conn.execute(
                "UPDATE documents SET status = 'deprecated' WHERE id = ?",
                (r["id"],),
            )
            deprecated += 1
    if deprecated:
        repo.conn.commit()

    return {
        "ok": True,
        "vault": str(root),
        "files": len(ingested),
        "created": created,
        "updated": updated,
        "unchanged": unchanged,
        "skipped": skipped,
        "deprecated": deprecated,
        "paths": ingested,
    }
