"""Gate before a test call: script from KB, Cedar voice, tools bound.

Hermes speaks and calls the tools. This module only reports facts and stores
the voice the owner agreed to. A registered phone line is not enough.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.models.tenant_voice_profile import TenantVoiceProfile
from app.services.telephony_script import LINE_TOOLS_BEFORE_TEST, get_telephony_config

CEDAR_VOICE = "cedar"


def _voice_row(db: Session, ctx: TenantContext) -> TenantVoiceProfile | None:
    return (
        db.query(TenantVoiceProfile)
        .filter(TenantVoiceProfile.tenant_id == ctx.tenant_id)
        .one_or_none()
    )


def current_voice(db: Session, ctx: TenantContext) -> str | None:
    row = _voice_row(db, ctx)
    if row is None or not (row.preset_id or "").strip():
        return None
    return str(row.preset_id).strip().lower()


def set_tenant_voice(db: Session, ctx: TenantContext, voice: str = CEDAR_VOICE) -> dict[str, Any]:
    """Remember the voice on THIS company. Does not touch other tenants."""
    name = (voice or CEDAR_VOICE).strip().lower()
    if not name.isalpha() or not 3 <= len(name) <= 32:
        return {"ok": False, "error": "bad_voice", "message_ru": "Такое имя голоса не подойдёт."}
    row = _voice_row(db, ctx)
    if row is None:
        row = TenantVoiceProfile(
            tenant_id=ctx.tenant_id,
            mode="preset",
            provider="openai",
            preset_id=name,
            language="ru",
        )
        db.add(row)
    else:
        row.preset_id = name
        row.provider = "openai"
        row.mode = "preset"
    db.commit()
    return {
        "ok": True,
        "voice": name,
        "cedar": name == CEDAR_VOICE,
        "message_ru": (
            "Голос секретаря — Cedar. Так он будет звучать на звонках."
            if name == CEDAR_VOICE
            else f"Голос секретаря переключён на «{name}»."
        ),
    }


def line_status(db: Session, ctx: TenantContext) -> dict[str, Any]:
    """Facts only. test_call_allowed is true only after script + Cedar + tools."""
    try:
        cfg = get_telephony_config(db, ctx)
    except Exception:  # noqa: BLE001
        cfg = {"configured": False, "tools": []}
    try:
        voice = current_voice(db, ctx)
    except Exception:  # noqa: BLE001
        voice = None
    tools = [t for t in (cfg.get("tools") or []) if isinstance(t, str)]
    missing_tools = [t for t in LINE_TOOLS_BEFORE_TEST if t not in tools]
    script_ready = bool(cfg.get("configured"))
    voice_ready = voice == CEDAR_VOICE
    tools_ready = script_ready and not missing_tools
    test_call_allowed = script_ready and voice_ready and tools_ready

    gaps: list[dict[str, str]] = []
    if not script_ready:
        gaps.append(
            {
                "id": "script",
                "tool": "telephony.script_propose",
                "then": "telephony.script_save",
                "title": "Сценарий",
                "text": "Собери сценарий секретаря из базы знаний",
            }
        )
    if not voice_ready:
        gaps.append(
            {
                "id": "voice",
                "tool": "telephony.voice_set",
                "title": "Голос Cedar",
                "text": "Поставь голос Cedar",
            }
        )
    if not tools_ready:
        gaps.append(
            {
                "id": "tools",
                "tool": "telephony.tools_set",
                "title": "Действия секретаря",
                "text": "Подключи к секретарю календарь, почту и видеовстречу",
            }
        )

    if test_call_allowed:
        message = (
            "Секретарь готов: есть сценарий, голос Cedar и действия "
            "(время, встреча, письмо, ссылка на созвон). Можно сделать пробный звонок."
        )
        suggested = [
            {"title": "Пробный звонок", "text": "Давай сделаем пробный звонок на наш номер"},
            {"title": "Что умеет секретарь", "text": "Что секретарь умеет на звонке?"},
        ]
        next_tool = None
    else:
        parts = []
        if not script_ready:
            parts.append("собрать сценарий из базы знаний")
        if not voice_ready:
            parts.append("поставить голос Cedar")
        if not tools_ready:
            parts.append("подключить календарь, почту и видеовстречу")
        message = (
            "Номер уже работает. Пробный звонок рано — сначала "
            + ", ".join(parts)
            + "."
        )
        suggested = [{"title": g["title"], "text": g["text"]} for g in gaps]
        next_tool = gaps[0]["tool"] if gaps else None

    return {
        "ok": True,
        "script_ready": script_ready,
        "voice": voice,
        "voice_ready": voice_ready,
        "tools": tools,
        "missing_tools": missing_tools,
        "tools_ready": tools_ready,
        "test_call_allowed": test_call_allowed,
        "next_tool": next_tool,
        "gaps": gaps,
        "message_ru": message,
        "suggested_actions": suggested,
    }


def followup_after_registered(db: Session, ctx: TenantContext) -> dict[str, Any]:
    """What to say right after the phone line is Registered."""
    status = line_status(db, ctx)
    return status
