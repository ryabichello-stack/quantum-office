"""OpenAI Realtime WebRTC for public widget (unified /v1/realtime/calls interface)."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.tenant import TenantContext
from app.operator.agent import _kb_context_from_result, build_widget_realtime_instructions
from app.operator.tools.registry import ToolResult, registry
from app.services.platform_env import get_openai_runtime

WIDGET_KB_SEED_QUERY = "DELNO тарифы подключение услуги возможности"


def load_widget_kb_context(db: Session, ctx: TenantContext) -> str:
    knowledge = registry.run(db, ctx, "get_knowledge", query=WIDGET_KB_SEED_QUERY)
    if isinstance(knowledge, ToolResult) and knowledge.ok:
        return _kb_context_from_result(knowledge)
    return ""


def _realtime_session_config(instructions: str) -> dict[str, Any]:
    runtime = get_openai_runtime()
    return {
        "type": "realtime",
        "model": runtime["realtime_model"],
        "instructions": instructions,
        "audio": {
            "input": {
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.5,
                    "prefix_padding_ms": 300,
                    "silence_duration_ms": 500,
                    "create_response": True,
                    "interrupt_response": True,
                },
            },
            "output": {"voice": runtime["realtime_voice"]},
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

    offer = (sdp_offer or "").strip()
    if not offer:
        return None, "SDP_REQUIRED"

    kb_context = load_widget_kb_context(db, ctx)
    instructions = build_widget_realtime_instructions(ctx, kb_context)
    session_config = _realtime_session_config(instructions)

    headers = {"Authorization": f"Bearer {api_key}"}
    safety = safety_identifier(visitor_id)
    if safety:
        headers["OpenAI-Safety-Identifier"] = safety

    files = {
        "sdp": (None, offer, "application/sdp"),
        "session": (None, json.dumps(session_config), "application/json"),
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                "https://api.openai.com/v1/realtime/calls",
                headers=headers,
                files=files,
            )
    except httpx.HTTPError:
        return None, "REALTIME_CONNECTION_FAILED"

    if response.status_code in (401, 403):
        return None, "VOICE_AUTH_FAILED"
    if response.status_code == 429:
        return None, "VOICE_LIMIT_REACHED"
    if response.status_code not in (200, 201):
        return None, "REALTIME_CONNECTION_FAILED"

    answer = (response.text or "").strip()
    if not answer:
        return None, "REALTIME_CONNECTION_FAILED"
    return answer, None
