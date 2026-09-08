"""GraphStore v1 — entities/edges with ACL-aware expand."""

from __future__ import annotations

import json
import time
from typing import Any

from brain_platform.db.repository import slug_id
from brain_platform.security.acl import Principal, resolve_principal_policy


def _j(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _loads(raw: Any, default: Any) -> Any:
    if raw is None:
        return default
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return default


class GraphStore:
    """SQLite-backed graph (synced to Postgres via sync-pg)."""

    def __init__(self, conn):
        self.conn = conn

    def upsert_entity(
        self,
        *,
        tenant_id: str,
        kind: str,
        canonical_name: str,
        entity_id: str | None = None,
        metadata: dict | None = None,
        visibility: str = "company",
        aliases: list[str] | None = None,
    ) -> str:
        name = (canonical_name or "").strip()
        if not name:
            raise ValueError("canonical_name required")
        kind = (kind or "entity").strip().lower()
        eid = entity_id or slug_id("ent", kind, name.lower())
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.conn.execute(
            """
            INSERT INTO entities (
              id, tenant_id, kind, canonical_name, metadata_json, visibility, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              canonical_name=excluded.canonical_name,
              metadata_json=excluded.metadata_json,
              visibility=excluded.visibility,
              updated_at=excluded.updated_at
            """,
            (eid, tenant_id, kind, name, _j(metadata or {}), visibility, now, now),
        )
        for alias in aliases or []:
            a = (alias or "").strip()
            if not a or a.lower() == name.lower():
                continue
            aid = slug_id("alias", tenant_id, a.lower())
            try:
                self.conn.execute(
                    """
                    INSERT INTO entity_aliases (id, tenant_id, entity_id, alias, alias_type)
                    VALUES (?, ?, ?, ?, 'name')
                    ON CONFLICT DO NOTHING
                    """,
                    (aid, tenant_id, eid, a),
                )
            except Exception:
                # SQLite may not have entity_aliases yet on older DBs
                pass
        self.conn.commit()
        return eid

    def upsert_edge(
        self,
        *,
        tenant_id: str,
        source_entity_id: str,
        target_entity_id: str,
        relation_type: str,
        source_document_id: str | None = None,
        confidence: float = 1.0,
        review_status: str = "accepted",
        visibility: str = "company",
        edge_id: str | None = None,
    ) -> str:
        rid = relation_type.strip().lower()
        eid = edge_id or slug_id(
            "edge", tenant_id, source_entity_id, rid, target_entity_id
        )
        self.conn.execute(
            """
            INSERT INTO edges (
              id, tenant_id, source_entity_id, target_entity_id, relation_type,
              source_document_id, confidence, review_status, visibility
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              confidence=excluded.confidence,
              review_status=excluded.review_status,
              visibility=excluded.visibility,
              source_document_id=COALESCE(excluded.source_document_id, edges.source_document_id)
            """,
            (
                eid,
                tenant_id,
                source_entity_id,
                target_entity_id,
                rid,
                source_document_id,
                float(confidence),
                review_status,
                visibility,
            ),
        )
        self.conn.commit()
        return eid

    def find_entities(
        self,
        principal: Principal,
        *,
        q: str = "",
        kind: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        filt = resolve_principal_policy(principal)
        if filt.deny_all or principal.principal_id == "service:voice-public":
            return []
        clauses = ["tenant_id = ?"]
        params: list[Any] = [principal.tenant_id]
        if kind:
            clauses.append("kind = ?")
            params.append(kind)
        if q.strip():
            clauses.append("canonical_name LIKE ?")
            params.append(f"%{q.strip()}%")
        if not filt.allow_all_in_tenant:
            # company/restricted graph — no public-only leak for assistants without allow_all
            clauses.append("visibility IN ('public','company','team:sales','restricted')")
        sql = (
            f"SELECT * FROM entities WHERE {' AND '.join(clauses)} "
            f"ORDER BY canonical_name LIMIT ?"
        )
        params.append(limit)
        rows = self.conn.execute(sql, params).fetchall()
        out = []
        for r in rows:
            out.append(
                {
                    "id": r["id"],
                    "kind": r["kind"],
                    "canonical_name": r["canonical_name"],
                    "visibility": r["visibility"],
                    "metadata": _loads(r["metadata_json"], {}),
                }
            )
        return out

    def expand(
        self,
        principal: Principal,
        *,
        entity_id: str | None = None,
        q: str = "",
        depth: int = 1,
        limit: int = 40,
    ) -> dict[str, Any]:
        """1–2 hop expand around an entity (by id or name query)."""
        filt = resolve_principal_policy(principal)
        if filt.deny_all or principal.principal_id == "service:voice-public":
            return {
                "ok": True,
                "denied": True,
                "reason": "deny_all_or_voice_public",
                "roots": [],
                "entities": [],
                "edges": [],
            }

        depth = max(1, min(int(depth or 1), 2))
        limit = max(1, min(int(limit or 40), 100))

        roots = []
        if entity_id:
            row = self.conn.execute(
                "SELECT * FROM entities WHERE id = ? AND tenant_id = ?",
                (entity_id, principal.tenant_id),
            ).fetchone()
            if row:
                roots.append(dict(row))
        if not roots and q.strip():
            roots = [
                dict(r)
                for r in self.conn.execute(
                    """
                    SELECT * FROM entities
                    WHERE tenant_id = ? AND canonical_name LIKE ?
                    ORDER BY length(canonical_name) ASC
                    LIMIT 5
                    """,
                    (principal.tenant_id, f"%{q.strip()}%"),
                ).fetchall()
            ]
            # also try alias table if present
            try:
                alias_hits = self.conn.execute(
                    """
                    SELECT e.* FROM entity_aliases a
                    JOIN entities e ON e.id = a.entity_id
                    WHERE a.tenant_id = ? AND a.alias LIKE ?
                    LIMIT 5
                    """,
                    (principal.tenant_id, f"%{q.strip()}%"),
                ).fetchall()
                seen = {r["id"] for r in roots}
                for r in alias_hits:
                    if r["id"] not in seen:
                        roots.append(dict(r))
                        seen.add(r["id"])
            except Exception:
                pass

        if not roots:
            return {
                "ok": True,
                "denied": False,
                "roots": [],
                "entities": [],
                "edges": [],
                "query": q,
                "entity_id": entity_id,
            }

        frontier = {r["id"] for r in roots}
        entities: dict[str, dict[str, Any]] = {
            r["id"]: {
                "id": r["id"],
                "kind": r["kind"],
                "canonical_name": r["canonical_name"],
                "visibility": r["visibility"],
                "metadata": _loads(r["metadata_json"], {}),
            }
            for r in roots
        }
        edges_out: list[dict[str, Any]] = []
        seen_edges: set[str] = set()

        for _hop in range(depth):
            if not frontier or len(entities) >= limit:
                break
            placeholders = ",".join("?" * len(frontier))
            hop_ids = list(frontier)
            rows = self.conn.execute(
                f"""
                SELECT * FROM edges
                WHERE tenant_id = ?
                  AND review_status = 'accepted'
                  AND (source_entity_id IN ({placeholders})
                       OR target_entity_id IN ({placeholders}))
                LIMIT ?
                """,
                [principal.tenant_id, *hop_ids, *hop_ids, limit * 3],
            ).fetchall()
            next_frontier: set[str] = set()
            for er in rows:
                if er["id"] in seen_edges:
                    continue
                seen_edges.add(er["id"])
                if not filt.allow_all_in_tenant and er["visibility"] not in (
                    "public",
                    "company",
                    "team:sales",
                    "restricted",
                ):
                    continue
                edges_out.append(
                    {
                        "id": er["id"],
                        "source_entity_id": er["source_entity_id"],
                        "target_entity_id": er["target_entity_id"],
                        "relation_type": er["relation_type"],
                        "confidence": er["confidence"],
                        "visibility": er["visibility"],
                        "source_document_id": er["source_document_id"],
                    }
                )
                for nid in (er["source_entity_id"], er["target_entity_id"]):
                    if nid not in entities:
                        next_frontier.add(nid)
            if next_frontier:
                ph = ",".join("?" * len(next_frontier))
                for nr in self.conn.execute(
                    f"SELECT * FROM entities WHERE tenant_id = ? AND id IN ({ph})",
                    [principal.tenant_id, *next_frontier],
                ).fetchall():
                    if len(entities) >= limit:
                        break
                    entities[nr["id"]] = {
                        "id": nr["id"],
                        "kind": nr["kind"],
                        "canonical_name": nr["canonical_name"],
                        "visibility": nr["visibility"],
                        "metadata": _loads(nr["metadata_json"], {}),
                    }
            frontier = {nid for nid in next_frontier if nid in entities}

        return {
            "ok": True,
            "denied": False,
            "query": q,
            "entity_id": entity_id,
            "depth": depth,
            "roots": [
                {
                    "id": r["id"],
                    "kind": r["kind"],
                    "canonical_name": r["canonical_name"],
                    "visibility": r["visibility"],
                }
                for r in roots
            ],
            "entities": list(entities.values())[:limit],
            "edges": edges_out[: limit * 2],
            "summary": self._summary(list(entities.values()), edges_out),
        }

    @staticmethod
    def _summary(entities: list[dict[str, Any]], edges: list[dict[str, Any]]) -> str:
        by_kind: dict[str, list[str]] = {}
        for e in entities:
            by_kind.setdefault(e.get("kind") or "?", []).append(e.get("canonical_name") or e["id"])
        parts = []
        for kind, names in sorted(by_kind.items()):
            parts.append(f"{kind}: {', '.join(names[:8])}" + ("…" if len(names) > 8 else ""))
        rels = sorted({e.get("relation_type") or "?" for e in edges})
        if rels:
            parts.append("relations: " + ", ".join(rels))
        return "; ".join(parts)
