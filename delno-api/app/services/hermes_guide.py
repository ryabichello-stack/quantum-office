"""Deterministic Hermes coach replies — used when OpenAI egress is down."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.services import hermes_ops, phone_provision
from app.services.tenant_vault import credential_form_spec, list_secret_status


def _sip_status(db: Session, ctx: TenantContext) -> dict[str, Any]:
    items = list_secret_status(db, ctx).get("items") or []
    row = next((i for i in items if i.get("kind") == "mango_sip"), None) or {}
    return {
        "configured": bool(row.get("configured")),
        "login_masked": row.get("login_masked") or "",
        "updated_at": row.get("updated_at"),
        "login_looks_partial": bool(row.get("configured") and "/" not in (row.get("login_masked") or "")),
    }


def _phone_block(db: Session, ctx: TenantContext, *, sip: dict[str, Any] | None = None) -> str:
    sip = sip or _sip_status(db, ctx)
    phones = phone_provision.list_phones(db, ctx).get("items") or []
    active = [p for p in phones if p.get("status") == "active"]

    lines: list[str] = []
    if active:
        lines.append("Номер в кабинете уже привязан:")
        for p in active[:5]:
            lines.append(f"• {p.get('e164')} · {p.get('label') or 'main'} · {p.get('status')}")
    else:
        lines.append(
            "Номер (DID) ещё не привязан. Скажите: «привяжи номер +7…» "
            "или нажмите чип «Настроить телефон»."
        )

    if sip.get("configured"):
        lines.append(
            f"SIP Mango сохранён в сейфе кабинета ({sip.get('login_masked') or '••••'}) "
            "— в чат пароль не попадал."
        )
        if sip.get("login_looks_partial"):
            lines.append(
                "Внимание: логин выглядит неполным (ожидается вид `номер/сотрудник`, "
                "например `400348777/garik`). Откройте форму ещё раз и сохраните полный логин."
            )
        else:
            lines.append(
                "Дальше — регистрация линии на Asterisk/Cloud4Box (статус Registered). "
                "Скажите «проверь здоровье» или «какие звонки были»."
            )
    else:
        lines.append(
            "SIP-логин и пароль Mango ещё не сохранены. "
            "Введите их в безопасной форме ниже — не вставляйте пароль в чат."
        )
    return "\n".join(lines)


def _is_status_question(lower: str) -> bool:
    status_cues = (
        "настроен",
        "настроена",
        "настроено",
        "уже сохран",
        "сохранил",
        "сохранено",
        "готово",
        "готов ли",
        "работает",
        "статус",
        "провери",
        "как дела",
        "что с телефон",
        "телефон ок",
    )
    return any(c in lower for c in status_cues)


def _wants_new_sip_form(lower: str, *, sip_configured: bool) -> bool:
    if any(
        k in lower
        for k in (
            "форму",
            "заново",
            "ещё раз",
            "еще раз",
            "сменить пароль",
            "поменять пароль",
            "обновить sip",
            "новый пароль",
        )
    ):
        return True
    if not sip_configured and any(k in lower for k in ("пароль", "логин", "sip", "mango", "манго")):
        return True
    return not sip_configured and not _is_status_question(lower)


def _voice_block(db: Session, ctx: TenantContext, message: str) -> dict[str, Any] | None:
    lower = message.lower()
    voice_words = ("голос", "voice", "realtime", "смени голос", "какой голос")
    if not any(w in lower for w in voice_words):
        return None
    from app.core.config import get_settings
    from app.models.tenant_voice_profile import TenantVoiceProfile

    settings = get_settings()
    model = getattr(settings, "openai_realtime_model", None) or "gpt-realtime-2.1-mini"
    default_voice = getattr(settings, "openai_realtime_voice", None) or "cedar"
    row = (
        db.query(TenantVoiceProfile)
        .filter(TenantVoiceProfile.tenant_id == ctx.tenant_id)
        .one_or_none()
    )
    current = (row.preset_id if row and row.preset_id else default_voice) or default_voice
    # "смени голос на X"
    new_voice = None
    for token in ("на ", "to ", "voice "):
        if token in lower:
            part = lower.split(token, 1)[-1].strip().split()[0].strip(".,!")
            if part.isalpha() and 3 <= len(part) <= 32:
                new_voice = part
                break
    if new_voice and new_voice not in ("голос", "voice", "realtime"):
        if row is None:
            row = TenantVoiceProfile(
                tenant_id=ctx.tenant_id,
                mode="preset",
                provider="openai",
                preset_id=new_voice,
                language="ru",
            )
            db.add(row)
        else:
            row.preset_id = new_voice
            row.provider = "openai"
            row.mode = "preset"
        db.commit()
        current = new_voice
        head = f"Голос Realtime переключил на «{current}» (модель {model})."
    else:
        head = f"Сейчас голос «{current}», модель {model} (как в архиве: gpt-realtime-2.1-mini / cedar)."
    return {
        "reply": (
            f"{head}\n"
            "Скажите «смени голос на cedar|alloy|echo|shimmer|…». "
            "Для звонков AVA читает ai-agent.local.yaml; кабинетный профиль — tenant_voice_profiles."
        ),
        "tool_calls": [{"tool": "hermes.voice", "ok": True, "voice": current, "model": model}],
        "suggested_actions": [
            {"title": "Голос cedar", "text": "Смени голос на cedar"},
            {"title": "Тест линии", "text": "Проверь регистрацию SIP и здоровье телефонии"},
        ],
    }


def _lost_user_guide(db: Session, ctx: TenantContext) -> dict[str, Any]:
    """Plain-language next steps when the owner is confused."""
    from app.services.sip_probe import probe_registration

    setup = hermes_ops.office_setup_status(db, ctx)
    sip = _sip_status(db, ctx)
    probe = probe_registration()
    phones = phone_provision.list_phones(db, ctx).get("items") or []
    active = [p for p in phones if p.get("status") == "active"]

    lines = [
        "Ок, без воды — вот что делаем по порядку.",
        "",
    ]
    step = 1
    if not active:
        lines.append(f"{step}) Привязать телефонный номер (DID). Скажите: «привяжи номер +7…».")
        step += 1
    else:
        lines.append(f"{step}) Номер уже есть: {active[0].get('e164')} — этот шаг закрыт.")
        step += 1
    if not sip.get("configured"):
        lines.append(
            f"{step}) Сохранить SIP Mango в безопасной форме (логин вида `номер/сотрудник` + SIP-пароль). "
            "Скажите «пришли форму» — открою форму, в чат пароль не пишите."
        )
        step += 1
    elif not probe.get("ok"):
        lines.append(
            f"{step}) SIP в сейфе есть, но линия {probe.get('status') or 'не Registered'}. "
            "Пересохраните полный логин/пароль в форме или скажите «дай задание Cursor»."
        )
        step += 1
    else:
        lines.append(f"{step}) Линия Registered — можно тестовый звонок.")
        step += 1
    nxt = (setup.get("next_steps") or [None])[0]
    if nxt and nxt.get("id") not in ("phone",):
        lines.append(f"{step}) Дальше по офису: {nxt.get('title')} — {nxt.get('hint')}.")
    lines.append("")
    lines.append("Напишите «пришли форму» или «тестовый звонок» — пойдём в выбранный шаг.")

    out: dict[str, Any] = {
        "reply": "\n".join(lines),
        "tool_calls": [{"tool": "hermes.guide.lost", "ok": True}],
        "suggested_actions": [
            {"title": "Форма SIP", "text": "Пришли форму, я введу логин"},
            {"title": "Статус линии", "text": "Телефон уже настроен?"},
            {"title": "Что дальше", "text": "Статус сетапа"},
        ],
    }
    if not sip.get("configured") or not probe.get("ok"):
        out["pending_credential_form"] = credential_form_spec("mango_sip")
    return out


def coach_reply(db: Session, ctx: TenantContext, message: str) -> dict[str, Any] | None:
    lower = (message or "").lower().strip()
    if not lower:
        return None

    # Don't steal list/health/billing/website intents
    if any(
        t in lower
        for t in (
            "какие звонки",
            "список звонков",
            "проверь здоровье",
            "здоровье офиса",
            "баланс",
            "тариф",
            "расход токенов",
            "зайди на",
            "собери знания",
            "импорт сайта",
            "парси",
            ".ru",
            ".com",
            "http://",
            "https://",
        )
    ):
        return None

    lost_cues = (
        "ничего не понимаю",
        "не понимаю",
        "что делать",
        "что мне делать",
        "подскажи что",
        "с чего начать",
        "помоги разобраться",
        "я запутался",
        "я запуталась",
        "объясни по шагам",
        "по шагам",
        "что нужно сделать",
        "что дальше делать",
    )
    if any(c in lower for c in lost_cues):
        return _lost_user_guide(db, ctx)

    voice = _voice_block(db, ctx, message)
    if voice:
        return voice

    if any(k in lower for k in ("задание cursor", "задачу cursor", "дай задание", "почини через cursor")):
        from app.services.sip_probe import CURSOR_TASK_SIP_REJECTED, probe_registration

        probe = probe_registration()
        return {
            "reply": (
                "Вот задание для Cursor по SIP/телефонии. Скопируйте в агент:\n\n"
                f"{CURSOR_TASK_SIP_REJECTED}\n\n"
                f"Текущий статус линии: {probe.get('message_ru')}"
            ),
            "tool_calls": [{"tool": "hermes.cursor_task", "ok": True, "topic": "sip"}],
            "suggested_actions": [
                {"title": "Форма SIP", "text": "Открой безопасную форму SIP Mango"},
                {"title": "Статус линии", "text": "Проверь регистрацию SIP"},
            ],
        }

    # Password paste / explicit form requests handled elsewhere; don't swallow
    # pure credential paste into the coach.
    if any(t in lower for t in ("password", "login")) and "телефон" not in lower:
        return None

    phone_words = (
        "телефон",
        "секретар",
        "номер",
        "did",
        "mango",
        "манго",
        "входящ",
        "исходящ",
        "лини",
        "sip",
        "настроить телефон",
        "настрой телефон",
        "помоги настроить",
    )
    if any(w in lower for w in phone_words) or (
        _is_status_question(lower) and any(w in lower for w in ("телефон", "sip", "лини", "секретар", "звон"))
    ):
        sip = _sip_status(db, ctx)
        setup = hermes_ops.office_setup_status(db, ctx)
        health = hermes_ops.office_health_report(db, ctx)
        status_q = _is_status_question(lower)
        show_form = _wants_new_sip_form(lower, sip_configured=bool(sip.get("configured")))

        if status_q and sip.get("configured"):
            head = "Да — SIP уже сохранён в кабинете. Не начинаю настройку заново."
        elif sip.get("configured"):
            head = "Телефония частично готова: данные SIP уже есть. Смотрим, что ещё осталось."
        else:
            head = "Ок, настраиваем телефонного секретаря — без лишних вопросов."

        body = [
            head,
            _phone_block(db, ctx, sip=sip),
            "",
            f"Сетап: {setup.get('message_ru')}",
            f"Здоровье: {health.get('message_ru')}",
        ]
        out: dict[str, Any] = {
            "reply": "\n".join(body),
            "tool_calls": [
                {"tool": "hermes.guide.phone", "ok": True, "sip_configured": bool(sip.get("configured"))},
                {"tool": "phones.list", "ok": True},
                {"tool": "hermes.setup_status", "ok": True},
                {"tool": "hermes.health", "ok": True},
            ],
        }
        if show_form:
            out["pending_credential_form"] = credential_form_spec("mango_sip")
        # Proactive next chips
        try:
            from app.services.sip_probe import probe_registration, _next_actions

            probe = probe_registration()
            out["tool_calls"].append(
                {
                    "tool": "sip.probe",
                    "ok": bool(probe.get("ok")),
                    "status": probe.get("status"),
                    "suggested_actions": _next_actions(probe),
                }
            )
            if not probe.get("ok") and sip.get("configured"):
                out["reply"] += (
                    "\n\nАвтопроверка: линия ещё не Registered. "
                    "Могу выдать задание для Cursor или снова открыть форму SIP."
                )
            elif probe.get("ok"):
                out["reply"] += "\n\nАвтопроверка: линия Registered. Следующий шаг — тестовый звонок."
        except Exception:  # noqa: BLE001
            pass
        return out

    setup_words = (
        "настрой офис",
        "настроить офис",
        "как начать",
        "что делать дальше",
        "что дальше",
        "помоги с сетапом",
        "статус сетапа",
    )
    if any(w in lower for w in setup_words) or (
        "сетап" in lower and any(w in lower for w in ("статус", "что", "помог", "покаж"))
    ):
        setup = hermes_ops.office_setup_status(db, ctx)
        next_steps = setup.get("next_steps") or []
        lines = [
            setup.get("message_ru") or "Продолжаем сетап офиса.",
            "Конкретные шаги:",
        ]
        if next_steps:
            for i, step in enumerate(next_steps[:3], 1):
                lines.append(f"{i}) {step.get('title')}: {step.get('hint')}")
        else:
            lines.append("Обязательные шаги закрыты. Можно проверять звонки и каналы.")
        lines.append("Голосом: удержите mic у поля ввода и надиктуйте задание.")
        return {
            "reply": "\n".join(lines),
            "tool_calls": [{"tool": "hermes.guide.setup", "ok": True}],
        }

    return None


def llm_unavailable_reply(message: str) -> str:
    return (
        "Сейчас умный LLM на сервере недоступен (OpenAI с Cloud4Box режется по региону — "
        "нужен SOCKS моста СПБ→Минск→NL в OPENAI_HTTP_PROXY).\n"
        "Пока работаю короткими командами: «статус сетапа», «настрой телефон», "
        "«проверь здоровье», «баланс», «какие звонки».\n"
        f"Ваш запрос: «{message.strip()[:180]}» — уточните одной из команд выше, "
        "или дайте proxy моста, и я отвечу полноценно."
    )
