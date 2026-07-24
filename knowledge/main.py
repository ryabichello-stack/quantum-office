"""
ava-knowledge — shared Quantum Labs Knowledge base for voice AVA + text secretary.

API:
  GET  /health
  GET  /api/knowledge/topics
  POST /api/knowledge/query   {topic?, topic_id?, limit?, max_chars?}
  POST /api/knowledge/get     {id}  — one section by id/title slug
  POST /api/knowledge/reload  — reread markdown + index (webhook optional)
  POST /api/knowledge/compare — legacy vs brain (diagnostics)

Second Brain (additive):
  /api/brain/*  — search, contacts, threads, ingest (ACL principals)

KNOWLEDGE_READ_MODE:
  legacy       — voice text from markdown (default rollback)
  dual_compare — legacy text + brain_compare metadata
  brain        — Second Brain faq-safe primary (voice-office ACL), legacy fallback
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

load_dotenv()

from store import store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("ava-knowledge")

WEBHOOK_TOKEN = os.getenv("WEBHOOK_TOKEN", "").strip()
SERVICE_NAME = "ava-knowledge"
BRAIN_ENABLED = os.getenv("BRAIN_ENABLED", "true").lower() not in ("0", "false", "no", "off")
# legacy | dual_compare | brain
KNOWLEDGE_READ_MODE = (os.getenv("KNOWLEDGE_READ_MODE") or "legacy").strip().lower()
BRAIN_VOICE_SEARCH_MODE = (
    os.getenv("BRAIN_VOICE_SEARCH_MODE") or os.getenv("BRAIN_SEARCH_MODE") or "hybrid"
).strip().lower()
BRAIN_VOICE_PRINCIPAL = (
    os.getenv("BRAIN_VOICE_PRINCIPAL") or "service:voice-office"
).strip()

app = FastAPI(title="Quantum Labs Knowledge", version="0.4.0")

if BRAIN_ENABLED:
    try:
        from brain_platform.api.router import router as brain_router

        app.include_router(brain_router)
        logger.info(
            "Second Brain API mounted; knowledge_read_mode=%s", KNOWLEDGE_READ_MODE
        )
    except Exception:  # noqa: BLE001
        logger.exception("Second Brain router failed to load; legacy knowledge still available")


def _check_token(x_webhook_token: Optional[str] = None) -> None:
    if not WEBHOOK_TOKEN:
        return
    if (x_webhook_token or "").strip() != WEBHOOK_TOKEN:
        raise HTTPException(status_code=401, detail="unauthorized")


class KnowledgeQueryRequest(BaseModel):
    topic: str = Field(default="", description="Free-text topic / question in Russian")
    topic_id: str = Field(default="", description="Catalog id from /api/knowledge/topics")
    q: str = Field(default="", description="Alias of topic")
    limit: int = Field(default=4, ge=1, le=8)
    max_chars: int = Field(default=4500, ge=500, le=12000)


class KnowledgeGetRequest(BaseModel):
    id: str = Field(..., min_length=1, max_length=200)


def _resolve_query(req: KnowledgeQueryRequest) -> tuple[str, str]:
    topic = (req.topic or req.q or "").strip()
    tid = (req.topic_id or "").strip()
    if topic:
        return topic, tid
    if tid:
        for t in store.list_topics():
            if t.get("id") == tid:
                return str(t.get("title") or tid), tid
        return tid, tid
    return "", tid


def _legacy_search(req: KnowledgeQueryRequest) -> dict[str, Any]:
    topic, tid = _resolve_query(req)
    return store.search(
        topic=topic,
        topic_id=tid,
        limit=req.limit,
        max_chars=req.max_chars,
    )


def _brain_voice_retrieve(topic: str, *, limit: int, max_chars: int) -> dict[str, Any]:
    """Faq-safe Second Brain retrieve for voice (assistant-safe principal)."""
    try:
        from brain_platform.db.factory import get_brain_repo
        from brain_platform.search.engine import BrainSearch
        from brain_platform.security.acl import Principal

        principal = Principal(
            principal_id=BRAIN_VOICE_PRINCIPAL,
            tenant_id=os.getenv("BRAIN_TENANT_ID", "quantum-labs"),
        )
        result = BrainSearch(get_brain_repo()).retrieve(
            principal,
            topic,
            limit=limit,
            max_chars=max_chars,
            mode=BRAIN_VOICE_SEARCH_MODE,
            purpose="voice-knowledge",
        )
        # Strip graph footer noise for voice brevity if present
        text = result.get("text") or ""
        if "## Связанные сущности [graph]" in text:
            text = text.split("## Связанные сущности [graph]", 1)[0].rstrip()
        matches = []
        for m in result.get("matches") or []:
            # Defense: never surface mail/restricted types to voice path even if ACL slips
            if (m.get("type") or "") in ("email", "mail", "thread"):
                continue
            matches.append(
                {
                    "title": m.get("title"),
                    "type": m.get("type"),
                    "citation": m.get("citation"),
                    "score": m.get("score"),
                    "id": m.get("document_id"),
                }
            )
        return {
            "ok": bool(result.get("ok")) and not result.get("denied"),
            "text": text,
            "chars": len(text),
            "citations": result.get("citations") or [],
            "matches": matches,
            "principal_id": BRAIN_VOICE_PRINCIPAL,
            "search_mode": result.get("search_mode"),
            "denied": bool(result.get("denied")),
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("brain voice retrieve failed")
        return {"ok": False, "error": str(exc), "text": "", "chars": 0, "matches": []}


@app.get("/health")
def health():
    st = store.status()
    return {
        "ok": True,
        "service": SERVICE_NAME,
        "brain_enabled": BRAIN_ENABLED,
        "knowledge_read_mode": KNOWLEDGE_READ_MODE,
        "brain_voice_principal": BRAIN_VOICE_PRINCIPAL,
        **st,
    }


@app.get("/api/knowledge/topics")
def knowledge_topics(x_webhook_token: Optional[str] = Header(None)):
    _check_token(x_webhook_token)
    topics = store.list_topics()
    return {"ok": True, "count": len(topics), "topics": topics}


@app.post("/api/knowledge/query")
def knowledge_query(
    req: KnowledgeQueryRequest,
    x_webhook_token: Optional[str] = Header(None),
):
    """Voice/text compatible knowledge query.

    Modes:
      legacy — markdown SoT
      dual_compare — legacy text + brain_compare
      brain — Second Brain primary (faq-safe), legacy fallback if empty/error
    Rollback: set KNOWLEDGE_READ_MODE=legacy and restart ava-knowledge.
    """
    _check_token(x_webhook_token)
    topic, tid = _resolve_query(req)
    legacy = store.search(
        topic=topic,
        topic_id=tid,
        limit=req.limit,
        max_chars=req.max_chars,
    )
    mode = KNOWLEDGE_READ_MODE

    if mode == "brain" and BRAIN_ENABLED and topic:
        brain = _brain_voice_retrieve(
            topic, limit=req.limit, max_chars=req.max_chars
        )
        if brain.get("ok") and (brain.get("chars") or 0) > 0:
            return {
                "ok": True,
                "topic": topic or tid,
                "topic_id": tid or legacy.get("topic_id"),
                "text": brain["text"],
                "chars": brain["chars"],
                "matches": brain.get("matches") or [],
                "citations": brain.get("citations") or [],
                "source": "second_brain",
                "source_of_truth": "second_brain",
                "knowledge_read_mode": "brain",
                "via": "ava-knowledge-brain",
            }
        # Fallback keeps voice answering
        out = dict(legacy)
        out["knowledge_read_mode"] = "brain"
        out["source"] = out.get("source") or "legacy_fallback"
        out["legacy_fallback"] = True
        out["brain_error"] = brain.get("error") or "empty_or_denied"
        out["via"] = "ava-knowledge-legacy-fallback"
        return out

    out = dict(legacy)
    out["knowledge_read_mode"] = mode
    if BRAIN_ENABLED and mode == "dual_compare" and topic:
        out["brain_compare"] = _brain_voice_retrieve(
            topic, limit=req.limit, max_chars=min(req.max_chars, 4000)
        )
    return out


@app.post("/api/knowledge/compare")
def knowledge_compare(
    req: KnowledgeQueryRequest,
    x_webhook_token: Optional[str] = Header(None),
):
    """Explicit legacy vs brain compare (diagnostics)."""
    _check_token(x_webhook_token)
    topic, tid = _resolve_query(req)
    legacy = store.search(
        topic=topic,
        topic_id=tid,
        limit=req.limit,
        max_chars=req.max_chars,
    )
    brain = (
        _brain_voice_retrieve(topic, limit=req.limit, max_chars=req.max_chars)
        if BRAIN_ENABLED and topic
        else {"ok": False, "error": "brain_disabled_or_empty_query"}
    )
    return {
        "ok": True,
        "query": topic,
        "legacy": legacy,
        "brain": brain,
        "active_mode": KNOWLEDGE_READ_MODE,
        "note": "Set KNOWLEDGE_READ_MODE=legacy to rollback voice to markdown",
    }


@app.post("/api/knowledge/get")
def knowledge_get(
    req: KnowledgeGetRequest,
    x_webhook_token: Optional[str] = Header(None),
):
    _check_token(x_webhook_token)
    sec = store.get_section(req.id)
    if not sec:
        return {"ok": False, "error": "not_found", "id": req.id, "text": ""}
    return {
        "ok": True,
        "id": sec.id,
        "title": sec.title,
        "source": sec.source,
        "text": sec.text,
        "chars": len(sec.text),
    }


@app.post("/api/knowledge/reload")
def knowledge_reload(x_webhook_token: Optional[str] = Header(None)):
    _check_token(x_webhook_token)
    store.reload()
    return {"ok": True, **store.status()}
