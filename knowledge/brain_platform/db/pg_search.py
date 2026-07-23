"""Postgres FTS + pgvector search with in-query ACL (mirrors SQLite BrainRepository)."""

from __future__ import annotations

import re
from typing import Any, Iterable

from brain_platform.security.acl import ACLFilter, Principal, resolve_principal_policy


def _zones_for(filt: ACLFilter) -> list[str]:
    if filt.deny_all:
        return []
    if filt.allow_all_in_tenant:
        return ["public", "private", "secret"]
    if filt.allowed_visibilities == {"public"} and not filt.require_assistant_safe:
        return ["public"]
    return ["public", "private"]


def _acl_sql(filt: ACLFilter, principal: Principal) -> tuple[str, list[Any]]:
    if filt.allow_all_in_tenant:
        return "TRUE", []
    parts: list[str] = []
    params: list[Any] = []
    if "public" in filt.allowed_visibilities or filt.require_assistant_safe:
        parts.append("(c.visibility = 'public' AND c.index_zone = 'public')")
    if filt.require_assistant_safe:
        parts.append(
            "(c.channels_json::text LIKE %s AND c.visibility IN ('company','public','team:sales','team:ops'))"
        )
        params.append("%office-assistant%")
    parts.append("c.allowed_users_json::text LIKE %s")
    params.append(f"%{principal.principal_id}%")
    if principal.user_id:
        parts.append("c.allowed_users_json::text LIKE %s")
        params.append(f"%user:{principal.user_id}%")
    parts.append("c.allowed_services_json::text LIKE %s")
    params.append(f"%{principal.principal_id}%")
    for g in principal.groups:
        gnorm = g if g.startswith("group:") else f"group:{g}"
        short = g.removeprefix("group:")
        parts.append("(c.allowed_groups_json::text LIKE %s OR c.allowed_groups_json::text LIKE %s)")
        params.extend([f"%{gnorm}%", f"%{short}%"])
    if principal.principal_id.startswith("user:") and "company" in filt.allowed_visibilities:
        parts.append("c.visibility = 'company'")
    for vis in filt.allowed_visibilities:
        if vis.startswith("team:"):
            parts.append("c.visibility = %s")
            params.append(vis)
    if not parts:
        return "FALSE", []
    return " OR ".join(parts), params


class PgSearchRepository:
    """Read-side search + directory on Postgres/pgvector."""

    def __init__(self, conn):
        self.conn = conn

    def search_chunks(
        self,
        principal: Principal,
        query: str,
        *,
        limit: int = 8,
        index_zones: Iterable[str] | None = None,
    ) -> list[dict[str, Any]]:
        filt = resolve_principal_policy(principal)
        if filt.deny_all:
            return []
        zones = list(index_zones) if index_zones is not None else _zones_for(filt)
        if not zones:
            return []
        q = (query or "").strip()
        if not q:
            return []
        tokens = re.findall(r"\w+", q, flags=re.U)[:12]
        tsq = " | ".join(tokens) if tokens else q
        acl_sql, acl_params = _acl_sql(filt, principal)
        sql = f"""
        SELECT c.chunk_id, c.document_id, c.tenant_id, c.visibility, c.text,
               c.index_zone, c.channels_json::text AS channels_json,
               c.allowed_users_json::text AS allowed_users_json,
               c.allowed_groups_json::text AS allowed_groups_json,
               c.allowed_services_json::text AS allowed_services_json,
               d.title, d.type, d.project_id,
               ts_rank(c.tsv, to_tsquery('simple', %s)) AS score
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE c.tenant_id = %s
          AND c.index_zone = ANY(%s)
          AND d.status = 'active'
          AND c.document_status = 'active'
          AND c.tsv @@ to_tsquery('simple', %s)
          AND ({acl_sql})
        ORDER BY score DESC
        LIMIT %s
        """
        params: list[Any] = [tsq, principal.tenant_id, zones, tsq, *acl_params, limit]
        try:
            with self.conn.cursor() as cur:
                cur.execute(sql, params)
                return list(cur.fetchall())
        except Exception:
            # fallback ILIKE
            like = f"%{q}%"
            sql_like = f"""
            SELECT c.chunk_id, c.document_id, c.tenant_id, c.visibility, c.text,
                   c.index_zone, c.channels_json::text AS channels_json,
                   c.allowed_users_json::text AS allowed_users_json,
                   c.allowed_groups_json::text AS allowed_groups_json,
                   c.allowed_services_json::text AS allowed_services_json,
                   d.title, d.type, d.project_id,
                   0.0 AS score
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE c.tenant_id = %s
              AND c.index_zone = ANY(%s)
              AND d.status = 'active'
              AND c.document_status = 'active'
              AND (c.text ILIKE %s OR d.title ILIKE %s)
              AND ({acl_sql})
            ORDER BY c.ordinal
            LIMIT %s
            """
            with self.conn.cursor() as cur:
                cur.execute(
                    sql_like,
                    [principal.tenant_id, zones, like, like, *acl_params, limit],
                )
                return list(cur.fetchall())

    def search_semantic(
        self,
        principal: Principal,
        query: str,
        *,
        limit: int = 8,
        candidate_limit: int = 2500,
    ) -> list[dict[str, Any]]:
        from brain_platform.vector import embed_texts

        filt = resolve_principal_policy(principal)
        if filt.deny_all or not query.strip():
            return []
        zones = _zones_for(filt)
        if not zones:
            return []
        vectors, _model = embed_texts([query], force_local=False)
        qvec = vectors[0]
        if len(qvec) != 1536:
            # local embedder dim mismatch — skip semantic on pgvector column
            return []
        emb_lit = "[" + ",".join(str(float(x)) for x in qvec) + "]"
        acl_sql, acl_params = _acl_sql(filt, principal)
        sql = f"""
        SELECT c.chunk_id, c.document_id, c.tenant_id, c.visibility, c.text,
               c.index_zone, c.channels_json::text AS channels_json,
               d.title, d.type, d.project_id,
               1 - (c.embedding <=> %s::vector) AS score,
               1 - (c.embedding <=> %s::vector) AS vector_score
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE c.tenant_id = %s
          AND c.index_zone = ANY(%s)
          AND d.status = 'active'
          AND c.document_status = 'active'
          AND c.embedding IS NOT NULL
          AND ({acl_sql})
        ORDER BY c.embedding <=> %s::vector
        LIMIT %s
        """
        with self.conn.cursor() as cur:
            cur.execute(
                sql,
                [emb_lit, emb_lit, principal.tenant_id, zones, *acl_params, emb_lit, limit],
            )
            return list(cur.fetchall())

    def find_contacts(self, principal: Principal, **kwargs) -> list[dict[str, Any]]:
        import json

        q = (kwargs.get("q") or "").strip()
        email = (kwargs.get("email") or "").strip().lower()
        limit = int(kwargs.get("limit") or 20)
        filt = resolve_principal_policy(principal)
        if filt.deny_all or principal.principal_id == "service:voice-public":
            return []
        clauses = ["tenant_id = %s", "status = 'active'"]
        params: list[Any] = [principal.tenant_id]
        if email:
            clauses.append("emails_json::text ILIKE %s")
            params.append(f"%{email}%")
        if q:
            clauses.append(
                "(display_name ILIKE %s OR company_name ILIKE %s OR emails_json::text ILIKE %s "
                "OR COALESCE(title,'') ILIKE %s)"
            )
            params.extend([f"%{q}%", f"%{q}%", f"%{q}%", f"%{q}%"])
        sql = f"""
        SELECT id, display_name, emails_json, phones_json, title, company_name, visibility, source
        FROM contacts
        WHERE {' AND '.join(clauses)}
        ORDER BY display_name
        LIMIT %s
        """
        params.append(limit)
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            rows = list(cur.fetchall())

        def _as_list(val: Any) -> list:
            if isinstance(val, list):
                return val
            if isinstance(val, str):
                try:
                    parsed = json.loads(val)
                    return parsed if isinstance(parsed, list) else []
                except Exception:
                    return []
            return []

        out = []
        for r in rows:
            out.append(
                {
                    "id": r["id"],
                    "display_name": r["display_name"],
                    "emails": _as_list(r.get("emails_json")),
                    "phones": _as_list(r.get("phones_json")),
                    "title": r.get("title"),
                    "company_name": r.get("company_name"),
                    "visibility": r.get("visibility"),
                    "source": r.get("source"),
                }
            )
        return out

    def list_threads(self, principal: Principal, **kwargs) -> list[dict[str, Any]]:
        q = (kwargs.get("q") or "").strip()
        limit = int(kwargs.get("limit") or 20)
        filt = resolve_principal_policy(principal)
        if filt.deny_all:
            return []
        clauses = ["tenant_id = %s"]
        params: list[Any] = [principal.tenant_id]
        if q:
            clauses.append("(subject ILIKE %s OR topics_json::text ILIKE %s)")
            params.extend([f"%{q}%", f"%{q}%"])
        sql = f"""
        SELECT id, subject, channel, last_message_at, topics_json, participant_ids_json, message_ids_json
        FROM threads
        WHERE {' AND '.join(clauses)}
        ORDER BY last_message_at DESC NULLS LAST
        LIMIT %s
        """
        params.append(limit)
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            rows = list(cur.fetchall())
        import json

        out = []
        for r in rows:
            item = dict(r)
            item["topics"] = item.get("topics_json") if not isinstance(item.get("topics_json"), str) else json.loads(item.get("topics_json") or "[]")
            item["message_ids"] = item.get("message_ids_json") if not isinstance(item.get("message_ids_json"), str) else json.loads(item.get("message_ids_json") or "[]")
            out.append(item)
        return out

    def stats(self, tenant_id: str) -> dict[str, int]:
        with self.conn.cursor() as cur:
            def c(sql, *a):
                cur.execute(sql, a)
                return int(cur.fetchone()["count"])

            return {
                "documents": c(
                    "SELECT count(*) AS count FROM documents WHERE tenant_id=%s AND status='active'",
                    tenant_id,
                ),
                "chunks": c("SELECT count(*) AS count FROM chunks WHERE tenant_id=%s", tenant_id),
                "chunks_embedded": c(
                    "SELECT count(*) AS count FROM chunks WHERE tenant_id=%s AND embedding IS NOT NULL",
                    tenant_id,
                ),
                "contacts": c("SELECT count(*) AS count FROM contacts WHERE tenant_id=%s", tenant_id),
                "emails": c("SELECT count(*) AS count FROM emails WHERE tenant_id=%s", tenant_id),
                "threads": c("SELECT count(*) AS count FROM threads WHERE tenant_id=%s", tenant_id),
                "files": c("SELECT count(*) AS count FROM files WHERE tenant_id=%s", tenant_id),
            }

    def write_audit(self, record: dict[str, Any]) -> None:
        import json

        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO audit_log (
                  principal_id, tenant_id, query_hash, query_preview_redacted,
                  retrieved_doc_ids_json, denied_doc_count, purpose, request_id, timestamp
                ) VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s,%s,NOW())
                """,
                (
                    record.get("principal_id"),
                    record.get("tenant_id"),
                    record.get("query_hash"),
                    record.get("query_preview_redacted"),
                    json.dumps(record.get("retrieved_doc_ids") or []),
                    int(record.get("denied_doc_count") or 0),
                    record.get("purpose"),
                    record.get("request_id"),
                ),
            )
        self.conn.commit()
