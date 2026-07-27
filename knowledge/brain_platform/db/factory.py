"""Repository factory: sqlite (default) or postgres search/read backend + dual-write."""

from __future__ import annotations

import logging
import os
from typing import Any

from brain_platform.db.connection import init_db
from brain_platform.db.pg import connect_postgres, database_url, store_backend
from brain_platform.db.pg_write import (
    dual_write_enabled,
    sync_contact,
    sync_documents,
    sync_email,
)
from brain_platform.db.repository import BrainRepository

logger = logging.getLogger("brain.factory")


class HybridBrainRepo:
    """
    Write path: SQLite BrainRepository (authoritative).
    Optional dual-write: touched rows copied to Postgres after successful SQLite commit.
    Read/search path: Postgres+pgvector when BRAIN_STORE=postgres.
    """

    def __init__(self, sqlite_repo: BrainRepository, pg_search=None):
        self.sqlite = sqlite_repo
        self.pg = pg_search
        self.conn = sqlite_repo.conn  # ingest expects .conn
        self.last_dual_write: dict[str, Any] | None = None

    def upsert_document(self, *args, **kwargs):
        result = self.sqlite.upsert_document(*args, **kwargs)
        doc_id = result.get("id") or kwargs.get("doc_id")
        if doc_id and dual_write_enabled():
            self.last_dual_write = sync_documents(self.conn, [doc_id])
            if result.get("unchanged") is False or not result.get("unchanged"):
                pass
            if not self.last_dual_write.get("ok"):
                logger.warning("dual-write document failed: %s", self.last_dual_write)
            result = {**result, "dual_write": self.last_dual_write}
        return result

    def upsert_email_message(self, *args, **kwargs):
        result = self.sqlite.upsert_email_message(*args, **kwargs)
        email_id = result.get("id")
        if email_id and dual_write_enabled() and result.get("created"):
            self.last_dual_write = sync_email(self.conn, email_id)
            if not self.last_dual_write.get("ok"):
                logger.warning("dual-write email failed: %s", self.last_dual_write)
            result = {**result, "dual_write": self.last_dual_write}
        return result

    def upsert_contact(self, *args, **kwargs):
        contact_id = self.sqlite.upsert_contact(*args, **kwargs)
        if contact_id and dual_write_enabled():
            self.last_dual_write = sync_contact(self.conn, contact_id)
            if not self.last_dual_write.get("ok"):
                logger.warning("dual-write contact failed: %s", self.last_dual_write)
        return contact_id

    def upsert_file_asset(self, *args, **kwargs):
        result = self.sqlite.upsert_file_asset(*args, **kwargs)
        doc_id = None
        if isinstance(result, dict):
            idx = result.get("index") if isinstance(result.get("index"), dict) else {}
            doc_id = idx.get("id") or (
                f"doc-{result['id']}" if result.get("id") else None
            )
        if doc_id and dual_write_enabled() and not result.get("unchanged"):
            self.last_dual_write = sync_documents(self.conn, [doc_id])
            if isinstance(result, dict):
                result = {**result, "dual_write": self.last_dual_write}
        return result

    def __getattr__(self, name: str) -> Any:
        # Prefer PG for search/directory/stats when available
        if self.pg is not None and name in {
            "search_chunks",
            "search_semantic",
            "find_contacts",
            "list_threads",
            "stats",
            "write_audit",
        }:
            return getattr(self.pg, name)
        return getattr(self.sqlite, name)


_repo_singleton = None


def get_brain_repo():
    global _repo_singleton
    if _repo_singleton is not None:
        return _repo_singleton

    sqlite_repo = BrainRepository(init_db())
    backend = store_backend()
    if backend == "postgres" and database_url():
        from brain_platform.db.pg_search import PgSearchRepository

        pg_conn = connect_postgres()
        # Read path is a long-lived singleton; autocommit avoids one failed
        # statement poisoning every subsequent request (InFailedSqlTransaction).
        try:
            pg_conn.autocommit = True
        except Exception:
            logger.warning("could not enable autocommit on brain postgres conn")
        pg_search = PgSearchRepository(pg_conn)
        _repo_singleton = HybridBrainRepo(sqlite_repo, pg_search)
        if dual_write_enabled():
            logger.info("Second Brain dual-write SQLite→Postgres enabled")
    else:
        _repo_singleton = sqlite_repo
    return _repo_singleton


def reset_repo_singleton() -> None:
    global _repo_singleton
    _repo_singleton = None
