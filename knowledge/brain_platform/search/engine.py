"""RAG retrieve with hybrid (FTS + vector RRF) search and principal-scoped ACL."""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from brain_platform.db.repository import BrainRepository
from brain_platform.schemas.models import CacheKeyParts
from brain_platform.security.acl import (
    Principal,
    build_cache_key,
    make_audit_record,
    resolve_principal_policy,
)
from brain_platform.vector import rrf_fuse

logger = logging.getLogger("brain.search")

DEFAULT_MODE = (os.getenv("BRAIN_SEARCH_MODE") or "hybrid").strip().lower()


def format_citation(hit: dict[str, Any]) -> str:
    """Human/machine citation string for a search match (S2)."""
    dtype = hit.get("type") or "doc"
    title = hit.get("title") or hit.get("document_id") or "untitled"
    parts = [f"[{dtype}] {title}"]
    if hit.get("source"):
        parts.append(f"src={hit['source']}")
    if hit.get("thread_id"):
        parts.append(f"thread={hit['thread_id']}")
    if hit.get("index_zone"):
        parts.append(f"zone={hit['index_zone']}")
    parts.append(f"doc={hit.get('document_id')}")
    parts.append(f"chunk={hit.get('chunk_id')}")
    return " | ".join(str(p) for p in parts if p)


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
        mode: str | None = None,
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
                "search_mode": mode or DEFAULT_MODE,
            }

        search_mode = (mode or DEFAULT_MODE or "hybrid").strip().lower()
        if search_mode not in ("keyword", "semantic", "hybrid"):
            search_mode = "hybrid"

        _ = build_cache_key(
            CacheKeyParts(
                tenant_id=principal.tenant_id,
                principal_id=principal.principal_id,
                groups=list(principal.groups),
                permission_revision=principal.permission_revision,
                query=query,
                search_mode=search_mode,
                index_revision=1,
            )
        )

        # Multi-query expansion for better recall (lexical variants)
        queries = [query]
        try:
            from brain_platform.search.memory import memory_query_variants

            variants = memory_query_variants(query)
            for v in variants:
                if v and v not in queries:
                    queries.append(v)
                if len(queries) >= 5:
                    break
        except Exception:
            pass

        keyword_hits: list[dict[str, Any]] = []
        semantic_hits: list[dict[str, Any]] = []
        seen_kw: set[str] = set()

        if search_mode in ("keyword", "hybrid"):
            for q in queries:
                for h in self.repo.search_chunks(principal, q, limit=limit * 2):
                    cid = h.get("chunk_id")
                    if cid in seen_kw:
                        continue
                    seen_kw.add(cid)
                    keyword_hits.append(h)
                if len(keyword_hits) >= limit * 3:
                    break

        if search_mode in ("semantic", "hybrid"):
            try:
                semantic_hits = self.repo.search_semantic(
                    principal, query, limit=max(limit * 2, 12)
                )
            except Exception:
                logger.exception("semantic search failed; continuing with keyword")
                if search_mode == "semantic":
                    search_mode = "keyword"

        if search_mode == "keyword":
            hits = keyword_hits[:limit]
        elif search_mode == "semantic":
            hits = semantic_hits[:limit]
        else:
            hits = rrf_fuse([keyword_hits, semantic_hits], k=60, limit=limit)
            if not hits:
                hits = (keyword_hits or semantic_hits)[:limit]

        parts: list[str] = []
        matches: list[dict[str, Any]] = []
        total = 0
        for h in hits:
            title = h.get("title") or ""
            body = h.get("text") or ""
            dtype = h.get("type") or ""
            header = f"## {title}" + (f" [{dtype}]" if dtype else "")
            block = f"{header}\n{body}".strip()
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
                    "index_zone": h.get("index_zone"),
                    "source": h.get("source"),
                    "thread_id": h.get("thread_id"),
                    "score": h.get("score"),
                    "rrf_score": h.get("rrf_score"),
                    "vector_score": h.get("vector_score"),
                    "snippet": body[:1200],
                    "citation": format_citation(h),
                }
            )

        text = "\n\n".join(parts)
        request_id = str(uuid.uuid4())
        citations = [m["citation"] for m in matches if m.get("citation")]
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
            "citations": citations,
            "request_id": request_id,
            "principal_id": principal.principal_id,
            "tenant_id": principal.tenant_id,
            "denied": False,
            "search_mode": search_mode,
            "keyword_hits": len(keyword_hits),
            "semantic_hits": len(semantic_hits),
            "source_of_truth": "second_brain",
        }
