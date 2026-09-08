"""G3 helpers: pull related entities from the knowledge graph into retrieve."""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from brain_platform.security.acl import Principal

logger = logging.getLogger("brain.graph_retrieve")

GRAPH_IN_RETRIEVE = (os.getenv("BRAIN_GRAPH_IN_RETRIEVE") or "true").strip().lower() in (
    "1",
    "true",
    "yes",
)


def _sqlite_conn(repo) -> Any:
    if hasattr(repo, "sqlite"):
        return repo.sqlite.conn
    return repo.conn


def graph_related_context(
    repo,
    principal: Principal,
    query: str,
    *,
    seed_titles: list[str] | None = None,
    depth: int = 1,
    limit_entities: int = 24,
) -> dict[str, Any]:
    """Expand graph around the query (and optional hit titles). ACL-aware."""
    if not GRAPH_IN_RETRIEVE:
        return {"ok": True, "skipped": True, "reason": "disabled"}
    if principal.principal_id == "service:voice-public":
        return {"ok": True, "denied": True, "entities": [], "edges": [], "summary": ""}

    try:
        from brain_platform.graph.store import GraphStore
    except Exception:
        return {"ok": False, "error": "graph_unavailable"}

    graph = GraphStore(_sqlite_conn(repo))
    seeds = [query.strip()] if query.strip() else []
    for t in seed_titles or []:
        t = (t or "").strip()
        # Prefer short proper-name-like tokens from titles
        if t and t not in seeds and len(t) <= 80:
            seeds.append(t)
        if len(seeds) >= 4:
            break

    merged_entities: dict[str, dict[str, Any]] = {}
    merged_edges: dict[str, dict[str, Any]] = {}
    roots: list[dict[str, Any]] = []

    for seed in seeds:
        # Skip pure FAQ-ish long questions for expand; keep short name-like seeds
        tokens = re.findall(r"\w+", seed, flags=re.U)
        if len(tokens) > 6 and seed == query:
            # Still try first capitalized / quoted spans
            named = re.findall(r"[\"«]([^\"»]{2,60})[\"»]|([A-ZА-ЯЁ][\w\-.]{2,40})", seed)
            flat = [a or b for a, b in named if (a or b)]
            if not flat:
                continue
            seed = flat[0]
        out = graph.expand(principal, q=seed, depth=depth, limit=limit_entities)
        if out.get("denied"):
            return out
        for r in out.get("roots") or []:
            if r.get("id") and r["id"] not in {x.get("id") for x in roots}:
                roots.append(r)
        for e in out.get("entities") or []:
            merged_entities[e["id"]] = e
        for edge in out.get("edges") or []:
            merged_edges[edge["id"]] = edge

    entities = list(merged_entities.values())
    edges = list(merged_edges.values())
    summary_parts = []
    by_kind: dict[str, list[str]] = {}
    for e in entities:
        by_kind.setdefault(e.get("kind") or "?", []).append(e.get("canonical_name") or e["id"])
    for kind, names in sorted(by_kind.items()):
        summary_parts.append(f"{kind}: {', '.join(names[:6])}" + ("…" if len(names) > 6 else ""))
    rels = sorted({e.get("relation_type") or "?" for e in edges})
    if rels:
        summary_parts.append("relations: " + ", ".join(rels))

    return {
        "ok": True,
        "denied": False,
        "roots": roots,
        "entities": entities,
        "edges": edges,
        "summary": "; ".join(summary_parts),
        "search_hints": _search_hints(entities),
    }


def _search_hints(entities: list[dict[str, Any]]) -> list[str]:
    hints: list[str] = []
    for e in entities:
        kind = e.get("kind")
        name = (e.get("canonical_name") or "").strip()
        if not name:
            continue
        if kind in ("person", "company", "thread_topic", "product"):
            hints.append(name)
        meta = e.get("metadata") or {}
        for em in meta.get("emails") or []:
            if isinstance(em, str) and "@" in em:
                hints.append(em)
        if meta.get("thread_id"):
            hints.append(str(meta["thread_id"]))
        if len(hints) >= 12:
            break
    # dedupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for h in hints:
        key = h.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(h)
    return out


def fetch_graph_hits(
    repo,
    principal: Principal,
    hints: list[str],
    *,
    limit_per_hint: int = 2,
    max_hits: int = 8,
) -> list[dict[str, Any]]:
    """Keyword-search related entities; mark hits as graph-boosted."""
    hits: list[dict[str, Any]] = []
    seen: set[str] = set()
    for hint in hints:
        if len(hits) >= max_hits:
            break
        try:
            rows = repo.search_chunks(principal, hint, limit=limit_per_hint)
        except Exception:
            logger.exception("graph hint search failed for %r", hint)
            continue
        for row in rows:
            cid = row.get("chunk_id")
            if not cid or cid in seen:
                continue
            seen.add(cid)
            item = dict(row)
            item["graph_boost"] = True
            # Soft score so RRF still ranks them below strong primary hits
            try:
                item["score"] = float(item.get("score") or 0.0) * 0.4
            except (TypeError, ValueError):
                item["score"] = 0.0
            hits.append(item)
            if len(hits) >= max_hits:
                break
    return hits
