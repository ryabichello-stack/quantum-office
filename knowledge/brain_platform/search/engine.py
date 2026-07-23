"""RAG retrieve with principal-scoped ACL search + redacted audit."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from brain_platform.db.repository import BrainRepository
from brain_platform.security.acl import (
    Principal,
    build_cache_key,
    make_audit_record,
    resolve_principal_policy,
)
from brain_platform.schemas.models import CacheKeyParts


class BrainSearch:
    def __init__(self, repo: BrainRepository):
        self.repo = repo

    def retrieve(
        self,
        principal: Principal,
        query: str,
        *,
        limit: int = 8,
        max_chars: int = 6000,
        purpose: str = "assistant-query",
    ) -> dict[str, Any]:
        filt = resolve_principal_policy(principal)
        if filt.deny_all:
            return {
                "ok": True,
                "text": "",
                "chars": 0,
                "matches": [],
                "denied": True,
                "reason": "deny_all",
            }

        # cache key includes security context (even if we don't persist cache yet)
        _ = build_cache_key(
            CacheKeyParts(
                tenant_id=principal.tenant_id,
                principal_id=principal.principal_id,
                groups=list(principal.groups),
                permission_revision=principal.permission_revision,
                query=query,
                search_mode="keyword",
                index_revision=1,
            )
        )

        hits = self.repo.search_chunks(principal, query, limit=limit)
        parts: list[str] = []
        matches: list[dict[str, Any]] = []
        total = 0
        for h in hits:
            title = h.get("title") or ""
            body = h.get("text") or ""
            block = f"## {title}\n{body}".strip()
            if total + len(block) > max_chars:
                remain = max_chars - total
                if remain > 200:
                    parts.append(block[:remain])
                    total += remain
                break
            parts.append(block)
            total += len(block) + 2
            matches.append(
                {
                    "document_id": h["document_id"],
                    "chunk_id": h["chunk_id"],
                    "title": title,
                    "type": h.get("type"),
                    "visibility": h.get("visibility"),
                    "score": h.get("score"),
                    "snippet": body[:1200],
                }
            )

        text = "\n\n".join(parts)
        request_id = str(uuid.uuid4())
        audit = make_audit_record(
            principal=principal,
            query=query,
            retrieved_doc_ids=[m["document_id"] for m in matches],
            denied_doc_count=0,
            purpose=purpose,
            request_id=request_id,
            timestamp=datetime.now(timezone.utc),
        )
        self.repo.write_audit(audit.model_dump(mode="json"))

        return {
            "ok": True,
            "text": text,
            "chars": len(text),
            "matches": matches,
            "request_id": request_id,
            "principal_id": principal.principal_id,
            "tenant_id": principal.tenant_id,
            "denied": False,
        }
