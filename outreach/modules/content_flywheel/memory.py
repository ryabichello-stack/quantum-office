"""Content memory — deduplication of published angles."""

from __future__ import annotations

import hashlib
import re
from typing import Any


def normalize_text(text: str) -> str:
    t = (text or "").lower()
    t = re.sub(r"https?://\S+", "", t)
    t = re.sub(r"[^\w\s]", " ", t, flags=re.UNICODE)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def content_hash(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def angle_fingerprint(title: str, body: str) -> str:
    base = normalize_text(f"{title}\n{body}")[:400]
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:32]


def word_set(text: str) -> set[str]:
    words = normalize_text(text).split()
    return {w for w in words if len(w) > 3}


def jaccard_similarity(a: str, b: str) -> float:
    sa, sb = word_set(a), word_set(b)
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    union = len(sa | sb)
    return inter / union if union else 0.0


def find_similar(
    text: str,
    memory_rows: list[dict[str, Any]],
    *,
    threshold: float = 0.55,
) -> list[dict[str, Any]]:
    """Return memory hits with similarity >= threshold."""
    hits: list[dict[str, Any]] = []
    for row in memory_rows:
        ref = f"{row.get('topic') or ''}\n{row.get('summary') or ''}"
        sim = jaccard_similarity(text, ref)
        if sim >= threshold:
            hits.append({**row, "similarity": round(sim, 3)})
    hits.sort(key=lambda x: x.get("similarity") or 0, reverse=True)
    return hits
