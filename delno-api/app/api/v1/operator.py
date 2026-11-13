from uuid import UUID

from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.auth import get_tenant_context_auth
from app.core.tenant import TenantContext
from app.models.call_session import CallSession
from app.models.conversation import Conversation, Message
from app.models.lead import Lead
from app.models.onboarding_upload import OnboardingUpload
from app.operator.agent import execute_confirmed_tool, run_operator_turn
from app.services.conversation_present import (
    filter_conversation_items,
    get_conversation_detail,
    list_conversation_items,
)
from app.services.stt import transcribe_audio
from app.services.tts import synthesize_speech

router = APIRouter(prefix="/operator", tags=["operator"])


class OperatorAttachment(BaseModel):
    filename: str = Field(default="file", max_length=200)
    content_type: str = Field(default="application/octet-stream", max_length=120)
    data_base64: str = Field(min_length=8, max_length=12_000_000)


class OperatorChatRequest(BaseModel):
    message: str = Field(default="", max_length=4000)
    channel: str = Field(default="web", max_length=32)
    conversation_id: UUID | None = None
    modality: str = Field(default="text", description="text | voice (post-STT)")
    attachments: list[OperatorAttachment] = Field(default_factory=list, max_length=4)


class OperatorConfirmRequest(BaseModel):
    tool_name: str
    params: dict = Field(default_factory=dict)


def _wants_media_generation(message: str) -> bool:
    """Route image/video generation asks to DIY tools (reliable OpenAI Images path)."""
    low = (message or "").lower()
    markers = (
        "generate_image",
        "сгенерируй картин",
        "сгенерируй изображ",
        "создай картин",
        "нарисуй",
        "сгенерируй фото",
        "сделай картин",
        "сделай изображ",
        "generate an image",
        "generate image",
        "draw me",
        "create an image",
    )
    return any(m in low for m in markers)


@router.post("/chat")
def operator_chat(
    body: OperatorChatRequest,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict:
    modality = body.modality if body.modality in ("text", "voice") else "text"
    attachments = [a.model_dump() for a in (body.attachments or [])]
    message = (body.message or "").strip()
    if not message and not attachments:
        raise HTTPException(status_code=422, detail="message_or_attachment_required")

    # Attachments + media-generation intents stay on DIY (Images API / vision / STT).
    prefer_diy = bool(attachments) or _wants_media_generation(message)

    # Fast-path: never rely on the LLM to "agree" to draw — call generate_image now.
    if _wants_media_generation(message) and not attachments:
        from app.operator.tools import register_builtin_tools
        from app.operator.tools.registry import ToolResult, registry

        register_builtin_tools()
        prompt = message
        for prefix in (
            "сгенерируй картинку:",
            "сгенерируй изображение:",
            "создай картинку:",
            "нарисуй:",
            "generate_image:",
            "generate an image:",
            "generate image:",
        ):
            if message.lower().startswith(prefix):
                prompt = message[len(prefix) :].strip() or message
                break
        result = registry.run(db, ctx, "generate_image", prompt=prompt)
        if isinstance(result, ToolResult) and result.ok:
            data = result.data or {}
            md = str(data.get("markdown") or "")
            caption = f"Готово — сгенерировал изображение по запросу: «{prompt[:120]}»."
            return {
                "ok": True,
                "engine": "diy_generate_image",
                "channel": body.channel,
                "conversation_id": body.conversation_id,
                "reply": f"{caption}\n\n{md}".strip() if md else caption,
                "tool_calls": [{"tool": "generate_image", "ok": True, "model": data.get("model")}],
                "modality": modality,
            }
        err = result.message if isinstance(result, ToolResult) else "image_failed"
        # Fall through to DIY LLM with the error context so the owner sees a clear reply.
        message = f"{message}\n\n[system: generate_image failed: {err}]"

    # Feature-flagged Nous Hermes runtime (Stage 0+). DIY loop remains fallback.
    try:
        from app.services.hermes_nous.bridge import HermesBridgeError, create_run
        from app.services.hermes_nous.flags import is_hermes_nous_enabled

        if is_hermes_nous_enabled(db, ctx) and message and not prefer_diy:
            try:
                from app.services.hermes_nous.onboarding import get_office_loop
                from app.services.hermes_nous.tool_packs import pack_for_mode

                # Product loop: until office is ready, Nous runs with onboarding pack
                # (KB + setup + credentials), not full conduct.
                loop = get_office_loop(db, ctx)
                setup_done = bool((loop.get("setup") or {}).get("setup_complete"))
                phase = str(loop.get("phase") or "welcome")
                pack_mode = "conduct" if setup_done or phase in ("ready", "conduct") else "onboarding"
                nous = create_run(
                    db,
                    ctx,
                    message=message,
                    session_id=str(body.conversation_id) if body.conversation_id else None,
                    tool_ids=pack_for_mode(pack_mode),
                    mode=pack_mode,
                )
                return {
                    "ok": True,
                    "engine": "nous_hermes_agent",
                    "channel": body.channel,
                    "conversation_id": body.conversation_id,
                    "reply": nous.get("output")
                    or (nous.get("hermes") or {}).get("output")
                    or "Hermes run started — progress via /v1/hermes-nous/runs/{run_id}.",
                    "hermes_run": nous,
                    "modality": modality,
                }
            except HermesBridgeError as exc:
                # Runtime not up yet → fall through to DIY (documented Stage 0 behavior)
                if exc.status not in (None, 503, 404, 502):
                    raise HTTPException(
                        status_code=exc.status or 503,
                        detail={"error": str(exc), "body": exc.body},
                    ) from exc
    except ImportError:
        pass

    return run_operator_turn(
        db,
        ctx,
        message=message or "",
        channel=body.channel,
        conversation_id=body.conversation_id,
        input_modality=modality,
        attachments=attachments or None,
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


@router.post("/stt")
async def operator_stt(
    file: UploadFile = File(...),
    _ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict:
    """Hermes mic fallback — Whisper transcription (ru)."""
    raw = await file.read()
    text, error = transcribe_audio(raw, filename=file.filename or "audio.webm")
    if error or not text:
        status = 503 if error in {"STT_NOT_CONFIGURED", "STT_AUTH_FAILED"} else 400 if error in {"AUDIO_REQUIRED", "AUDIO_TOO_LARGE", "STT_EMPTY"} else 502
        raise HTTPException(status_code=status, detail=error or "STT_FAILED")
    return {"ok": True, "text": text}


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


def _purge_conversation(db: Session, tenant_id: UUID, conversation_id: UUID) -> int:
    """Remove a conversation and detach/delete FK dependents. Returns message count."""
    db.query(CallSession).filter(
        CallSession.conversation_id == conversation_id, CallSession.tenant_id == tenant_id
    ).delete(synchronize_session=False)
    db.query(OnboardingUpload).filter(
        OnboardingUpload.conversation_id == conversation_id,
        OnboardingUpload.tenant_id == tenant_id,
    ).update({OnboardingUpload.conversation_id: None}, synchronize_session=False)
    db.query(Lead).filter(
        Lead.conversation_id == conversation_id, Lead.tenant_id == tenant_id
    ).update({Lead.conversation_id: None}, synchronize_session=False)
    deleted_messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id, Message.tenant_id == tenant_id)
        .delete(synchronize_session=False)
    )
    db.query(Conversation).filter(
        Conversation.id == conversation_id, Conversation.tenant_id == tenant_id
    ).delete(synchronize_session=False)
    return deleted_messages


@router.delete("/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: UUID,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict:
    """Delete one conversation and its messages for this tenant."""
    conv = (
        db.query(Conversation)
        .filter(Conversation.id == conversation_id, Conversation.tenant_id == ctx.tenant_id)
        .one_or_none()
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    deleted_messages = _purge_conversation(db, ctx.tenant_id, conversation_id)
    db.commit()
    return {"ok": True, "deleted_id": str(conversation_id), "deleted_messages": deleted_messages}


class BulkDeleteConversations(BaseModel):
    ids: list[UUID] = Field(default_factory=list, max_length=200)
    channel: str | None = Field(default=None, max_length=32)
    keep_latest_hermes: bool = False


@router.post("/conversations/bulk-delete")
def bulk_delete_conversations(
    body: BulkDeleteConversations,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict:
    """Delete many conversations by id list and/or channel (junk cleanup)."""
    q = db.query(Conversation).filter(Conversation.tenant_id == ctx.tenant_id)
    if body.ids:
        q = q.filter(Conversation.id.in_(body.ids))
    elif body.channel:
        q = q.filter(Conversation.channel == body.channel.strip().lower())
    else:
        raise HTTPException(status_code=400, detail="Provide ids or channel")

    rows = q.order_by(Conversation.updated_at.desc()).all()
    if body.keep_latest_hermes and body.channel == "hermes" and rows:
        rows = rows[1:]

    deleted_ids: list[str] = []
    for conv in rows:
        _purge_conversation(db, ctx.tenant_id, conv.id)
        deleted_ids.append(str(conv.id))
    db.commit()
    return {"ok": True, "deleted": len(deleted_ids), "ids": deleted_ids}


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
