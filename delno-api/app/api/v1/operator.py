from datetime import datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

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
    """Route image/video generation asks to DIY tools (reliable OpenAI Images path).

    Match contiguous phrases and adverb-interrupted ones
    («сгенерируй простую картинку») — otherwise Nous onboarding pack has no
    generate_image and the owner gets a dead-end reply.
    """
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
        "create a picture",
        "draw a",
    )
    if any(m in low for m in markers):
        return True
    verbs = (
        "сгенерируй",
        "сгенерировать",
        "создай",
        "нарисуй",
        "сделай",
        "generate",
        "draw",
    )
    nouns = (
        "картин",
        "изображ",
        "фото",
        "image",
        "picture",
        "illustration",
        "mockup",
        "мокап",
        "обложк",
    )
    return any(v in low for v in verbs) and any(n in low for n in nouns)


def _wants_calendar_slots(message: str) -> bool:
    """Clear «предложи слоты» intents — DIY, do not trust Nous to call the tool."""
    low = (message or "").lower()
    has_cal = any(
        m in low
        for m in (
            "слот",
            "календар",
            "свободн",
            "встреч",
            "meeting slot",
            "calendar slot",
        )
    )
    has_ask = any(
        m in low
        for m in (
            "предлож",
            "найди",
            "покажи",
            "подбери",
            "suggest",
            "свободные",
        )
    )
    return has_cal and has_ask


def _calendar_slot_start_iso(message: str) -> str:
    """Best-effort start ISO in Europe/Moscow from owner wording."""
    low = (message or "").lower()
    tz = ZoneInfo("Europe/Moscow")
    now = datetime.now(tz)
    day = now.date()
    if "послезавтра" in low:
        day = (now + timedelta(days=2)).date()
    elif "завтра" in low:
        day = (now + timedelta(days=1)).date()
    hour = 10
    for h, keys in (
        (9, ("утром", "9:", "09:")),
        (12, ("в обед", "12:")),
        (15, ("днём", "днев", "15:")),
        (18, ("вечером", "18:")),
    ):
        if any(k in low for k in keys):
            hour = h
            break
    return datetime(day.year, day.month, day.day, hour, 0, tzinfo=tz).isoformat()


def _calendar_duration_min(message: str) -> int:
    low = (message or "").lower()
    if "30" in low or "полчас" in low:
        return 30
    if "2 час" in low or "два час" in low:
        return 120
    return 60


# hermes_ops checklist id → vault form kind (only when the mapping is unambiguous).
_SETUP_NEXT_TO_FORM_KIND: dict[str, str] = {
    "phone": "mango_sip",
    "telegram": "telegram_bot",
    "max": "max_bot",
    "files": "files_yadisk",
}


def _asks_setup_progress(message_low: str) -> bool:
    """Owner asks «what's next» / continue office setup — not a post-save status ping."""
    return any(
        m in message_low
        for m in (
            "что дальше",
            "следующий шаг",
            "что сейчас по сетап",
            "что по сетап",
            "продолжим",
            "продолжить сетап",
            "продолжить настройк",
            "давай дальше",
            "давайте дальше",
            "настроим офис",
            "настроить офис",
            "статус сетап",
        )
    )


def _form_kind_for_setup_next(
    setup_next_id: str | None,
    setup_substep: str | None,
) -> str | None:
    """Vault kind for the current hermes_ops step, or None when tools (not form) are next."""
    sid = str(setup_next_id or "")
    mapped = _SETUP_NEXT_TO_FORM_KIND.get(sid)
    if not mapped:
        return None
    # Phone: form only while SIP vault empty. need_did / need_reg → Hermes tools.
    if sid == "phone" and setup_substep not in (None, "", "need_sip"):
        return None
    return mapped


def _credential_form_kind_from_message(
    message: str,
    *,
    setup_next_id: str | None = None,
    setup_substep: str | None = None,
) -> str | None:
    """Map owner intent → vault form kind. Secrets never belong in chat text.

    Aligns with PRODUCT_LOOP: credentials.open_form must reach the cabinet as
    pending_credential_form. Nous text-only replies cannot surface the card, so
    the API opens the form when intent (or the office-loop CTA) is clear.
    Do not over-match generic «подключи …» — that would open the wrong vault.
    After SIP is saved (substep need_did / need_reg) do not reopen mango_sip
    unless the owner explicitly asks for the form.
    """
    low = (message or "").lower()
    wants_form = (
        "credentials.open_form" in low
        or "открой форму" in low
        or "открой безопасную форму" in low
        or "пришли форму" in low
    )
    if wants_form:
        if "yadisk" in low or "яндекс" in low:
            return "files_yadisk"
        if "mail.ru" in low or "mailru" in low:
            return "files_mailru"
        if "gdrive" in low or "google drive" in low or "гугл диск" in low:
            return "files_gdrive"
        if "onedrive" in low or "one drive" in low:
            return "files_onedrive"
        if "sip" in low or "mango" in low:
            return "mango_sip"
        if "telegram" in low or "телеграм" in low or "botfather" in low:
            return "telegram_bot"
        if "max_bot" in low or "макс" in low or (setup_next_id == "max" and "max" in low):
            return "max_bot"
        if "телефон" in low:
            return "mango_sip"
        # CTA / open_form without kind → use hermes_ops next step when unambiguous.
        return _form_kind_for_setup_next(setup_next_id, setup_substep)
    # Do NOT match post-save follow-ups («SIP сохранён…») — those must reach Hermes/DIY
    # for status, not reopen the vault card in a loop. Bare «что дальше» is handled below.
    if any(
        x in low
        for x in (
            "сохранён",
            "сохранен",
            "проверь регистрац",
            "телефон настроен",
            "registered",
        )
    ):
        return None
    # PRODUCT_LOOP: «что дальше / настроим офис» on a vault step → open the form
    # instead of a Nous text waffle that cannot surface CredentialFormCard.
    progress_kind = _form_kind_for_setup_next(setup_next_id, setup_substep)
    if progress_kind and _asks_setup_progress(low):
        return progress_kind
    # Only auto-open SIP while vault is still empty (need_sip). Later micro-steps
    # are DID provision / registration — Hermes tools, not the form.
    if setup_next_id == "phone" and (setup_substep in (None, "", "need_sip")) and any(
        m in low
        for m in (
            "sip",
            "mango",
            "телефон",
            "did",
            "линию",
            "линия",
            "телефони",
            "настроить: телефон",
        )
    ):
        return "mango_sip"
    # Messenger / files vault steps — clear connect intent opens the form
    # (Nous cannot surface CredentialFormCard).
    connectish = any(
        m in low
        for m in (
            "подключ",
            "настро",
            "открой",
            "пришли",
            "токен",
            "botfather",
            "подключить:",
            "настроить:",
        )
    )
    if connectish or setup_next_id == "telegram":
        if any(m in low for m in ("telegram", "телеграм", "tg bot", "тг бот")):
            return "telegram_bot"
    if connectish or setup_next_id == "max":
        if any(m in low for m in ("max_bot", "макс бот", "бот max", "бот макс")) or (
            setup_next_id == "max" and ("max" in low or "макс" in low)
        ):
            return "max_bot"
    if setup_next_id == "files" and any(
        m in low for m in ("файл", "диск", "yadisk", "яндекс", "облак", "mail.ru", "gdrive", "onedrive")
    ):
        if "mail.ru" in low or "mailru" in low:
            return "files_mailru"
        if "gdrive" in low or "google" in low or "гугл" in low:
            return "files_gdrive"
        if "onedrive" in low:
            return "files_onedrive"
        return "files_yadisk"
    return None


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

    # Attachments + media/calendar intents stay on DIY (Images / vision / STT / slots).
    prefer_diy = (
        bool(attachments)
        or _wants_media_generation(message)
        or _wants_calendar_slots(message)
    )

    # Vault forms must reach the cabinet as pending_credential_form. Nous text-only
    # runs cannot surface the UI card — open the form server-side when intent is clear.
    try:
        from app.services.hermes_nous.onboarding import get_office_loop

        loop_preview = get_office_loop(db, ctx)
        sn = (loop_preview.get("setup_next") or {}) if isinstance(loop_preview, dict) else {}
        setup_next_id = str(sn.get("id") or "") or None
        setup_substep = str(sn.get("substep") or "") or None
    except Exception:  # noqa: BLE001
        loop_preview = None
        setup_next_id = None
        setup_substep = None
    form_kind = _credential_form_kind_from_message(
        message, setup_next_id=setup_next_id, setup_substep=setup_substep
    )
    if form_kind and not attachments:
        from app.operator.tools import register_builtin_tools
        from app.operator.tools.registry import ToolResult, registry

        register_builtin_tools()
        result = registry.run(db, ctx, "credentials.open_form", kind=form_kind)
        if isinstance(result, ToolResult) and result.ok:
            form = (result.data or {}).get("pending_credential_form")
            return {
                "ok": True,
                "engine": "diy_credential_form",
                "channel": body.channel,
                "conversation_id": body.conversation_id,
                "reply": result.message
                or "Открыл безопасную форму. Секрет не пишите в чат — только в форме.",
                "tool_calls": [{"tool": "credentials.open_form", "ok": True, "kind": form_kind}],
                "pending_credential_form": form if isinstance(form, dict) else None,
                "modality": modality,
                "office_loop": loop_preview,
            }

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

    # Conduct fast-path: calendar slots (Nous often fails to call the MCP tool).
    if _wants_calendar_slots(message) and not attachments:
        from app.operator.tools import register_builtin_tools
        from app.operator.tools.registry import ToolResult, registry

        register_builtin_tools()
        start = _calendar_slot_start_iso(message)
        duration = _calendar_duration_min(message)
        result = registry.run(
            db,
            ctx,
            "suggest_calendar_slots",
            start=start,
            duration_min=duration,
        )
        if isinstance(result, ToolResult) and result.ok:
            data = result.data or {}
            suggestions = data.get("suggestions") or (data.get("data") or {}).get("suggestions") or []
            if not suggestions and isinstance(data.get("data"), dict):
                suggestions = data["data"].get("suggestions") or []
            lines = []
            for i, slot in enumerate(suggestions[:5], 1):
                if isinstance(slot, dict):
                    label = slot.get("label") or slot.get("start") or str(slot)
                else:
                    label = str(slot)
                lines.append(f"{i}. {label}")
            body_txt = "\n".join(lines) if lines else (result.message or "Слоты получены.")
            stub = bool(
                data.get("stub")
                or (data.get("data") or {}).get("stub")
                or any(isinstance(s, dict) and s.get("stub") for s in suggestions)
            )
            note = " (черновик/stub — CalDAV ещё без живых кредов)" if stub else ""
            return {
                "ok": True,
                "engine": "diy_calendar_slots",
                "channel": body.channel,
                "conversation_id": body.conversation_id,
                "reply": f"Варианты слотов на {start} · {duration} мин{note}:\n{body_txt}",
                "tool_calls": [
                    {
                        "tool": "suggest_calendar_slots",
                        "ok": True,
                        "start": start,
                        "duration_min": duration,
                        "stub": stub,
                    }
                ],
                "modality": modality,
            }
        err = result.message if isinstance(result, ToolResult) else "calendar_failed"
        message = f"{message}\n\n[system: suggest_calendar_slots failed: {err}]"

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
                    office_context={
                        "phase": phase,
                        "kb_ok": bool(loop.get("kb_ok")),
                        "setup_next": loop.get("setup_next"),
                        "setup_complete": setup_done,
                    },
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
