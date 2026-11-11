"""Embedding providers for Second Brain (OpenAI + local fallback)."""

from __future__ import annotations

import hashlib
import logging
import math
import os
import re
from abc import ABC, abstractmethod
from typing import Sequence

logger = logging.getLogger("brain.embeddings")

DEFAULT_DIM = int(os.getenv("BRAIN_EMBED_DIM", "1536") or "1536")
DEFAULT_MODEL = os.getenv("BRAIN_EMBED_MODEL", "text-embedding-3-small")


class Embedder(ABC):
    model: str
    dim: int

    @abstractmethod
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        raise NotImplementedError


class LocalHashEmbedder(Embedder):
    """Deterministic bag-of-tokens hash embedder for offline/tests and secret docs."""

    def __init__(self, dim: int = 384):
        self.model = "local-hash-v1"
        self.dim = dim

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            vec = [0.0] * self.dim
            tokens = re.findall(r"[A-Za-zА-Яа-яЁё0-9]{2,}", (text or "").lower())
            if not tokens:
                tokens = ["empty"]
            for tok in tokens:
                h = hashlib.sha256(tok.encode("utf-8")).digest()
                idx = int.from_bytes(h[:4], "little") % self.dim
                sign = 1.0 if h[4] % 2 == 0 else -1.0
                weight = 1.0 + (h[5] / 255.0)
                vec[idx] += sign * weight
            # L2 normalize
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            out.append([v / norm for v in vec])
        return out


class OpenAIEmbedder(Embedder):
    def __init__(self, api_key: str | None = None, model: str | None = None, dim: int | None = None):
        self.api_key = (api_key or os.getenv("OPENAI_API_KEY") or "").strip()
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY required for OpenAIEmbedder")
        self.model = model or DEFAULT_MODEL
        self.dim = dim or DEFAULT_DIM
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(api_key=self.api_key)
        return self._client

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        # OpenAI limit ~2048 inputs; batch
        client = self._get_client()
        vectors: list[list[float]] = []
        batch_size = 64
        for i in range(0, len(texts), batch_size):
            batch = [t[:8000] if t else " " for t in texts[i : i + batch_size]]
            resp = client.embeddings.create(model=self.model, input=batch)
            # ensure order by index
            ordered = sorted(resp.data, key=lambda x: x.index)
            for item in ordered:
                vectors.append(list(item.embedding))
        return vectors


def get_embedder(*, force_local: bool = False) -> Embedder:
    provider = (os.getenv("BRAIN_EMBED_PROVIDER") or "auto").strip().lower()
    if force_local or provider == "local":
        return LocalHashEmbedder(dim=int(os.getenv("BRAIN_EMBED_LOCAL_DIM", "384") or "384"))
    if provider in ("openai", "auto"):
        key = (os.getenv("OPENAI_API_KEY") or "").strip()
        if key:
            try:
                return OpenAIEmbedder(api_key=key)
            except Exception as exc:
                logger.warning("openai embedder unavailable (%s), falling back to local", exc)
        elif provider == "openai":
            raise RuntimeError("BRAIN_EMBED_PROVIDER=openai but OPENAI_API_KEY missing")
    return LocalHashEmbedder(dim=int(os.getenv("BRAIN_EMBED_LOCAL_DIM", "384") or "384"))


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return -1.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0 or nb <= 0:
        return -1.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def should_external_embed(
    *,
    visibility: str,
    classification: dict | None,
    ai_processing: dict | None,
) -> bool:
    """Decide whether cloud embeddings are allowed for this document."""
    ai = ai_processing or {}
    if ai.get("external_embedding_allowed") is True:
        return True
    if ai.get("local_processing_required") is True and ai.get("external_embedding_allowed") is False:
        # explicit local-only
        if "external_embedding_allowed" in ai:
            return False
    level = str((classification or {}).get("level") or "internal").lower()
    if level in ("secret",) or visibility in ("secret",):
        return False
    if level == "confidential" or visibility == "restricted":
        return os.getenv("BRAIN_EMBED_RESTRICTED_EXTERNAL", "true").lower() not in (
            "0",
            "false",
            "no",
            "off",
        )
    # FAQ / company / public / internal — allow external by default
    return True
