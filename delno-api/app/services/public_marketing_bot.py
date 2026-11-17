"""DELNO's public information bot; deliberately has no cabinet tools."""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.adapters.knowledge import KnowledgeAdapter
from app.core.principals import PRINCIPAL_TEXT_GUEST
from app.core.tenant import TenantContext
from app.models.conversation import Conversation, Message
from app.services.leads import create_lead_record
from app.services.llm_keys import chat_for_tenant

_PHONE = re.compile(r"(?<!\d)(?:\+?7|8)[\s()-]*\d[\d\s()-]{8,16}\d(?!\d)")
_CONTACT_WORDS = ("свяж", "позвон", "оставить контакт", "оставлю контакт", "заявк", "/contact")
_CONSENT_RE = re.compile(
    r"соглас(?:ен|на|енна)\s+на\s+обработку(?:\s+пд[нн]?)?",
    re.IGNORECASE,
)
_FALLBACK_FACTS = (
    "DELNO — ИИ-секретарь для первой линии бизнеса. Консультирует по услугам и ценам "
    "из единой базы знаний, отвечает на сайте, в Telegram, MAX и по телефону. "
    "Поддерживает запись/перенос/отмену встречи, почту и файлы при подключённых инструментах. "
    "Тарифы: «Диалоги» 2 990 ₽/мес (сайт, мессенджеры, KB, до 300 ИИ-диалогов, 30 мин голоса на сайте); "
    "«Диалоги + звонки» 5 990 ₽/мес (+ 100 мин телефонии). Сверх пакета и юр.условия — у менеджера. "
    "Сайт: https://dlno.ru. Почта: office@dlno.ru. Телефон: 8 800 555-94-18. "
    "Политика: https://dlno.ru/privacy. Ответ на заявку: пн–пт 10:00–19:00 МСК."
)
_SYSTEM_BASE = (
    "Ты публичный ИИ-секретарь DELNO. Отвечай по-русски ясно и коротко.\n"
    "Скрипт: спокойный деловой тон; одна мысль — один вопрос; не обещай того, чего нет в базе.\n"
    "Открытие (если диалог только начинается): "
    "«Здравствуйте! Я ИИ-секретарь DELNO: отвечаю клиентам, записываю в календарь и собираю заявки "
    "на сайте, в мессенджерах и по телефону. Рассказать, как это будет у вас, или сразу про тарифы?»\n"
    "Используй только факты из базы знаний ниже; если точных данных нет — скажи честно и предложи "
    "оставить контакт. Не говори, что интеграция уже подключена у собеседника. "
    "Не раскрывай внутренние названия, архитектуру или данные других компаний. "
    "Не вызывай инструменты и не обещай выполнить действие в чужом кабинете. "
    "Instagram/Meta только с пометкой «*Meta признана экстремистской в РФ». "
    "Если человек хочет связаться с командой — сначала согласие на обработку ПДн "
    "и ссылка https://dlno.ru/privacy, затем имя/телефон и «да, свяжитесь со мной».\n\n"
    "База знаний:\n"
)


def _phone(text: str) -> str | None:
    match = _PHONE.search(text)
    if not match:
        return None
    digits = re.sub(r"\D", "", match.group())
    if len(digits) != 11 or digits[0] not in "78":
        return None
    return "+7" + digits[1:]


def _kb_snippet(ctx: TenantContext, query: str) -> str:
    data = KnowledgeAdapter().search(
        query[:400] or "DELNO тарифы возможности",
        tenant_slug=ctx.tenant_slug,
        principal_id=PRINCIPAL_TEXT_GUEST,
        limit=6,
    )
    if not data.get("ok", True):
        return ""
    text = str(data.get("text") or "").strip()
    if text:
        return text[:6000]
    parts: list[str] = []
    for hit in data.get("matches") or data.get("results") or []:
        if not isinstance(hit, dict):
            continue
        chunk = str(hit.get("text") or hit.get("body") or hit.get("snippet") or "").strip()
        title = str(hit.get("title") or "").strip()
        if chunk:
            parts.append(f"{title}\n{chunk}" if title else chunk)
    return "\n\n".join(parts)[:6000]


def _consent_prompt() -> str:
    return (
        "Чтобы передать контакт команде DELNO, нужно ваше согласие на обработку персональных данных. "
        "Политика: https://dlno.ru/privacy — напишите «согласен(на) на обработку ПДн», имя и телефон, "
        "затем «да, свяжитесь со мной»."
    )


def answer_public_bot(
    db: Session, ctx: TenantContext, conversation: Conversation, *,
    message: str, display_name: str | None, source: str,
) -> str:
    """Offer contact collection (152-FZ), then answer from public KB without tools."""
    meta = dict(conversation.meta or {})
    low = message.lower()
    wants_contact = any(word in low for word in _CONTACT_WORDS)
    phone = _phone(message)
    has_consent = bool(meta.get("pdn_consent")) or bool(_CONSENT_RE.search(message))
    if has_consent:
        meta["pdn_consent"] = True
        conversation.meta = meta

    if meta.get("contact_requested") and meta.get("pending_phone") and "да, свяж" in low:
        if not meta.get("pdn_consent"):
            return _consent_prompt()
        chosen_phone = str(meta.get("pending_phone"))
        if not meta.get("lead_id"):
            name = display_name or "Посетитель"
            if "да, свяж" in low:
                suffix = re.split(r"да, свяжитесь со мной", message, flags=re.IGNORECASE)[-1].strip(" .,!—:-")
                if suffix:
                    name = suffix[:120]
            lead, _ = create_lead_record(
                db, ctx, name=name, phone=chosen_phone, source=source,
                audit_action="lead.create.public_bot", event_source="public.bot",
                channel=source, conversation_id=conversation.id,
            )
            meta["lead_id"] = str(lead.id)
            meta.pop("pending_phone", None)
            conversation.meta = meta
        return (
            "Спасибо! Передал контакт команде DELNO. "
            "Свяжемся в течение рабочего дня (пн–пт, 10:00–19:00 МСК)."
        )
    if phone:
        meta["contact_requested"] = True
        meta["pending_phone"] = phone
        conversation.meta = meta
        if not meta.get("pdn_consent"):
            return _consent_prompt()
        return (
            "Могу передать ваш номер команде DELNO. Подтвердите ответом «да, свяжитесь со мной» "
            "и напишите, как к вам обращаться."
        )
    if meta.get("contact_requested") and meta.get("pending_phone") and meta.get("pdn_consent"):
        return (
            "Могу передать ваш номер команде DELNO. Подтвердите ответом «да, свяжитесь со мной» "
            "и напишите, как к вам обращаться."
        )
    if wants_contact:
        meta["contact_requested"] = True
        conversation.meta = meta
        if not meta.get("pdn_consent"):
            return _consent_prompt()
        return (
            "Напишите имя и телефон, затем подтвердите «да, свяжитесь со мной»."
        )

    kb = _kb_snippet(ctx, message)
    facts = kb if kb else _FALLBACK_FACTS
    system = _SYSTEM_BASE + facts

    history = (
        db.query(Message).filter(Message.tenant_id == ctx.tenant_id, Message.conversation_id == conversation.id)
        .order_by(Message.created_at.desc()).limit(9).all()
    )
    messages = [{"role": "system", "content": system}]
    messages.extend({"role": row.role, "content": row.body[:1500]} for row in reversed(history) if row.role in {"user", "assistant"})
    completion = chat_for_tenant(db, ctx, messages=messages, max_tokens=450)
    if completion.get("ok"):
        try:
            text = str(completion["data"]["choices"][0]["message"].get("content") or "").strip()
            if text:
                return text[:4000]
        except (KeyError, IndexError, TypeError):
            pass
    return (
        "Здравствуйте! Я ИИ-секретарь DELNO: отвечаю клиентам, записываю в календарь и собираю заявки. "
        "Рассказать, как это будет у вас, или сразу про тарифы?"
    )
