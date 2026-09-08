"""OpenAI Realtime WebRTC for public widget (unified /v1/realtime/calls interface)."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.operator.agent import _kb_context_from_result, build_widget_realtime_instructions
from app.operator.tools.registry import ToolResult, registry
from app.services.platform_env import get_openai_runtime

logger = logging.getLogger(__name__)

# Preload public KB slices for Realtime session instructions (guest ACL).
WIDGET_KB_SEED_QUERIES = (
    "DELNO компания продукт для кого чем занимается",
    "DELNO тарифы цены подключение услуги лимиты пакет",
    "DELNO сколько обращений диалогов сообщений звонков минут входит в тариф 2990 5990",
    "DELNO возможности каналы контакты воронка заявка",
)

_KB_CONTEXT_CACHE: dict[str, tuple[float, str]] = {}
_KB_CONTEXT_TTL_SEC = 300.0
_REALTIME_CONNECT_ATTEMPTS = 3

WIDGET_REALTIME_KB_TOOL: dict[str, Any] = {
    "type": "function",
    "name": "get_knowledge",
    "description": (
        "Поиск в базе знаний DELNO по вопросу клиента: тарифы, продукт, компания, подключение, каналы. "
        "Вызывай перед каждым ответом на фактический вопрос."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Вопрос или тема на русском"},
        },
        "required": ["query"],
    },
}


def sanitize_realtime_answer_sdp(raw: str) -> str:
    """Normalize OpenAI SDP answer for browser RTCPeerConnection.

    OpenAI appends non-standard `` ufrag <token>`` to ``a=candidate`` lines.
    Chrome's SDP parser rejects those lines; strip the suffix and use CRLF.
    """
    if not raw or not raw.strip():
        return ""
    lines: list[str] = []
    for line in raw.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if not line:
            continue
        if line.startswith("a=candidate:") and " ufrag " in line:
            line = line.split(" ufrag ", 1)[0]
        lines.append(line)
    return "\r\n".join(lines) + "\r\n"


def load_widget_kb_context(db: Session, ctx: TenantContext) -> str:
    """Cached KB preload — optional hint for Realtime; tool get_knowledge is authoritative."""
    cache_key = ctx.tenant_slug or "default"
    now = time.monotonic()
    cached = _KB_CONTEXT_CACHE.get(cache_key)
    if cached and now - cached[0] < _KB_CONTEXT_TTL_SEC:
        return cached[1]

    snippets: list[str] = []
    seen: set[str] = set()
    for query in WIDGET_KB_SEED_QUERIES:
        knowledge = registry.run(db, ctx, "get_knowledge", query=query)
        if isinstance(knowledge, ToolResult) and knowledge.ok:
            chunk = _kb_context_from_result(knowledge)
            if chunk and chunk not in seen:
                seen.add(chunk)
                snippets.append(chunk)
    result = "\n\n".join(snippets)[:4000]
    _KB_CONTEXT_CACHE[cache_key] = (now, result)
    return result


def _realtime_session_config(instructions: str) -> dict[str, Any]:
    """Full-duplex Realtime like telephony: cedar voice, barge-in, KB tool + transcription."""
    runtime = get_openai_runtime()
    return {
        "type": "realtime",
        "model": runtime["realtime_model"],
        "instructions": instructions,
        "tools": [WIDGET_REALTIME_KB_TOOL],
        "tool_choice": "auto",
        "audio": {
            "output": {"voice": runtime["realtime_voice"]},
            "input": {
                "transcription": {
                    "model": "gpt-4o-mini-transcribe",
                    "language": "ru",
                },
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.5,
                    "prefix_padding_ms": 300,
                    "silence_duration_ms": 500,
                    "create_response": True,
                    "interrupt_response": True,
                },
            },
        },
    }


def safety_identifier(visitor_id: str | None) -> str | None:
    if not visitor_id:
        return None
    digest = hashlib.sha256(visitor_id.encode("utf-8")).hexdigest()
    return digest[:32]


def exchange_widget_realtime_sdp(
    db: Session,
    ctx: TenantContext,
    *,
    sdp_offer: str,
    visitor_id: str | None = None,
) -> tuple[str | None, str | None]:
    """Return (sdp_answer, error_code). Uses OpenAI unified Realtime calls endpoint."""
    runtime = get_openai_runtime()
    api_key = runtime["api_key"]
    if not api_key:
        return None, "VOICE_NOT_CONFIGURED"

    offer = sdp_offer if sdp_offer is not None else ""
    if not offer.strip():
        return None, "SDP_REQUIRED"

    kb_context = load_widget_kb_context(db, ctx)
    instructions = build_widget_realtime_instructions(ctx, kb_context)
    session_config = _realtime_session_config(instructions)

    # OpenAI expects multipart form fields (no filenames), not file attachments.
    files = {
        "sdp": (None, offer, "application/sdp"),
        "session": (None, json.dumps(session_config), "application/json"),
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/sdp",
    }
    safety = safety_identifier(visitor_id)
    if safety:
        headers["OpenAI-Safety-Identifier"] = safety

    response: httpx.Response | None = None
    last_exc: Exception | None = None
    for attempt in range(_REALTIME_CONNECT_ATTEMPTS):
        try:
            response = httpx.post(
                "https://api.openai.com/v1/realtime/calls",
                headers=headers,
                files=files,
                timeout=45.0,
            )
            break
        except httpx.HTTPError as exc:
            last_exc = exc
            logger.warning(
                "openai_realtime_http_error attempt=%s err=%s",
                attempt + 1,
                exc.__class__.__name__,
            )
            if attempt + 1 < _REALTIME_CONNECT_ATTEMPTS:
                time.sleep(0.6 * (attempt + 1))

    if response is None:
        logger.warning("openai_realtime_http_error final: %s", last_exc.__class__.__name__ if last_exc else "unknown")
        return None, "REALTIME_CONNECTION_FAILED"

    if response.status_code in (401, 403):
        return None, "VOICE_AUTH_FAILED"
    if response.status_code == 429:
        return None, "VOICE_LIMIT_REACHED"
    if response.status_code not in (200, 201):
        logger.warning(
            "openai_realtime_failed status=%s body=%s",
            response.status_code,
            (response.text or "")[:300],
        )
        return None, "REALTIME_CONNECTION_FAILED"

    answer = sanitize_realtime_answer_sdp(response.text or "")
    if not answer.startswith("v="):
        logger.warning("openai_realtime_empty_answer status=%s", response.status_code)
        return None, "REALTIME_CONNECTION_FAILED"
    return answer, None


def search_widget_knowledge(db: Session, ctx: TenantContext, query: str) -> str:
    """KB search for Realtime get_knowledge tool (browser executes tool, server provides data)."""
    from app.adapters.knowledge import KnowledgeAdapter
    from app.core.principals import principal_for_public_channel

    q = (query or "").strip()
    if not q:
        return ""
    adapter = KnowledgeAdapter()
    data = adapter.search(
        q,
        tenant_slug=ctx.tenant_slug,
        principal_id=principal_for_public_channel("widget"),
    )
    if not data.get("ok", True):
        return ""
    return _kb_context_from_result(ToolResult(ok=True, data=data))
