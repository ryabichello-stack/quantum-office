from uuid import UUID

from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.auth import get_tenant_context_auth
from app.core.tenant import TenantContext
from app.models.conversation import Conversation, Message
from app.operator.agent import execute_confirmed_tool, run_operator_turn
from app.services.conversation_present import (
    filter_conversation_items,
    get_conversation_detail,
    list_conversation_items,
)
from app.services.tts import synthesize_speech

router = APIRouter(prefix="/operator", tags=["operator"])


class OperatorChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    channel: str = Field(default="web", max_length=32)
    conversation_id: UUID | None = None
    modality: str = Field(default="text", description="text | voice (post-STT)")


class OperatorConfirmRequest(BaseModel):
    tool_name: str
    params: dict = Field(default_factory=dict)


@router.post("/chat")
def operator_chat(
    body: OperatorChatRequest,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict:
    modality = body.modality if body.modality in ("text", "voice") else "text"
    return run_operator_turn(
        db,
        ctx,
        message=body.message.strip(),
        channel=body.channel,
        conversation_id=body.conversation_id,
        input_modality=modality,
    )


@router.get("/tts")
def operator_tts(
    text: str = Query(..., min_length=1, max_length=800),
    _ctx: TenantContext = Depends(get_tenant_context_auth),
) -> Response:
    """Cabinet voice output — OpenAI TTS (JWT required)."""
    audio, error = synthesize_speech(text)
    if error or not audio:
        code = error or "VOICE_GENERATION_FAILED"
        status = 503 if code == "VOICE_NOT_CONFIGURED" else 502 if code != "TEXT_REQUIRED" else 400
        raise HTTPException(status_code=status, detail=code)
    return Response(
        content=audio,
        media_type="audio/mpeg",
        headers={
            "Cache-Control": "private, max-age=3600",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/voice")
def operator_voice_stub() -> dict:
    """
    Placeholder for voice pipeline: audio upload → STT → /chat → TTS.
    Same operator logic; only I/O differs.
    """
    raise HTTPException(
        status_code=501,
        detail="Voice I/O not implemented yet. Use POST /v1/operator/chat with modality=voice after client-side STT.",
    )


@router.post("/confirm")
def operator_confirm(
    body: OperatorConfirmRequest,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict:
    result = execute_confirmed_tool(db, ctx, tool_name=body.tool_name, params=body.params)
    return {"ok": getattr(result, "ok", False), "message": getattr(result, "message", ""), "data": getattr(result, "data", {})}


@router.get("/conversations")
def list_conversations(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
    limit: int = 50,
    q: str | None = Query(default=None, max_length=120),
    filter: str | None = Query(default=None, max_length=16),
) -> dict:
    rows = (
        db.query(Conversation)
        .filter(Conversation.tenant_id == ctx.tenant_id)
        .order_by(Conversation.updated_at.desc())
        .limit(min(limit, 100))
        .all()
    )
    items = list_conversation_items(db, ctx.tenant_id, rows)
    new_count = sum(1 for i in items if i.get("is_new"))
    items = filter_conversation_items(items, q=q, status_filter=filter)
    return {"items": items, "total": len(items), "new_count": new_count}


@router.get("/conversations/{conversation_id}")
def get_conversation(
    conversation_id: UUID,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict:
    detail = get_conversation_detail(db, ctx.tenant_id, conversation_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return detail


@router.get("/conversations/{conversation_id}/messages")
def list_messages(
    conversation_id: UUID,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict:
    rows = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id, Message.tenant_id == ctx.tenant_id)
        .order_by(Message.created_at.asc())
        .all()
    )
    if not rows:
        conv = (
            db.query(Conversation)
            .filter(Conversation.id == conversation_id, Conversation.tenant_id == ctx.tenant_id)
            .one_or_none()
        )
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
    return {
        "items": [
            {
                "id": str(row.id),
                "role": row.role,
                "body": row.body,
                "meta": row.meta,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ]
    }
