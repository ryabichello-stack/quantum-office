"""Knowledge / Second Brain client for outreach citations (best-effort)."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger("ava-outreach.knowledge_client")

DEFAULT_BASE = "http://127.0.0.1:8017"


def knowledge_base_url() -> str:
    return (
        (os.getenv("KNOWLEDGE_BASE") or os.getenv("AVA_KNOWLEDGE_BASE") or DEFAULT_BASE)
        .strip()
        .rstrip("/")
    )


def fetch_reply_citations(
    *,
    query: str,
    limit: int = 3,
    timeout: float = 2.5,
) -> list[dict[str, Any]]:
    """Pull short facts + citations from ava-knowledge (brain or legacy)."""
    q = (query or "").strip()
    if not q:
        return []
    base = knowledge_base_url()
    headers: dict[str, str] = {}
    token = (os.getenv("KNOWLEDGE_WEBHOOK_TOKEN") or os.getenv("AVA_WEBHOOK_TOKEN") or "").strip()
    if token:
        headers["X-Webhook-Token"] = token

    # Prefer Second Brain search when available
    try:
        with httpx.Client(timeout=timeout) as client:
            br = client.post(
                f"{base}/api/brain/search",
                json={"query": q, "mode": "hybrid", "limit": limit},
                headers=headers,
            )
            if br.status_code == 200:
                data = br.json()
                cites = data.get("citations") or []
                if cites:
                    out = []
                    for c in cites[:limit]:
                        out.append(
                            {
                                "source": "second_brain",
                                "ref": c.get("document_id")
                                or c.get("chunk_id")
                                or c.get("path")
                                or c.get("title")
                                or "brain",
                                "note": (c.get("snippet") or c.get("text") or c.get("title") or "")[
                                    :240
                                ],
                                "approval_required": True,
                            }
                        )
                    if out:
                        return out
                # some brain responses put matches without citations key
                matches = data.get("matches") or data.get("results") or []
                if matches:
                    out = []
                    for m in matches[:limit]:
                        out.append(
                            {
                                "source": "second_brain",
                                "ref": m.get("document_id")
                                or m.get("id")
                                or m.get("title")
                                or "brain",
                                "note": (m.get("text") or m.get("snippet") or "")[:240],
                                "approval_required": True,
                            }
                        )
                    if out:
                        return out
    except Exception:  # noqa: BLE001
        logger.debug("brain search unavailable", exc_info=True)

    try:
        with httpx.Client(timeout=timeout) as client:
            kr = client.post(
                f"{base}/api/knowledge/query",
                json={"topic": q, "limit": limit, "max_chars": 600},
                headers=headers,
            )
            if kr.status_code != 200:
                return []
            data = kr.json()
            cites = data.get("citations") or []
            if cites:
                return [
                    {
                        "source": data.get("source") or "knowledge",
                        "ref": c.get("id") or c.get("title") or c.get("path") or "knowledge",
                        "note": (c.get("snippet") or c.get("text") or "")[:240],
                        "approval_required": True,
                    }
                    for c in cites[:limit]
                ]
            text = (data.get("text") or "").strip()
            if text:
                return [
                    {
                        "source": data.get("source") or "knowledge",
                        "ref": data.get("topic_id") or data.get("topic") or "knowledge",
                        "note": text[:240],
                        "approval_required": True,
                    }
                ]
    except Exception:  # noqa: BLE001
        logger.debug("knowledge query unavailable", exc_info=True)
    return []


def queue_flywheel_document(
    *,
    title: str,
    body: str,
    tags: list[str] | None = None,
    source_id: str = "",
    timeout: float = 3.0,
) -> dict[str, Any]:
    """Write news markdown to brain inbox for later ingest (best-effort)."""
    from datetime import datetime, timezone
    from pathlib import Path

    from core.paths import DATA_DIR

    inbox = Path(DATA_DIR) / "flywheel" / "brain_inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in (title or "news")[:40])
    fname = f"{now}-{source_id[:8] if source_id else 'manual'}-{safe}.md"
    path = inbox / fname
    tag_line = ", ".join(tags or ["flywheel", "news"])
    md = (
        f"---\n"
        f"title: {title}\n"
        f"tags: [{tag_line}]\n"
        f"source: content_flywheel\n"
        f"source_id: {source_id}\n"
        f"zone: office\n"
        f"---\n\n"
        f"# {title}\n\n"
        f"{body.strip()}\n"
    )
    path.write_text(md, encoding="utf-8")
    result: dict[str, Any] = {
        "ok": True,
        "status": "file_written",
        "path": str(path),
        "note": "Markdown в brain_inbox; ingest files через ava-knowledge",
    }
    base = knowledge_base_url()
    headers: dict[str, str] = {}
    token = (os.getenv("KNOWLEDGE_WEBHOOK_TOKEN") or os.getenv("AVA_WEBHOOK_TOKEN") or "").strip()
    if token:
        headers["X-Webhook-Token"] = token
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.post(
                f"{base}/api/brain/ingest/run",
                json={"tenant_id": "quantum-labs", "sources": ["files"], "file_limit": 5},
                headers=headers,
            )
            if r.status_code == 200:
                result["status"] = "ingest_triggered"
                result["ingest"] = r.json()
    except Exception as exc:  # noqa: BLE001
        logger.debug("flywheel kb ingest trigger failed: %s", exc)
    return result
