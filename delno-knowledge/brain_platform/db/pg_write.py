"""Incremental SQLite → Postgres dual-write helpers (row-level)."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Iterable

from brain_platform.db.pg import connect_postgres, database_url, store_backend

logger = logging.getLogger("brain.pg_write")


def dual_write_enabled() -> bool:
    raw = (os.getenv("BRAIN_DUAL_WRITE") or "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    if raw in ("1", "true", "yes", "on"):
        return True
    # Default on when search already uses Postgres
    return store_backend() == "postgres" and bool(database_url())


def _parse_embedding(raw: str | None) -> str | None:
    if not raw or raw == "[]":
        return None
    try:
        vec = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(vec, list) or len(vec) != 1536:
        return None
    return "[" + ",".join(str(float(x)) for x in vec) + "]"


def _row(conn, sql: str, params: tuple | list) -> dict[str, Any] | None:
    cur = conn.execute(sql, params)
    r = cur.fetchone()
    if r is None:
        return None
    return dict(r)


def _rows(conn, sql: str, params: tuple | list) -> list[dict[str, Any]]:
    cur = conn.execute(sql, params)
    return [dict(r) for r in cur.fetchall()]


def upsert_document_tree(sqlite_conn, pg_conn, document_id: str) -> dict[str, Any]:
    doc = _row(sqlite_conn, "SELECT * FROM documents WHERE id = ?", (document_id,))
    if not doc:
        with pg_conn.cursor() as cur:
            cur.execute("DELETE FROM chunks WHERE document_id = %s", (document_id,))
            cur.execute("DELETE FROM documents WHERE id = %s", (document_id,))
        pg_conn.commit()
        return {"ok": True, "deleted": True, "document_id": document_id}

    payload = {
        **doc,
        "publication_json": doc.get("publication_json") or "{}",
        "ai_processing_json": doc.get("ai_processing_json") or "{}",
        "channels_json": doc.get("channels_json") or "[]",
        "acl_json": doc.get("acl_json") or "{}",
        "classification_json": doc.get("classification_json") or "{}",
        "body": doc.get("body") or "",
        "body_hash": doc.get("body_hash") or "",
        "index_zone": doc.get("index_zone") or "private",
        "status": doc.get("status") or "active",
        "version": doc.get("version") or 1,
        "acl_revision": doc.get("acl_revision") or 1,
    }
    with pg_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO documents (
              id, tenant_id, title, type, visibility, acl_json, classification_json,
              publication_json, channels_json, ai_processing_json, status, version,
              acl_revision, source, project_id, body, body_hash, index_zone,
              created_at, updated_at
            ) VALUES (
              %(id)s, %(tenant_id)s, %(title)s, %(type)s, %(visibility)s,
              %(acl_json)s::jsonb, %(classification_json)s::jsonb,
              COALESCE(NULLIF(%(publication_json)s,''), '{}')::jsonb,
              %(channels_json)s::jsonb, %(ai_processing_json)s::jsonb,
              %(status)s, %(version)s, %(acl_revision)s, %(source)s, %(project_id)s,
              %(body)s, %(body_hash)s, %(index_zone)s,
              COALESCE(%(created_at)s::timestamptz, NOW()),
              COALESCE(%(updated_at)s::timestamptz, NOW())
            )
            ON CONFLICT (id) DO UPDATE SET
              title = EXCLUDED.title,
              type = EXCLUDED.type,
              visibility = EXCLUDED.visibility,
              acl_json = EXCLUDED.acl_json,
              classification_json = EXCLUDED.classification_json,
              publication_json = EXCLUDED.publication_json,
              channels_json = EXCLUDED.channels_json,
              ai_processing_json = EXCLUDED.ai_processing_json,
              status = EXCLUDED.status,
              version = EXCLUDED.version,
              acl_revision = EXCLUDED.acl_revision,
              source = EXCLUDED.source,
              project_id = EXCLUDED.project_id,
              body = EXCLUDED.body,
              body_hash = EXCLUDED.body_hash,
              index_zone = EXCLUDED.index_zone,
              updated_at = EXCLUDED.updated_at
            """,
            payload,
        )
        cur.execute("DELETE FROM chunks WHERE document_id = %s", (document_id,))
        chunks = _rows(
            sqlite_conn, "SELECT * FROM chunks WHERE document_id = ?", (document_id,)
        )
        n_emb = 0
        for r in chunks:
            emb_lit = _parse_embedding(r.get("embedding_json"))
            base = {
                **{k: r.get(k) for k in r.keys()},
                "allowed_users_json": r.get("allowed_users_json") or "[]",
                "allowed_groups_json": r.get("allowed_groups_json") or "[]",
                "allowed_services_json": r.get("allowed_services_json") or "[]",
                "channels_json": r.get("channels_json") or "[]",
                "embedding_json": r.get("embedding_json") or "[]",
            }
            if emb_lit is None:
                cur.execute(
                    """
                    INSERT INTO chunks (
                      chunk_id, document_id, tenant_id, visibility,
                      allowed_users_json, allowed_groups_json, allowed_services_json,
                      classification, acl_revision, document_status, document_version,
                      index_zone, channels_json, ordinal, text, embedding_json, embedding
                    ) VALUES (
                      %(chunk_id)s, %(document_id)s, %(tenant_id)s, %(visibility)s,
                      %(allowed_users_json)s::jsonb, %(allowed_groups_json)s::jsonb,
                      %(allowed_services_json)s::jsonb, %(classification)s, %(acl_revision)s,
                      %(document_status)s, %(document_version)s, %(index_zone)s,
                      %(channels_json)s::jsonb, %(ordinal)s, %(text)s, %(embedding_json)s,
                      NULL
                    )
                    """,
                    base,
                )
            else:
                n_emb += 1
                cur.execute(
                    """
                    INSERT INTO chunks (
                      chunk_id, document_id, tenant_id, visibility,
                      allowed_users_json, allowed_groups_json, allowed_services_json,
                      classification, acl_revision, document_status, document_version,
                      index_zone, channels_json, ordinal, text, embedding_json, embedding
                    ) VALUES (
                      %(chunk_id)s, %(document_id)s, %(tenant_id)s, %(visibility)s,
                      %(allowed_users_json)s::jsonb, %(allowed_groups_json)s::jsonb,
                      %(allowed_services_json)s::jsonb, %(classification)s, %(acl_revision)s,
                      %(document_status)s, %(document_version)s, %(index_zone)s,
                      %(channels_json)s::jsonb, %(ordinal)s, %(text)s, %(embedding_json)s,
                      %(emb_lit)s::vector
                    )
                    """,
                    {**base, "emb_lit": emb_lit},
                )
    pg_conn.commit()
    return {
        "ok": True,
        "document_id": document_id,
        "chunks": len(chunks),
        "embeddings": n_emb,
    }


def upsert_contact_row(sqlite_conn, pg_conn, contact_id: str) -> dict[str, Any]:
    c = _row(sqlite_conn, "SELECT * FROM contacts WHERE id = ?", (contact_id,))
    if not c:
        return {"ok": True, "skipped": True}
    with pg_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO contacts (
              id, tenant_id, display_name, emails_json, phones_json, title, company_name,
              company_entity_id, visibility, acl_json, classification_json, project_ids_json,
              acl_revision, status, source, updated_at
            ) VALUES (
              %(id)s, %(tenant_id)s, %(display_name)s, %(emails_json)s::jsonb,
              %(phones_json)s::jsonb, %(title)s, %(company_name)s, %(company_entity_id)s,
              %(visibility)s, %(acl_json)s::jsonb, %(classification_json)s::jsonb,
              %(project_ids_json)s::jsonb, %(acl_revision)s, %(status)s, %(source)s,
              COALESCE(%(updated_at)s::timestamptz, NOW())
            )
            ON CONFLICT (id) DO UPDATE SET
              display_name = EXCLUDED.display_name,
              emails_json = EXCLUDED.emails_json,
              phones_json = EXCLUDED.phones_json,
              title = EXCLUDED.title,
              company_name = EXCLUDED.company_name,
              visibility = EXCLUDED.visibility,
              source = EXCLUDED.source,
              updated_at = EXCLUDED.updated_at
            """,
            {
                **c,
                "emails_json": c.get("emails_json") or "[]",
                "phones_json": c.get("phones_json") or "[]",
                "acl_json": c.get("acl_json") or "{}",
                "classification_json": c.get("classification_json") or "{}",
                "project_ids_json": c.get("project_ids_json") or "[]",
                "status": c.get("status") or "active",
                "acl_revision": c.get("acl_revision") or 1,
            },
        )
        for er in _rows(
            sqlite_conn,
            "SELECT * FROM contact_emails WHERE contact_id = ?",
            (contact_id,),
        ):
            cur.execute(
                """
                INSERT INTO contact_emails(tenant_id, email, contact_id)
                VALUES (%(tenant_id)s, %(email)s, %(contact_id)s)
                ON CONFLICT DO NOTHING
                """,
                dict(er),
            )
    pg_conn.commit()
    return {"ok": True, "contact_id": contact_id}


def upsert_email_tree(sqlite_conn, pg_conn, email_id: str) -> dict[str, Any]:
    email = _row(sqlite_conn, "SELECT * FROM emails WHERE id = ?", (email_id,))
    if not email:
        return {"ok": True, "skipped": True}
    thread_id = email.get("thread_id")
    if thread_id:
        thr = _row(sqlite_conn, "SELECT * FROM threads WHERE id = ?", (thread_id,))
        if thr:
            with pg_conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO threads (
                      id, tenant_id, subject, channel, project_id, participant_ids_json,
                      message_ids_json, last_message_at, visibility, acl_json, topics_json,
                      acl_revision, updated_at
                    ) VALUES (
                      %(id)s, %(tenant_id)s, %(subject)s, %(channel)s, %(project_id)s,
                      %(participant_ids_json)s::jsonb, %(message_ids_json)s::jsonb,
                      NULLIF(%(last_message_at)s,'')::timestamptz, %(visibility)s,
                      %(acl_json)s::jsonb, %(topics_json)s::jsonb, %(acl_revision)s,
                      COALESCE(NULLIF(%(updated_at)s,'')::timestamptz, NOW())
                    )
                    ON CONFLICT (id) DO UPDATE SET
                      subject = EXCLUDED.subject,
                      participant_ids_json = EXCLUDED.participant_ids_json,
                      message_ids_json = EXCLUDED.message_ids_json,
                      last_message_at = EXCLUDED.last_message_at,
                      topics_json = EXCLUDED.topics_json,
                      updated_at = EXCLUDED.updated_at
                    """,
                    {
                        **thr,
                        "participant_ids_json": thr.get("participant_ids_json") or "[]",
                        "message_ids_json": thr.get("message_ids_json") or "[]",
                        "acl_json": thr.get("acl_json") or "{}",
                        "topics_json": thr.get("topics_json") or "[]",
                        "last_message_at": thr.get("last_message_at") or "",
                        "updated_at": thr.get("updated_at") or "",
                        "acl_revision": thr.get("acl_revision") or 1,
                    },
                )
            pg_conn.commit()

    with pg_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO emails (
              id, tenant_id, message_id, direction, thread_id, subject, from_email,
              to_emails_json, cc_emails_json, sent_at, project_id, visibility, acl_json,
              classification_json, body_hash, body_text, attachment_ids_json,
              acl_revision, status
            ) VALUES (
              %(id)s, %(tenant_id)s, %(message_id)s, %(direction)s, %(thread_id)s,
              %(subject)s, %(from_email)s, %(to_emails_json)s::jsonb, %(cc_emails_json)s::jsonb,
              %(sent_at)s, %(project_id)s, %(visibility)s, %(acl_json)s::jsonb,
              %(classification_json)s::jsonb, %(body_hash)s, %(body_text)s,
              %(attachment_ids_json)s::jsonb, %(acl_revision)s, %(status)s
            )
            ON CONFLICT (id) DO UPDATE SET
              subject = EXCLUDED.subject,
              body_text = EXCLUDED.body_text,
              body_hash = EXCLUDED.body_hash,
              status = EXCLUDED.status
            """,
            {
                **{k: email.get(k) for k in email.keys()},
                "subject": email.get("subject") or "",
                "from_email": email.get("from_email") or "",
                "to_emails_json": email.get("to_emails_json") or "[]",
                "cc_emails_json": email.get("cc_emails_json") or "[]",
                "acl_json": email.get("acl_json") or "{}",
                "classification_json": email.get("classification_json") or "{}",
                "attachment_ids_json": email.get("attachment_ids_json") or "[]",
                "body_text": email.get("body_text") or "",
                "body_hash": email.get("body_hash") or "",
                "status": email.get("status") or "active",
                "acl_revision": email.get("acl_revision") or 1,
            },
        )
    pg_conn.commit()
    doc_id = f"doc-{email_id}"
    doc_stats = upsert_document_tree(sqlite_conn, pg_conn, doc_id)
    return {"ok": True, "email_id": email_id, "document": doc_stats}


def sync_documents(sqlite_conn, document_ids: Iterable[str]) -> dict[str, Any]:
    if not dual_write_enabled():
        return {"ok": True, "skipped": True, "reason": "dual_write_disabled"}
    ids = [d for d in document_ids if d]
    if not ids:
        return {"ok": True, "synced": 0}
    try:
        pg = connect_postgres()
    except Exception as exc:  # noqa: BLE001
        logger.exception("dual-write connect failed")
        return {"ok": False, "error": str(exc)}
    out = []
    try:
        for did in ids:
            try:
                out.append(upsert_document_tree(sqlite_conn, pg, did))
            except Exception as exc:  # noqa: BLE001
                logger.exception("dual-write document %s failed", did)
                out.append({"ok": False, "document_id": did, "error": str(exc)})
                pg.rollback()
        return {"ok": all(x.get("ok") for x in out), "synced": len(out), "results": out}
    finally:
        pg.close()


def sync_email(sqlite_conn, email_id: str) -> dict[str, Any]:
    if not dual_write_enabled():
        return {"ok": True, "skipped": True}
    try:
        pg = connect_postgres()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
    try:
        return upsert_email_tree(sqlite_conn, pg, email_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("dual-write email failed")
        pg.rollback()
        return {"ok": False, "error": str(exc)}
    finally:
        pg.close()


def sync_contact(sqlite_conn, contact_id: str) -> dict[str, Any]:
    if not dual_write_enabled():
        return {"ok": True, "skipped": True}
    try:
        pg = connect_postgres()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
    try:
        return upsert_contact_row(sqlite_conn, pg, contact_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("dual-write contact failed")
        pg.rollback()
        return {"ok": False, "error": str(exc)}
    finally:
        pg.close()
