"""Repository factory: sqlite (default) or postgres search/read backend."""

from __future__ import annotations

import os
from typing import Any

from brain_platform.db.connection import init_db
from brain_platform.db.pg import connect_postgres, database_url, store_backend
from brain_platform.db.repository import BrainRepository


class HybridBrainRepo:
    """
    Write path: SQLite BrainRepository (ingest stays stable).
    Read/search path: Postgres+pgvector when BRAIN_STORE=postgres.
    After ingest, run `brain sync-pg` to refresh Postgres.
    """

    def __init__(self, sqlite_repo: BrainRepository, pg_search=None):
        self.sqlite = sqlite_repo
        self.pg = pg_search
        self.conn = sqlite_repo.conn  # ingest expects .conn

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
        pg_search = PgSearchRepository(pg_conn)
        _repo_singleton = HybridBrainRepo(sqlite_repo, pg_search)
    else:
        _repo_singleton = sqlite_repo
    return _repo_singleton


def reset_repo_singleton() -> None:
    global _repo_singleton
    _repo_singleton = None
