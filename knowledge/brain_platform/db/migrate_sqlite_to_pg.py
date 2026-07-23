"""Copy Second Brain corpus from SQLite → Postgres (no data loss)."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from typing import Any

logger = logging.getLogger("brain.migrate")

TABLES_ORDER = [
    "meta",
    "documents",
    "chunks",
    "contacts",
    "contact_emails",
    "threads",
    "emails",
    "files",
    "entities",
    "edges",
    "audit_log",
    "ingest_state",
]


def _sqlite_rows(conn: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(f"SELECT * FROM {table}").fetchall()
    except sqlite3.OperationalError:
        return []
    return [dict(r) for r in rows]


def _parse_embedding(raw: str | None) -> list[float] | None:
    if not raw or raw == "[]":
        return None
    try:
        vec = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(vec, list) or not vec:
        return None
    # Only load 1536-d OpenAI vectors into pgvector column
    if len(vec) != 1536:
        return None
    return [float(x) for x in vec]


def migrate(sqlite_path: str, pg_dsn: str, *, truncate: bool = True) -> dict[str, Any]:
    from brain_platform.db.pg import ensure_hnsw_index, init_postgres

    sq = sqlite3.connect(sqlite_path)
    sq.row_factory = sqlite3.Row
    pg = init_postgres(pg_dsn)

    stats: dict[str, Any] = {"tables": {}, "embeddings_loaded": 0, "embeddings_skipped": 0}

    with pg.cursor() as cur:
        if truncate:
            # FK-safe truncate
            cur.execute(
                "TRUNCATE TABLE "
                "document_entities, entity_versions, entity_aliases, edges, entities, "
                "chunks, emails, threads, contact_emails, contacts, files, documents, "
                "audit_log, ingest_state, meta "
                "RESTART IDENTITY CASCADE"
            )

        # meta
        for r in _sqlite_rows(sq, "meta"):
            cur.execute(
                "INSERT INTO meta(key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value",
                (r["key"], r["value"]),
            )
        stats["tables"]["meta"] = cur.rowcount

        # documents
        docs = _sqlite_rows(sq, "documents")
        for r in docs:
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
                ON CONFLICT (id) DO NOTHING
                """,
                {
                    **r,
                    "publication_json": r.get("publication_json") or "{}",
                    "ai_processing_json": r.get("ai_processing_json") or "{}",
                    "channels_json": r.get("channels_json") or "[]",
                    "acl_json": r.get("acl_json") or "{}",
                    "classification_json": r.get("classification_json") or "{}",
                },
            )
        stats["tables"]["documents"] = len(docs)

        # chunks
        chunks = _sqlite_rows(sq, "chunks")
        for r in chunks:
            emb = _parse_embedding(r.get("embedding_json"))
            if emb:
                stats["embeddings_loaded"] += 1
                emb_lit = "[" + ",".join(str(x) for x in emb) + "]"
            else:
                stats["embeddings_skipped"] += 1
                emb_lit = None
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
                  CASE WHEN %(emb_lit)s IS NULL THEN NULL ELSE %(emb_lit)s::vector END
                )
                ON CONFLICT (chunk_id) DO UPDATE SET
                  document_id = EXCLUDED.document_id,
                  tenant_id = EXCLUDED.tenant_id,
                  visibility = EXCLUDED.visibility,
                  allowed_users_json = EXCLUDED.allowed_users_json,
                  allowed_groups_json = EXCLUDED.allowed_groups_json,
                  allowed_services_json = EXCLUDED.allowed_services_json,
                  classification = EXCLUDED.classification,
                  acl_revision = EXCLUDED.acl_revision,
                  document_status = EXCLUDED.document_status,
                  document_version = EXCLUDED.document_version,
                  index_zone = EXCLUDED.index_zone,
                  channels_json = EXCLUDED.channels_json,
                  ordinal = EXCLUDED.ordinal,
                  text = EXCLUDED.text,
                  embedding_json = EXCLUDED.embedding_json,
                  embedding = EXCLUDED.embedding
                """,
                {
                    **{k: r.get(k) for k in r.keys()},
                    "allowed_users_json": r.get("allowed_users_json") or "[]",
                    "allowed_groups_json": r.get("allowed_groups_json") or "[]",
                    "allowed_services_json": r.get("allowed_services_json") or "[]",
                    "channels_json": r.get("channels_json") or "[]",
                    "embedding_json": r.get("embedding_json") or "[]",
                    "emb_lit": emb_lit,
                },
            )
        stats["tables"]["chunks"] = len(chunks)

        # contacts
        contacts = _sqlite_rows(sq, "contacts")
        for r in contacts:
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
                ON CONFLICT (id) DO NOTHING
                """,
                {
                    **r,
                    "emails_json": r.get("emails_json") or "[]",
                    "phones_json": r.get("phones_json") or "[]",
                    "acl_json": r.get("acl_json") or "{}",
                    "classification_json": r.get("classification_json") or "{}",
                    "project_ids_json": r.get("project_ids_json") or "[]",
                },
            )
        stats["tables"]["contacts"] = len(contacts)

        for r in _sqlite_rows(sq, "contact_emails"):
            cur.execute(
                """
                INSERT INTO contact_emails(tenant_id, email, contact_id)
                VALUES (%(tenant_id)s, %(email)s, %(contact_id)s)
                ON CONFLICT DO NOTHING
                """,
                dict(r),
            )

        threads = _sqlite_rows(sq, "threads")
        for r in threads:
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
                ON CONFLICT (id) DO NOTHING
                """,
                {
                    **r,
                    "participant_ids_json": r.get("participant_ids_json") or "[]",
                    "message_ids_json": r.get("message_ids_json") or "[]",
                    "acl_json": r.get("acl_json") or "{}",
                    "topics_json": r.get("topics_json") or "[]",
                    "last_message_at": r.get("last_message_at") or "",
                    "updated_at": r.get("updated_at") or "",
                },
            )
        stats["tables"]["threads"] = len(threads)

        emails = _sqlite_rows(sq, "emails")
        for r in emails:
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
                ON CONFLICT (id) DO NOTHING
                """,
                {
                    **{k: r.get(k) for k in r.keys()},
                    "subject": r.get("subject") or "",
                    "from_email": r.get("from_email") or "",
                    "to_emails_json": r.get("to_emails_json") or "[]",
                    "cc_emails_json": r.get("cc_emails_json") or "[]",
                    "acl_json": r.get("acl_json") or "{}",
                    "classification_json": r.get("classification_json") or "{}",
                    "attachment_ids_json": r.get("attachment_ids_json") or "[]",
                    "body_text": r.get("body_text") or "",
                    "body_hash": r.get("body_hash") or "",
                    "status": r.get("status") or "active",
                    "acl_revision": r.get("acl_revision") or 1,
                },
            )
        stats["tables"]["emails"] = len(emails)

        files = _sqlite_rows(sq, "files")
        for r in files:
            cur.execute(
                """
                INSERT INTO files (
                  id, tenant_id, path, filename, content_hash, source, project_id,
                  visibility, acl_json, classification_json, text_excerpt, acl_revision,
                  status, updated_at
                ) VALUES (
                  %(id)s, %(tenant_id)s, %(path)s, %(filename)s, %(content_hash)s,
                  %(source)s, %(project_id)s, %(visibility)s, %(acl_json)s::jsonb,
                  %(classification_json)s::jsonb, %(text_excerpt)s, %(acl_revision)s,
                  %(status)s, COALESCE(NULLIF(%(updated_at)s,'')::timestamptz, NOW())
                )
                ON CONFLICT (id) DO NOTHING
                """,
                {
                    **r,
                    "acl_json": r.get("acl_json") or "{}",
                    "classification_json": r.get("classification_json") or "{}",
                    "text_excerpt": r.get("text_excerpt") or "",
                    "updated_at": r.get("updated_at") or "",
                    "status": r.get("status") or "active",
                },
            )
        stats["tables"]["files"] = len(files)

        # optional graph stubs
        for r in _sqlite_rows(sq, "entities"):
            cur.execute(
                """
                INSERT INTO entities (id, tenant_id, kind, canonical_name, metadata_json, visibility, created_at, updated_at)
                VALUES (%(id)s, %(tenant_id)s, %(kind)s, %(canonical_name)s, %(metadata_json)s::jsonb,
                        %(visibility)s, COALESCE(%(created_at)s::timestamptz, NOW()),
                        COALESCE(%(updated_at)s::timestamptz, NOW()))
                ON CONFLICT DO NOTHING
                """,
                {**r, "metadata_json": r.get("metadata_json") or "{}"},
            )
        for r in _sqlite_rows(sq, "edges"):
            cur.execute(
                """
                INSERT INTO edges (
                  id, tenant_id, source_entity_id, target_entity_id, relation_type,
                  source_document_id, confidence, review_status, visibility
                ) VALUES (
                  %(id)s, %(tenant_id)s, %(source_entity_id)s, %(target_entity_id)s,
                  %(relation_type)s, %(source_document_id)s, %(confidence)s,
                  %(review_status)s, %(visibility)s
                )
                ON CONFLICT DO NOTHING
                """,
                dict(r),
            )

        for r in _sqlite_rows(sq, "ingest_state"):
            cur.execute(
                """
                INSERT INTO ingest_state(key, value, updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=NOW()
                """,
                (r["key"], r["value"]),
            )

        cur.execute(
            "INSERT INTO meta(key, value) VALUES ('migrated_from_sqlite', %s) "
            "ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value",
            (sqlite_path,),
        )

    pg.commit()
    stats["hnsw"] = ensure_hnsw_index(pg)
    pg.close()
    sq.close()
    stats["ok"] = True
    return stats
