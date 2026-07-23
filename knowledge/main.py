"""
ava-knowledge — shared Quantum Labs Knowledge base for voice AVA + text secretary.

API:
  GET  /health
  GET  /api/knowledge/topics
  POST /api/knowledge/query   {topic?, topic_id?, limit?, max_chars?}
  POST /api/knowledge/get     {id}  — one section by id/title slug
  POST /api/knowledge/reload  — reread markdown + index (webhook optional)
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

app = FastAPI(title="Quantum Labs Knowledge", version="0.1.0")


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
    return {"ok": True, "service": SERVICE_NAME, **st}


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
    """Compatible with voice AVA + text-bot: returns ok/topic/text/chars (+ matches)."""
    _check_token(x_webhook_token)
    topic = (req.topic or req.q or "").strip()
    return store.search(
        topic=topic,
        topic_id=req.topic_id.strip(),
        limit=req.limit,
        max_chars=req.max_chars,
    )


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
