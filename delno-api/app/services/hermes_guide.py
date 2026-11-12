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
