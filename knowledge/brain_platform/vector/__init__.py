"""Vector store abstraction — SQLite JSON backend now; pgvector-ready interface."""

from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod
from typing import Any, Iterable, Sequence

from brain_platform.embeddings import cosine_similarity, get_embedder

logger = logging.getLogger("brain.vector")


class VectorStore(ABC):
    @abstractmethod
    def upsert(self, chunk_id: str, embedding: Sequence[float], *, model: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def search(
        self,
        query_vec: Sequence[float],
        *,
        candidate_rows: list[dict[str, Any]],
        limit: int = 8,
    ) -> list[dict[str, Any]]:
        """Rank ACL-prefiltered candidate rows by cosine similarity."""
        raise NotImplementedError


class SqliteJsonVectorStore(VectorStore):
    """Stores vectors in chunks.embedding_json; ranks in-process (fine for ~10k chunks)."""

    def __init__(self, conn):
        self.conn = conn

    def upsert(self, chunk_id: str, embedding: Sequence[float], *, model: str) -> None:
        payload = json.dumps(list(embedding), separators=(",", ":"))
        self.conn.execute(
            "UPDATE chunks SET embedding_json = ? WHERE chunk_id = ?",
            (payload, chunk_id),
        )
        # track model in meta
        self.conn.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            ("embedding_model", model),
        )

    def search(
        self,
        query_vec: Sequence[float],
        *,
        candidate_rows: list[dict[str, Any]],
        limit: int = 8,
    ) -> list[dict[str, Any]]:
        scored: list[tuple[float, dict[str, Any]]] = []
        for row in candidate_rows:
            raw = row.get("embedding_json") or "[]"
            try:
                vec = json.loads(raw) if isinstance(raw, str) else list(raw)
            except json.JSONDecodeError:
                continue
            if not vec:
                continue
            sim = cosine_similarity(query_vec, vec)
            if sim < 0:
                continue
            item = dict(row)
            item["score"] = float(sim)
            item["vector_score"] = float(sim)
            scored.append((sim, item))
        scored.sort(key=lambda x: -x[0])
        return [r for _, r in scored[:limit]]


def get_vector_store(conn) -> VectorStore:
    backend = (os.getenv("BRAIN_VECTOR_BACKEND") or "sqlite_json").strip().lower()
    if backend in ("sqlite", "sqlite_json", "json"):
        return SqliteJsonVectorStore(conn)
    if backend in ("pgvector", "postgres"):
        # Reserved: requires Postgres+pgvector provisioned
        raise RuntimeError(
            "BRAIN_VECTOR_BACKEND=pgvector not provisioned yet; use sqlite_json"
        )
    return SqliteJsonVectorStore(conn)


def rrf_fuse(
    ranked_lists: list[list[dict[str, Any]]],
    *,
    k: int = 60,
    limit: int = 8,
    id_key: str = "chunk_id",
) -> list[dict[str, Any]]:
    """Reciprocal Rank Fusion over multiple ranked result lists."""
    scores: dict[str, float] = {}
    payload: dict[str, dict[str, Any]] = {}
    for results in ranked_lists:
        for rank, row in enumerate(results):
            cid = str(row.get(id_key) or "")
            if not cid:
                continue
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
            if cid not in payload:
                payload[cid] = dict(row)
            else:
                # keep best vector/keyword annotations
                payload[cid].update({kk: vv for kk, vv in row.items() if kk not in payload[cid] or kk == "score"})
            payload[cid]["rrf_score"] = scores[cid]
    ordered = sorted(scores.items(), key=lambda x: -x[1])
    out: list[dict[str, Any]] = []
    for cid, sc in ordered[:limit]:
        item = payload[cid]
        item["score"] = sc
        out.append(item)
    return out


def embed_texts(texts: Sequence[str], *, force_local: bool = False) -> tuple[list[list[float]], str]:
    emb = get_embedder(force_local=force_local)
    return emb.embed(list(texts)), emb.model
