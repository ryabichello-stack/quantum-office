"""
ava-knowledge — shared Quantum Labs Knowledge base for voice AVA + text secretary.

API:
  GET  /health
  GET  /api/knowledge/topics
  POST /api/knowledge/query   {topic?, topic_id?, limit?, max_chars?}
  POST /api/knowledge/get     {id}  — one section by id/title slug
  POST /api/knowledge/reload  — reread markdown + index (webhook optional)

Second Brain (additive, does not replace legacy query):
  /api/brain/*  — search, contacts, threads, ingest (ACL principals)
"""

from __future__ import annotations

import logging
import os
from typing import Optional

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
# legacy (default) | dual_compare — never switches voice text to brain without approval
KNOWLEDGE_READ_MODE = (os.getenv("KNOWLEDGE_READ_MODE") or "legacy").strip().lower()

app = FastAPI(title="Quantum Labs Knowledge", version="0.3.0")

if BRAIN_ENABLED:
    try:
        from brain_platform.api.router import router as brain_router

        app.include_router(brain_router)
        logger.info("Second Brain API mounted at /api/brain/*")
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


@app.get("/health")
def health():
    st = store.status()
    out = {
        "ok": True,
        "service": SERVICE_NAME,
        "brain_enabled": BRAIN_ENABLED,
        "knowledge_read_mode": KNOWLEDGE_READ_MODE,
        **st,
    }
    return out


@app.get("/api/knowledge/topics")
def knowledge_topics(x_webhook_token: Optional[str] = Header(None)):
    _check_token(x_webhook_token)
    topics = store.list_topics()
    return {"ok": True, "count": len(topics), "topics": topics}


def _brain_compare_payload(topic: str, *, limit: int, max_chars: int) -> dict:
    """Run brain search as voice-office (assistant-safe). Never used as voice primary text."""
    try:
        from brain_platform.db.factory import get_brain_repo
        from brain_platform.search.engine import BrainSearch
        from brain_platform.security.acl import Principal

        principal = Principal(
            principal_id="service:voice-office",
            tenant_id=os.getenv("BRAIN_TENANT_ID", "quantum-labs"),
        )
        result = BrainSearch(get_brain_repo()).retrieve(
            principal,
            topic,
            limit=limit,
            max_chars=max_chars,
            mode=os.getenv("BRAIN_SEARCH_MODE", "hybrid"),
            purpose="voice-dual-compare",
        )
        return {
            "ok": bool(result.get("ok")),
            "chars": result.get("chars") or 0,
            "citations": result.get("citations") or [],
            "matches": [
                {
                    "title": m.get("title"),
                    "type": m.get("type"),
                    "citation": m.get("citation"),
                    "score": m.get("score"),
                }
                for m in (result.get("matches") or [])[:8]
            ],
            "text_preview": (result.get("text") or "")[:500],
            "principal_id": "service:voice-office",
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("brain compare failed")
        return {"ok": False, "error": str(exc)}


@app.post("/api/knowledge/query")
def knowledge_query(
    req: KnowledgeQueryRequest,
    x_webhook_token: Optional[str] = Header(None),
):
    """Compatible with voice AVA + text-bot: returns ok/topic/text/chars (+ matches).

    Voice always gets legacy `text`. When KNOWLEDGE_READ_MODE=dual_compare, attaches
    brain_compare metadata for parity checks — does NOT replace legacy text.
    """
    _check_token(x_webhook_token)
    topic = (req.topic or req.q or "").strip()
    out = store.search(
        topic=topic,
        topic_id=req.topic_id.strip(),
        limit=req.limit,
        max_chars=req.max_chars,
    )
    out["knowledge_read_mode"] = KNOWLEDGE_READ_MODE
    if BRAIN_ENABLED and KNOWLEDGE_READ_MODE == "dual_compare" and topic:
        out["brain_compare"] = _brain_compare_payload(
            topic, limit=req.limit, max_chars=min(req.max_chars, 4000)
        )
    return out


@app.post("/api/knowledge/compare")
def knowledge_compare(
    req: KnowledgeQueryRequest,
    x_webhook_token: Optional[str] = Header(None),
):
    """Explicit legacy vs brain compare (opt-in). Voice must not call this as primary."""
    _check_token(x_webhook_token)
    topic = (req.topic or req.q or "").strip()
    legacy = store.search(
        topic=topic,
        topic_id=req.topic_id.strip(),
        limit=req.limit,
        max_chars=req.max_chars,
    )
    brain = (
        _brain_compare_payload(topic, limit=req.limit, max_chars=req.max_chars)
        if BRAIN_ENABLED and topic
        else {"ok": False, "error": "brain_disabled_or_empty_query"}
    )
    return {
        "ok": True,
        "query": topic,
        "legacy": legacy,
        "brain": brain,
        "note": "legacy.text remains the voice SoT until A3 approval",
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
