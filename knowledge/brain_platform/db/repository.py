"""Persistence layer with in-query ACL helpers."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable

from brain_platform.security.acl import ACLFilter, Principal, resolve_principal_policy
from brain_platform.security.safety import decide_index_action, scan_document_text
from brain_platform.security.zones import coerce_index_zone

try:
    from brain_platform.embeddings import should_external_embed
    from brain_platform.vector import embed_texts, get_vector_store
except Exception:  # pragma: no cover - during partial imports in tests
    should_external_embed = None  # type: ignore
    embed_texts = None  # type: ignore
    get_vector_store = None  # type: ignore


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _j(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _loads(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def body_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def slug_id(prefix: str, *parts: str) -> str:
    base = "-".join(p.strip().lower() for p in parts if p and p.strip())
    base = re.sub(r"[^a-z0-9а-яё_-]+", "-", base, flags=re.I)[:80].strip("-")
    h = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:10]
    return f"{prefix}-{base}-{h}" if base else f"{prefix}-{h}"


DEFAULT_MAIL_ACL = {
    "allow_users": [],
    "allow_groups": ["group:management", "group:sales"],
    "allow_services": ["service:cursor-admin", "service:text-secretary"],
    "deny_users": [],
    "deny_groups": [],
}


class BrainRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    # ----- documents / chunks -----

    def upsert_document(
        self,
        *,
        doc_id: str,
        tenant_id: str,
        title: str,
        doc_type: str,
        body: str,
        visibility: str = "company",
        acl: dict | None = None,
        classification: dict | None = None,
        channels: list[str] | None = None,
        project_id: str | None = None,
        source: str | None = None,
        index_zone: str = "private",
        status: str = "active",
        chunk_size: int = 1400,
        chunk_overlap: int = 200,
        ai_processing: dict | None = None,
        embed: bool = True,
        publication: dict | None = None,
    ) -> dict[str, Any]:
        report = scan_document_text(body)
        if decide_index_action(report) == "quarantine":
            status = "quarantine"
            classification = {
                **(classification or {}),
                "level": "secret",
                "contains_credentials": True,
            }

        acl = acl or {}
        classification = classification or {"level": "internal"}
        channels = channels or []
        ai_processing = ai_processing or {}
        publication = publication or {}
        index_zone = coerce_index_zone(
            doc_type=doc_type,
            visibility=visibility,
            index_zone=index_zone,
            classification=classification,
            publication=publication,
        )
        now = _now()
        bh = body_hash(body)

        existing = self.conn.execute(
            "SELECT version, acl_revision, body_hash, status FROM documents WHERE id = ?",
            (doc_id,),
        ).fetchone()
        # Unchanged body → keep chunks/embeddings, refresh metadata lightly
        if (
            existing
            and existing["body_hash"] == bh
            and existing["status"] == "active"
            and status == "active"
        ):
            self.conn.execute(
                """
                UPDATE documents SET
                  title=?, visibility=?, acl_json=?, classification_json=?,
                  channels_json=?, ai_processing_json=?, source=?, project_id=?,
                  index_zone=?, updated_at=?
                WHERE id=?
                """,
                (
                    title,
                    visibility,
                    _j(acl or {}),
                    _j(classification or {"level": "internal"}),
                    _j(channels or []),
                    _j(ai_processing or {}),
                    source,
                    project_id,
                    index_zone,
                    _now(),
                    doc_id,
                ),
            )
            self.conn.commit()
            chunks_n = self.conn.execute(
                "SELECT COUNT(*) AS n FROM chunks WHERE document_id=?", (doc_id,)
            ).fetchone()["n"]
            return {
                "id": doc_id,
                "status": "active",
                "version": existing["version"],
                "acl_revision": existing["acl_revision"],
                "chunks": chunks_n,
                "embedded": 0,
                "unchanged": True,
                "quarantine": False,
                "findings": [],
            }

        version = (existing["version"] + 1) if existing else 1
        acl_revision = (existing["acl_revision"] + 1) if existing else 1

        self.conn.execute(
            """
            INSERT INTO documents (
              id, tenant_id, title, type, visibility, acl_json, classification_json,
              publication_json, channels_json, ai_processing_json, status, version,
              acl_revision, source, project_id, body, body_hash, index_zone,
              created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              title=excluded.title,
              type=excluded.type,
              visibility=excluded.visibility,
              acl_json=excluded.acl_json,
              classification_json=excluded.classification_json,
              publication_json=excluded.publication_json,
              channels_json=excluded.channels_json,
              ai_processing_json=excluded.ai_processing_json,
              status=excluded.status,
              version=excluded.version,
              acl_revision=excluded.acl_revision,
              source=excluded.source,
              project_id=excluded.project_id,
              body=excluded.body,
              body_hash=excluded.body_hash,
              index_zone=excluded.index_zone,
              updated_at=excluded.updated_at
            """,
            (
                doc_id,
                tenant_id,
                title,
                doc_type,
                visibility,
                _j(acl),
                _j(classification),
                _j(publication),
                _j(channels),
                _j(ai_processing),
                status,
                version,
                acl_revision,
                source,
                project_id,
                body,
                bh,
                index_zone,
                now,
                now,
            ),
        )

        # Replace chunks transactionally with document ACL inheritance
        old_chunks = self.conn.execute(
            "SELECT chunk_id FROM chunks WHERE document_id = ?", (doc_id,)
        ).fetchall()
        for row in old_chunks:
            self.conn.execute("DELETE FROM chunks_fts WHERE chunk_id = ?", (row["chunk_id"],))
        self.conn.execute("DELETE FROM chunks WHERE document_id = ?", (doc_id,))

        chunk_count = 0
        embedded = 0
        if status != "quarantine":
            parts = self._chunk_text(body, chunk_size, overlap=chunk_overlap)
            chunk_count = len(parts)
            allow_users = list(acl.get("allow_users") or [])
            allow_groups = [g.removeprefix("group:") for g in (acl.get("allow_groups") or [])]
            allow_services = list(acl.get("allow_services") or [])
            class_level = classification.get("level", "internal")
            chunk_ids: list[str] = []
            for i, part in enumerate(parts):
                cid = f"{doc_id}:chunk-{i:04d}"
                chunk_ids.append(cid)
                self.conn.execute(
                    """
                    INSERT INTO chunks (
                      chunk_id, document_id, tenant_id, visibility,
                      allowed_users_json, allowed_groups_json, allowed_services_json,
                      classification, acl_revision, document_status, document_version,
                      index_zone, channels_json, ordinal, text, embedding_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '[]')
                    """,
                    (
                        cid,
                        doc_id,
                        tenant_id,
                        visibility,
                        _j(allow_users),
                        _j(allow_groups),
                        _j(allow_services),
                        class_level,
                        acl_revision,
                        status,
                        version,
                        index_zone,
                        _j(channels),
                        i,
                        part,
                    ),
                )
                self.conn.execute(
                    "INSERT INTO chunks_fts(chunk_id, document_id, tenant_id, text, title) VALUES (?, ?, ?, ?, ?)",
                    (cid, doc_id, tenant_id, part, title),
                )

            if embed and parts and embed_texts and get_vector_store and should_external_embed:
                try:
                    use_external = should_external_embed(
                        visibility=visibility,
                        classification=classification,
                        ai_processing=ai_processing,
                    )
                    vectors, model = embed_texts(parts, force_local=not use_external)
                    store = get_vector_store(self.conn)
                    for cid, vec in zip(chunk_ids, vectors):
                        store.upsert(cid, vec, model=model)
                        embedded += 1
                except Exception:
                    # Keyword path remains usable even if embeddings fail
                    import logging

                    logging.getLogger("brain.repo").exception(
                        "embedding failed for document %s", doc_id
                    )

        self.conn.commit()
        return {
            "id": doc_id,
            "status": status,
            "version": version,
            "acl_revision": acl_revision,
            "chunks": chunk_count,
            "embedded": embedded,
            "quarantine": status == "quarantine",
            "findings": [f.kind for f in report.findings],
        }

    @staticmethod
    def _chunk_text(text: str, size: int, overlap: int = 200) -> list[str]:
        text = (text or "").strip()
        if not text:
            return []
        size = max(400, int(size or 1400))
        overlap = max(0, min(int(overlap or 0), size // 2))
        # Prefer markdown headings
        blocks = re.split(r"(?m)(?=^#{1,3}\s)", text)
        blocks = [b.strip() for b in blocks if b.strip()]
        if not blocks:
            blocks = [text]
        out: list[str] = []
        for block in blocks:
            if len(block) <= size:
                out.append(block)
                continue
            step = max(1, size - overlap)
            for i in range(0, len(block), step):
                piece = block[i : i + size].strip()
                if piece:
                    out.append(piece)
                if i + size >= len(block):
                    break
        return out

    def fetch_acl_chunk_candidates(
        self,
        principal: Principal,
        *,
        limit: int = 2000,
        index_zones: Iterable[str] | None = None,
        embedded_only: bool = False,
    ) -> list[dict[str, Any]]:
        """Load ACL-eligible chunks (for vector ranking). Filter stays in SQL."""
        filt = resolve_principal_policy(principal)
        if filt.deny_all:
            return []
        zones = list(index_zones) if index_zones is not None else self._zones_for(filt)
        if not zones:
            return []
        zone_placeholders = ",".join("?" * len(zones))
        acl_sql, acl_params = self._acl_sql(filt, principal)
        emb_clause = "AND c.embedding_json != '[]' AND length(c.embedding_json) > 2" if embedded_only else ""
        sql = f"""
        SELECT c.chunk_id, c.document_id, c.tenant_id, c.visibility, c.text,
               c.index_zone, c.channels_json, c.allowed_users_json, c.allowed_groups_json,
               c.allowed_services_json, c.embedding_json, d.title, d.type, d.project_id,
               d.source, e.thread_id,
               0.0 AS score
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        LEFT JOIN emails e ON d.type = 'email' AND d.id = ('doc-' || e.id)
        WHERE c.tenant_id = ?
          AND c.index_zone IN ({zone_placeholders})
          AND d.status = 'active'
          AND c.document_status = 'active'
          {emb_clause}
          AND ({acl_sql})
        ORDER BY c.document_id, c.ordinal
        LIMIT ?
        """
        params: list[Any] = [principal.tenant_id, *zones, *acl_params, limit]
        rows = self.conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def search_semantic(
        self,
        principal: Principal,
        query: str,
        *,
        limit: int = 8,
        candidate_limit: int = 2500,
    ) -> list[dict[str, Any]]:
        if not query.strip() or not embed_texts or not get_vector_store:
            return []
        candidates = self.fetch_acl_chunk_candidates(
            principal, limit=candidate_limit, embedded_only=True
        )
        if not candidates:
            return []
        # Prefer external query embedding unless forced local
        vectors, _model = embed_texts([query], force_local=False)
        store = get_vector_store(self.conn)
        return store.search(vectors[0], candidate_rows=candidates, limit=limit)

    def backfill_embeddings(
        self,
        *,
        tenant_id: str,
        limit: int = 500,
        only_missing: bool = True,
    ) -> dict[str, Any]:
        if not embed_texts or not get_vector_store or not should_external_embed:
            return {"ok": False, "error": "embedder_unavailable", "updated": 0}
        where = "c.tenant_id = ? AND c.document_status = 'active'"
        if only_missing:
            where += " AND (c.embedding_json = '[]' OR length(c.embedding_json) < 3)"
        rows = self.conn.execute(
            f"""
            SELECT c.chunk_id, c.text, c.visibility, c.classification,
                   d.ai_processing_json
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE {where}
            ORDER BY c.document_id, c.ordinal
            LIMIT ?
            """,
            (tenant_id, limit),
        ).fetchall()
        if not rows:
            return {"ok": True, "updated": 0, "scanned": 0}

        # Batch by external vs local policy
        external_batch: list[tuple[str, str]] = []
        local_batch: list[tuple[str, str]] = []
        for r in rows:
            ai = _loads(r["ai_processing_json"], {})
            vis = r["visibility"]
            classification = {"level": r["classification"] or "internal"}
            if should_external_embed(
                visibility=vis, classification=classification, ai_processing=ai
            ):
                external_batch.append((r["chunk_id"], r["text"]))
            else:
                local_batch.append((r["chunk_id"], r["text"]))

        store = get_vector_store(self.conn)
        updated = 0
        model = ""
        for force_local, batch in ((False, external_batch), (True, local_batch)):
            if not batch:
                continue
            texts = [t for _, t in batch]
            vectors, model = embed_texts(texts, force_local=force_local)
            for (cid, _t), vec in zip(batch, vectors):
                store.upsert(cid, vec, model=model)
                updated += 1
        self.conn.commit()
        return {
            "ok": True,
            "updated": updated,
            "scanned": len(rows),
            "external": len(external_batch),
            "local": len(local_batch),
            "model": model,
        }
    def search_chunks(
        self,
        principal: Principal,
        query: str,
        *,
        limit: int = 8,
        index_zones: Iterable[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Keyword/FTS search with ACL applied INSIDE the SQL query (not post-filter-only)."""
        filt = resolve_principal_policy(principal)
        if filt.deny_all:
            return []

        zones = list(index_zones) if index_zones is not None else self._zones_for(filt)
        if not zones:
            return []

        # Build FTS query: escape quotes
        q = (query or "").strip()
        if not q:
            return []
        fts_q = " ".join(f'"{t}"' if " " in t else t for t in re.findall(r"\w+", q, flags=re.U)[:12])
        if not fts_q:
            fts_q = q.replace('"', "")

        # Prefer OR matching so multi-word questions don't miss partial hits
        tokens = re.findall(r"\w+", q, flags=re.U)[:12]
        if len(tokens) >= 2:
            fts_or = " OR ".join(tokens)
        else:
            fts_or = fts_q

        zone_placeholders = ",".join("?" * len(zones))
        params: list[Any] = [fts_or, principal.tenant_id, *zones]

        acl_sql, acl_params = self._acl_sql(filt, principal)
        params.extend(acl_params)

        sql = f"""
        SELECT c.chunk_id, c.document_id, c.tenant_id, c.visibility, c.text,
               c.index_zone, c.channels_json, c.allowed_users_json, c.allowed_groups_json,
               c.allowed_services_json, d.title, d.type, d.project_id,
               d.source, e.thread_id,
               bm25(chunks_fts) AS score
        FROM chunks_fts
        JOIN chunks c ON c.chunk_id = chunks_fts.chunk_id
        JOIN documents d ON d.id = c.document_id
        LEFT JOIN emails e ON d.type = 'email' AND d.id = ('doc-' || e.id)
        WHERE chunks_fts MATCH ?
          AND c.tenant_id = ?
          AND c.index_zone IN ({zone_placeholders})
          AND d.status = 'active'
          AND c.document_status = 'active'
          AND ({acl_sql})
        ORDER BY score
        LIMIT ?
        """
        params.append(limit)
        try:
            rows = self.conn.execute(sql, params).fetchall()
        except sqlite3.OperationalError:
            # Fallback: LIKE search with same ACL predicate (still in-query)
            like = f"%{q}%"
            sql_like = f"""
            SELECT c.chunk_id, c.document_id, c.tenant_id, c.visibility, c.text,
                   c.index_zone, c.channels_json, c.allowed_users_json, c.allowed_groups_json,
                   c.allowed_services_json, d.title, d.type, d.project_id,
                   d.source, e.thread_id,
                   0.0 AS score
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            LEFT JOIN emails e ON d.type = 'email' AND d.id = ('doc-' || e.id)
            WHERE c.tenant_id = ?
              AND c.index_zone IN ({zone_placeholders})
              AND d.status = 'active'
              AND c.document_status = 'active'
              AND (c.text LIKE ? OR d.title LIKE ?)
              AND ({acl_sql})
            ORDER BY c.ordinal
            LIMIT ?
            """
            like_params: list[Any] = [principal.tenant_id, *zones, like, like, *acl_params, limit]
            rows = self.conn.execute(sql_like, like_params).fetchall()
        return [dict(r) for r in rows]

    def _zones_for(self, filt: ACLFilter) -> list[str]:
        if filt.deny_all:
            return []
        if filt.allow_all_in_tenant:
            return ["public", "private", "secret"]
        if filt.allowed_visibilities == {"public"} and not filt.require_assistant_safe:
            return ["public"]
        # office bots + internal
        return ["public", "private"]

    def _acl_sql(self, filt: ACLFilter, principal: Principal) -> tuple[str, list[Any]]:
        if filt.allow_all_in_tenant:
            return "1=1", []

        parts: list[str] = []
        params: list[Any] = []

        # published public zone
        if "public" in filt.allowed_visibilities or filt.require_assistant_safe:
            parts.append("(c.visibility = 'public' AND c.index_zone = 'public')")

        if filt.require_assistant_safe:
            parts.append(
                "(c.channels_json LIKE ? AND c.visibility IN ('company','public','team:sales','team:ops'))"
            )
            params.append("%office-assistant%")

        # explicit ACL allow on chunk
        parts.append("c.allowed_users_json LIKE ?")
        params.append(f"%{principal.principal_id}%")
        if principal.user_id:
            parts.append("c.allowed_users_json LIKE ?")
            params.append(f"%user:{principal.user_id}%")
        parts.append("c.allowed_services_json LIKE ?")
        params.append(f"%{principal.principal_id}%")
        for g in principal.groups:
            gnorm = g if g.startswith("group:") else f"group:{g}"
            short = g.removeprefix("group:")
            parts.append("(c.allowed_groups_json LIKE ? OR c.allowed_groups_json LIKE ?)")
            params.extend([f"%{gnorm}%", f"%{short}%"])

        # company visibility for human users only (not voice/text blanket)
        if principal.principal_id.startswith("user:") and "company" in filt.allowed_visibilities:
            parts.append("c.visibility = 'company'")

        for vis in filt.allowed_visibilities:
            if vis.startswith("team:"):
                parts.append("c.visibility = ?")
                params.append(vis)

        if not parts:
            return "0=1", []
        return " OR ".join(parts), params

    # ----- contacts -----

    def upsert_contact(
        self,
        *,
        tenant_id: str,
        display_name: str,
        emails: list[str] | None = None,
        phones: list[str] | None = None,
        title: str | None = None,
        company_name: str | None = None,
        visibility: str = "company",
        acl: dict | None = None,
        source: str | None = None,
        project_ids: list[str] | None = None,
        contact_id: str | None = None,
    ) -> str:
        emails = [e.strip().lower() for e in (emails or []) if e and e.strip()]
        # Normalize messy address strings to bare emails
        cleaned: list[str] = []
        for e in emails:
            m = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", e)
            if m:
                cleaned.append(m.group(0).lower())
        emails = sorted(set(cleaned))
        phones = [p.strip() for p in (phones or []) if p and p.strip()]
        if not emails and not phones:
            raise ValueError("contact needs email or phone")
        # Prefer human display name over email-local if provided
        display_name = (display_name or "").strip() or (emails[0].split("@")[0] if emails else phones[0])

        # Merge by email if exists
        found_id = None
        for em in emails:
            row = self.conn.execute(
                "SELECT contact_id FROM contact_emails WHERE tenant_id = ? AND email = ?",
                (tenant_id, em),
            ).fetchone()
            if row:
                found_id = row["contact_id"]
                break

        cid = found_id or contact_id or slug_id("contact", display_name, emails[0] if emails else phones[0])
        now = _now()
        acl = acl or {
            "allow_users": [],
            "allow_groups": ["group:management", "group:sales"],
            "allow_services": ["service:cursor-admin", "service:text-secretary"],
            "deny_users": [],
            "deny_groups": [],
        }
        classification = {
            "level": "confidential",
            "contains_personal_data": True,
            "contains_bank_secret": False,
            "contains_credentials": False,
        }

        existing = self.conn.execute("SELECT * FROM contacts WHERE id = ?", (cid,)).fetchone()
        if existing:
            old_emails = _loads(existing["emails_json"], [])
            old_phones = _loads(existing["phones_json"], [])
            emails = sorted(set(old_emails) | set(emails))
            # re-normalize after merge
            cleaned2: list[str] = []
            for e in emails:
                m = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", str(e))
                if m:
                    cleaned2.append(m.group(0).lower())
            emails = sorted(set(cleaned2))
            phones = sorted(set(old_phones) | set(phones))
            old_name = existing["display_name"] or ""
            # Prefer human FIO over email-local nicknames
            def _name_score(n: str) -> int:
                n = (n or "").strip()
                if not n:
                    return 0
                score = len(n)
                if " " in n:
                    score += 20
                if re.search(r"[А-Яа-яЁё]", n):
                    score += 30
                if "@" in n or "<" in n:
                    score -= 50
                return score

            if _name_score(old_name) >= _name_score(display_name):
                display_name = old_name
            title = title or existing["title"]
            company_name = company_name or existing["company_name"]

        self.conn.execute(
            """
            INSERT INTO contacts (
              id, tenant_id, display_name, emails_json, phones_json, title, company_name,
              visibility, acl_json, classification_json, project_ids_json, acl_revision,
              status, source, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'active', ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              display_name=excluded.display_name,
              emails_json=excluded.emails_json,
              phones_json=excluded.phones_json,
              title=COALESCE(excluded.title, contacts.title),
              company_name=COALESCE(excluded.company_name, contacts.company_name),
              source=excluded.source,
              updated_at=excluded.updated_at
            """,
            (
                cid,
                tenant_id,
                display_name,
                _j(emails),
                _j(phones),
                title,
                company_name,
                visibility,
                _j(acl),
                _j(classification),
                _j(project_ids or []),
                source,
                now,
            ),
        )
        for em in emails:
            self.conn.execute(
                "INSERT OR REPLACE INTO contact_emails(tenant_id, email, contact_id) VALUES (?, ?, ?)",
                (tenant_id, em, cid),
            )
        self.conn.commit()

        # Also index a searchable contact card document
        card = (
            f"# Contact: {display_name}\n\n"
            f"- Title: {title or '—'}\n"
            f"- Company: {company_name or '—'}\n"
            f"- Emails: {', '.join(emails) or '—'}\n"
            f"- Phones: {', '.join(phones) or '—'}\n"
        )
        self.upsert_document(
            doc_id=f"doc-{cid}",
            tenant_id=tenant_id,
            title=f"Contact: {display_name}",
            doc_type="contact",
            body=card,
            visibility=visibility if visibility != "public" else "company",
            acl=acl,
            classification=classification,
            channels=["office-assistant"] if visibility == "company" else [],
            source=source,
            index_zone="private",
        )
        return cid

    def find_contacts(
        self,
        principal: Principal,
        *,
        q: str = "",
        email: str = "",
        phone: str = "",
        company: str = "",
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        filt = resolve_principal_policy(principal)
        if filt.deny_all:
            return []
        # voice-public: no PII contacts
        if principal.principal_id == "service:voice-public":
            return []

        clauses = ["tenant_id = ?"]
        params: list[Any] = [principal.tenant_id]
        if email:
            clauses.append("emails_json LIKE ?")
            params.append(f"%{email.strip().lower()}%")
        if phone:
            digits = re.sub(r"\D", "", phone)
            clauses.append("phones_json LIKE ?")
            params.append(f"%{digits[-10:] if len(digits) >= 10 else phone}%")
        if company:
            clauses.append("company_name LIKE ?")
            params.append(f"%{company}%")
        if q:
            # Match ANY strong token (name parts), not only the full phrase.
            tokens = [t for t in re.split(r"[\s,;]+", q.strip()) if len(t) >= 2]
            if not tokens:
                tokens = [q.strip()]
            token_groups: list[str] = []
            for t in tokens[:6]:
                token_groups.append(
                    "(display_name LIKE ? OR emails_json LIKE ? OR phones_json LIKE ? "
                    "OR company_name LIKE ? OR IFNULL(title,'') LIKE ?)"
                )
                like = f"%{t}%"
                params.extend([like, like, like, like, like])
            # Also try full phrase
            token_groups.append(
                "(display_name LIKE ? OR emails_json LIKE ? OR phones_json LIKE ? "
                "OR company_name LIKE ? OR IFNULL(title,'') LIKE ?)"
            )
            like_full = f"%{q.strip()}%"
            params.extend([like_full, like_full, like_full, like_full, like_full])
            clauses.append("(" + " OR ".join(token_groups) + ")")

        sql = f"SELECT * FROM contacts WHERE {' AND '.join(clauses)} AND status = 'active' ORDER BY display_name LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(sql, params).fetchall()
        out = []
        for r in rows:
            out.append(
                {
                    "id": r["id"],
                    "display_name": r["display_name"],
                    "emails": _loads(r["emails_json"], []),
                    "phones": _loads(r["phones_json"], []),
                    "title": r["title"],
                    "company_name": r["company_name"],
                    "visibility": r["visibility"],
                    "source": r["source"],
                }
            )
        return out

    # ----- mail / threads -----

    def upsert_email_message(
        self,
        *,
        tenant_id: str,
        message_id: str,
        direction: str,
        subject: str,
        from_email: str,
        to_emails: list[str],
        cc_emails: list[str] | None = None,
        body_text: str,
        sent_at: str | None = None,
        acl: dict | None = None,
        from_name: str | None = None,
        participant_names: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        mid = message_id.strip().lower().strip("<>")
        existing = self.conn.execute(
            "SELECT id FROM emails WHERE tenant_id = ? AND message_id = ?",
            (tenant_id, mid),
        ).fetchone()
        if existing:
            # Still refresh contact display names if we learned better ones
            names = dict(participant_names or {})
            if from_email and from_name:
                names[from_email.lower()] = from_name
            for addr, name in names.items():
                if addr and name and "@" in addr:
                    try:
                        self.upsert_contact(
                            tenant_id=tenant_id,
                            display_name=name,
                            emails=[addr],
                            source="mail-ingest",
                            acl=acl or DEFAULT_MAIL_ACL,
                            visibility="restricted",
                        )
                    except Exception:  # noqa: BLE001
                        pass
            return {"id": existing["id"], "created": False}

        acl = acl or DEFAULT_MAIL_ACL
        thread_key = self._thread_key(subject, from_email, to_emails)
        thread_id = slug_id("thread", thread_key)
        email_id = slug_id("email", mid)
        now = _now()
        cc_emails = cc_emails or []
        bh = body_hash(body_text)
        names = dict(participant_names or {})
        if from_email and from_name:
            names[from_email.lower()] = from_name

        # ensure thread
        t = self.conn.execute("SELECT * FROM threads WHERE id = ?", (thread_id,)).fetchone()
        participants: list[str] = []
        # upsert contacts from participants
        for addr in {from_email, *to_emails, *cc_emails}:
            if not addr or "@" not in addr:
                continue
            addr = addr.lower()
            name = (names.get(addr) or "").strip() or addr.split("@")[0]
            cid = self.upsert_contact(
                tenant_id=tenant_id,
                display_name=name,
                emails=[addr],
                source="mail-ingest",
                acl=acl,
                visibility="restricted",
            )
            participants.append(cid)

        msg_ids = _loads(t["message_ids_json"], []) if t else []
        msg_ids.append(email_id)
        self.conn.execute(
            """
            INSERT INTO threads (
              id, tenant_id, subject, channel, project_id, participant_ids_json,
              message_ids_json, last_message_at, visibility, acl_json, topics_json,
              acl_revision, updated_at
            ) VALUES (?, ?, ?, 'email', NULL, ?, ?, ?, 'restricted', ?, '[]', 1, ?)
            ON CONFLICT(id) DO UPDATE SET
              message_ids_json=excluded.message_ids_json,
              participant_ids_json=excluded.participant_ids_json,
              last_message_at=excluded.last_message_at,
              updated_at=excluded.updated_at
            """,
            (
                thread_id,
                tenant_id,
                subject or "(no subject)",
                _j(sorted(set(participants))),
                _j(msg_ids),
                sent_at or now,
                _j(acl),
                now,
            ),
        )

        classification = {
            "level": "confidential",
            "contains_personal_data": True,
            "contains_bank_secret": False,
            "contains_credentials": False,
        }
        self.conn.execute(
            """
            INSERT INTO emails (
              id, tenant_id, message_id, direction, thread_id, subject, from_email,
              to_emails_json, cc_emails_json, sent_at, visibility, acl_json,
              classification_json, body_hash, body_text, attachment_ids_json,
              acl_revision, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'restricted', ?, ?, ?, ?, '[]', 1, 'active')
            """,
            (
                email_id,
                tenant_id,
                mid,
                direction,
                thread_id,
                subject or "(no subject)",
                from_email,
                _j(to_emails),
                _j(cc_emails),
                sent_at or now,
                _j(acl),
                _j(classification),
                bh,
                body_text,
            ),
        )
        self.conn.commit()

        doc_body = (
            f"# Email ({direction}): {subject}\n\n"
            f"- From: {from_email}\n"
            f"- To: {', '.join(to_emails)}\n"
            f"- Message-ID: {mid}\n"
            f"- Thread: {thread_id}\n\n"
            f"{body_text}"
        )
        indexed = self.upsert_document(
            doc_id=f"doc-{email_id}",
            tenant_id=tenant_id,
            title=f"Email: {subject}",
            doc_type="email",
            body=doc_body,
            visibility="restricted",
            acl=acl,
            classification=classification,
            channels=[],  # not voice-safe by default
            source=f"mail:{direction}",
            index_zone="private",
        )
        return {"id": email_id, "thread_id": thread_id, "created": True, "index": indexed}

    @staticmethod
    def _thread_key(subject: str, from_email: str, to_emails: list[str]) -> str:
        sub = re.sub(r"^(re|fw|fwd|aw|sv):\s*", "", (subject or "").strip(), flags=re.I)
        sub = re.sub(r"\s+", " ", sub).lower()
        people = ",".join(sorted({from_email.lower(), *[e.lower() for e in to_emails]}))
        return f"{sub}|{people}"

    def list_threads(
        self,
        principal: Principal,
        *,
        q: str = "",
        since: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        filt = resolve_principal_policy(principal)
        if filt.deny_all or principal.principal_id == "service:voice-public":
            return []
        clauses = ["tenant_id = ?"]
        params: list[Any] = [principal.tenant_id]
        if q:
            clauses.append("(subject LIKE ? OR topics_json LIKE ?)")
            params.extend([f"%{q}%", f"%{q}%"])
        if since:
            clauses.append("IFNULL(last_message_at,'') >= ?")
            params.append(since)
        sql = f"SELECT * FROM threads WHERE {' AND '.join(clauses)} ORDER BY last_message_at DESC LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(sql, params).fetchall()
        return [
            {
                "id": r["id"],
                "subject": r["subject"],
                "channel": r["channel"],
                "project_id": r["project_id"],
                "last_message_at": r["last_message_at"],
                "topics": _loads(r["topics_json"], []),
                "message_ids": _loads(r["message_ids_json"], []),
            }
            for r in rows
        ]

    # ----- files -----

    def get_file_by_path(self, tenant_id: str, path: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM files WHERE tenant_id=? AND path=?",
            (tenant_id, path),
        ).fetchone()
        return dict(row) if row else None

    def find_document_by_body_hash(
        self,
        tenant_id: str,
        bh: str,
        *,
        exclude_id: str | None = None,
    ) -> dict[str, Any] | None:
        if not bh:
            return None
        if exclude_id:
            row = self.conn.execute(
                """
                SELECT id, title, type, source, body_hash FROM documents
                WHERE tenant_id=? AND body_hash=? AND status='active' AND id!=?
                LIMIT 1
                """,
                (tenant_id, bh, exclude_id),
            ).fetchone()
        else:
            row = self.conn.execute(
                """
                SELECT id, title, type, source, body_hash FROM documents
                WHERE tenant_id=? AND body_hash=? AND status='active'
                LIMIT 1
                """,
                (tenant_id, bh),
            ).fetchone()
        return dict(row) if row else None

    def deprecate_documents_not_in(
        self,
        *,
        tenant_id: str,
        source: str,
        keep_ids: set[str],
        doc_type: str | None = None,
    ) -> int:
        """Soft-delete stale docs from a source that are no longer produced by ingest."""
        rows = self.conn.execute(
            """
            SELECT id FROM documents
            WHERE tenant_id=? AND source=? AND status='active'
            """,
            (tenant_id, source),
        ).fetchall()
        n = 0
        now = _now()
        for r in rows:
            if r["id"] in keep_ids:
                continue
            if doc_type:
                typ = self.conn.execute(
                    "SELECT type FROM documents WHERE id=?", (r["id"],)
                ).fetchone()
                if typ and typ["type"] != doc_type:
                    continue
            self.conn.execute(
                "UPDATE documents SET status='deprecated', updated_at=? WHERE id=?",
                (now, r["id"]),
            )
            n += 1
        if n:
            self.conn.commit()
        return n

    def upsert_file_asset(
        self,
        *,
        tenant_id: str,
        path: str,
        filename: str,
        content_hash: str,
        source: str,
        text_excerpt: str = "",
        visibility: str = "company",
        acl: dict | None = None,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        acl = acl or {
            "allow_users": [],
            "allow_groups": ["group:management"],
            "allow_services": ["service:cursor-admin", "service:text-secretary"],
            "deny_users": [],
            "deny_groups": [],
        }
        fid = slug_id("file", path)
        now = _now()
        prev = self.get_file_by_path(tenant_id, path)
        if prev and prev.get("content_hash") == content_hash:
            # unchanged on disk — do not re-chunk / re-embed
            return {
                "id": fid,
                "unchanged": True,
                "index": {
                    "id": f"doc-{fid}",
                    "unchanged": True,
                    "chunks": self.conn.execute(
                        "SELECT COUNT(*) AS n FROM chunks WHERE document_id=?",
                        (f"doc-{fid}",),
                    ).fetchone()["n"],
                },
            }

        # Same bytes already indexed under another path → keep one searchable copy
        other = self.conn.execute(
            """
            SELECT id, path FROM files
            WHERE tenant_id=? AND content_hash=? AND path!=? AND status='active'
            LIMIT 1
            """,
            (tenant_id, content_hash, path),
        ).fetchone()
        if other:
            # still record this path in files table for inventory, without second doc
            self.conn.execute(
                """
                INSERT INTO files (
                  id, tenant_id, path, filename, content_hash, source, project_id,
                  visibility, acl_json, classification_json, text_excerpt, acl_revision,
                  status, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '{}', ?, 1, 'active', ?)
                ON CONFLICT(tenant_id, path) DO UPDATE SET
                  content_hash=excluded.content_hash,
                  text_excerpt=excluded.text_excerpt,
                  updated_at=excluded.updated_at,
                  filename=excluded.filename
                """,
                (
                    fid,
                    tenant_id,
                    path,
                    filename,
                    content_hash,
                    source,
                    project_id,
                    visibility,
                    _j(acl),
                    text_excerpt[:20000],
                    now,
                ),
            )
            self.conn.commit()
            return {
                "id": fid,
                "duplicate_of": other["id"],
                "duplicate_path": other["path"],
                "skipped_duplicate_content": True,
                "index": {"id": f"doc-{other['id']}", "chunks": 0, "unchanged": True},
            }

        self.conn.execute(
            """
            INSERT INTO files (
              id, tenant_id, path, filename, content_hash, source, project_id,
              visibility, acl_json, classification_json, text_excerpt, acl_revision,
              status, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '{}', ?, 1, 'active', ?)
            ON CONFLICT(tenant_id, path) DO UPDATE SET
              content_hash=excluded.content_hash,
              text_excerpt=excluded.text_excerpt,
              updated_at=excluded.updated_at,
              filename=excluded.filename
            """,
            (
                fid,
                tenant_id,
                path,
                filename,
                content_hash,
                source,
                project_id,
                visibility,
                _j(acl),
                text_excerpt[:20000],
                now,
            ),
        )
        self.conn.commit()
        body = f"# File: {filename}\n\nPath: `{path}`\nSource: {source}\n\n{text_excerpt[:15000]}"
        indexed = self.upsert_document(
            doc_id=f"doc-{fid}",
            tenant_id=tenant_id,
            title=f"File: {filename}",
            doc_type="file",
            body=body,
            visibility=visibility if visibility != "public" else "company",
            acl=acl,
            channels=["office-assistant"] if visibility == "company" else [],
            source=f"file:{source}",
            index_zone="private",
            project_id=project_id,
        )
        return {"id": fid, "index": indexed}

    # ----- audit / ingest state -----

    def write_audit(self, record: dict[str, Any]) -> None:
        self.conn.execute(
            """
            INSERT INTO audit_log (
              principal_id, tenant_id, query_hash, query_preview_redacted,
              retrieved_doc_ids_json, denied_doc_count, purpose, request_id, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["principal_id"],
                record["tenant_id"],
                record["query_hash"],
                record["query_preview_redacted"],
                _j(record.get("retrieved_doc_ids") or []),
                int(record.get("denied_doc_count") or 0),
                record["purpose"],
                record["request_id"],
                record["timestamp"],
            ),
        )
        self.conn.commit()

    def set_ingest_state(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO ingest_state(key, value, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, value, _now()),
        )
        self.conn.commit()

    def get_ingest_state(self, key: str) -> str | None:
        row = self.conn.execute(
            "SELECT value FROM ingest_state WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else None

    def stats(self, tenant_id: str) -> dict[str, int]:
        def cnt(table: str) -> int:
            row = self.conn.execute(
                f"SELECT COUNT(*) AS c FROM {table} WHERE tenant_id = ?", (tenant_id,)
            ).fetchone()
            return int(row["c"])

        return {
            "documents": cnt("documents"),
            "chunks": cnt("chunks"),
            "contacts": cnt("contacts"),
            "emails": cnt("emails"),
            "threads": cnt("threads"),
            "files": cnt("files"),
        }
