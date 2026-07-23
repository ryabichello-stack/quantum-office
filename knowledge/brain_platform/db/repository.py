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
        chunk_size: int = 1800,
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
        now = _now()
        bh = body_hash(body)

        existing = self.conn.execute(
            "SELECT version, acl_revision FROM documents WHERE id = ?", (doc_id,)
        ).fetchone()
        version = (existing["version"] + 1) if existing else 1
        acl_revision = (existing["acl_revision"] + 1) if existing else 1

        self.conn.execute(
            """
            INSERT INTO documents (
              id, tenant_id, title, type, visibility, acl_json, classification_json,
              publication_json, channels_json, ai_processing_json, status, version,
              acl_revision, source, project_id, body, body_hash, index_zone,
              created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, '{}', ?, '{}', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              title=excluded.title,
              type=excluded.type,
              visibility=excluded.visibility,
              acl_json=excluded.acl_json,
              classification_json=excluded.classification_json,
              channels_json=excluded.channels_json,
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
                _j(channels),
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
        if status != "quarantine":
            parts = self._chunk_text(body, chunk_size)
            chunk_count = len(parts)
            allow_users = list(acl.get("allow_users") or [])
            allow_groups = [g.removeprefix("group:") for g in (acl.get("allow_groups") or [])]
            allow_services = list(acl.get("allow_services") or [])
            class_level = classification.get("level", "internal")
            for i, part in enumerate(parts):
                cid = f"{doc_id}:chunk-{i:04d}"
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

        self.conn.commit()
        return {
            "id": doc_id,
            "status": status,
            "version": version,
            "acl_revision": acl_revision,
            "chunks": chunk_count,
            "quarantine": status == "quarantine",
            "findings": [f.kind for f in report.findings],
        }

    @staticmethod
    def _chunk_text(text: str, size: int) -> list[str]:
        text = (text or "").strip()
        if not text:
            return []
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
            for i in range(0, len(block), size):
                out.append(block[i : i + size])
        return out

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

        zone_placeholders = ",".join("?" * len(zones))
        params: list[Any] = [fts_q, principal.tenant_id, *zones]

        acl_sql, acl_params = self._acl_sql(filt, principal)
        params.extend(acl_params)

        sql = f"""
        SELECT c.chunk_id, c.document_id, c.tenant_id, c.visibility, c.text,
               c.index_zone, c.channels_json, c.allowed_users_json, c.allowed_groups_json,
               c.allowed_services_json, d.title, d.type, d.project_id,
               bm25(chunks_fts) AS score
        FROM chunks_fts
        JOIN chunks c ON c.chunk_id = chunks_fts.chunk_id
        JOIN documents d ON d.id = c.document_id
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
                   0.0 AS score
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
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
        phones = [p.strip() for p in (phones or []) if p and p.strip()]
        if not emails and not phones:
            raise ValueError("contact needs email or phone")

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
            phones = sorted(set(old_phones) | set(phones))
            display_name = display_name or existing["display_name"]
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
            clauses.append(
                "(display_name LIKE ? OR emails_json LIKE ? OR phones_json LIKE ? OR company_name LIKE ? OR IFNULL(title,'') LIKE ?)"
            )
            like = f"%{q}%"
            params.extend([like, like, like, like, like])

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
    ) -> dict[str, Any]:
        mid = message_id.strip().lower().strip("<>")
        existing = self.conn.execute(
            "SELECT id FROM emails WHERE tenant_id = ? AND message_id = ?",
            (tenant_id, mid),
        ).fetchone()
        if existing:
            return {"id": existing["id"], "created": False}

        acl = acl or DEFAULT_MAIL_ACL
        thread_key = self._thread_key(subject, from_email, to_emails)
        thread_id = slug_id("thread", thread_key)
        email_id = slug_id("email", mid)
        now = _now()
        cc_emails = cc_emails or []
        bh = body_hash(body_text)

        # ensure thread
        t = self.conn.execute("SELECT * FROM threads WHERE id = ?", (thread_id,)).fetchone()
        participants: list[str] = []
        # upsert contacts from participants
        for addr in {from_email, *to_emails, *cc_emails}:
            if not addr:
                continue
            name = addr.split("@")[0]
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
