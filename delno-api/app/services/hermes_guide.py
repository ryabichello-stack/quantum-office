"""Deterministic Hermes coach replies — used when OpenAI egress is down."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.services import hermes_ops, phone_provision


def _phone_block(db: Session, ctx: TenantContext) -> str:
    phones = phone_provision.list_phones(db, ctx).get("items") or []
    active = [p for p in phones if p.get("status") == "active"]
    if not active:
        return (
            "Телефон ещё не привязан.\n"
            "Скажите: «привяжи номер +7…» или нажмите чип «Настроить телефон».\n"
            "После привязки DID входящие пойдут на секретаря Frontline."
        )
    lines = ["Телефония уже в кабинете:"]
    for p in active[:5]:
        lines.append(f"• {p.get('e164')} · {p.get('label') or 'main'} · {p.get('status')}")
    lines.append(
        "Секретарь (Frontline) отвечает на этот DID, когда линия Mango/Asterisk в статусе Registered.\n"
        "Сейчас на Cloud4Box регистрация Mango часто Rejected — нужен SIP-пароль сотрудника Mango.\n"
        "Что сделать дальше:\n"
        "1) Проверьте «здоровье офиса».\n"
        "2) Введите SIP-логин и пароль Mango в безопасной форме ниже "
        "(не вставляйте пароль в чат).\n"
        "3) Скажите «какие звонки были»."
    )
    return "\n".join(lines)


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
            "пароль",
            "логин",
            "password",
            "login",
            "доступ",
        )
    ):
        return None

    phone_words = (
        "телефон",
        "секретар",
        "номер",
        "did",
        "mango",
        "входящ",
        "исходящ",
        "лини",
        "sip",
        "настроить телефон",
        "настрой телефон",
        "помоги настроить",
    )
    if any(w in lower for w in phone_words):
        setup = hermes_ops.office_setup_status(db, ctx)
        health = hermes_ops.office_health_report(db, ctx)
        body = [
            "Ок, настраиваем телефонного секретаря — без лишних вопросов.",
            _phone_block(db, ctx),
            "",
            f"Сетап: {setup.get('message_ru')}",
            f"Здоровье: {health.get('message_ru')}",
        ]
        from app.services.tenant_secrets import credential_form_spec

        return {
            "reply": "\n".join(body),
            "tool_calls": [
                {"tool": "hermes.guide.phone", "ok": True},
                {"tool": "phones.list", "ok": True},
                {"tool": "hermes.setup_status", "ok": True},
                {"tool": "hermes.health", "ok": True},
            ],
            "pending_credential_form": credential_form_spec("mango_sip"),
        }

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
