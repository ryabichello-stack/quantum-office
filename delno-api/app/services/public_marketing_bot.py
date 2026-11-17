"""DELNO's public information bot; deliberately has no cabinet tools."""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.models.conversation import Conversation, Message
from app.services.leads import create_lead_record
from app.services.llm_keys import chat_for_tenant

_PHONE = re.compile(r"(?<!\d)(?:\+?7|8)[\s()-]*\d[\d\s()-]{8,16}\d(?!\d)")
_CONTACT_WORDS = ("свяж", "позвон", "оставить контакт", "оставлю контакт", "заявк", "/contact")
_FACTS = (
    "DELNO — ИИ-секретарь для первой линии бизнеса. Он может консультировать по услугам и ценам "
    "на основе единой базы знаний компании, отвечать в подключённых каналах: на сайте, "
    "в Telegram, MAX и по телефону. Система поддерживает запись, перенос и отмену встречи, "
    "календарь, отправку письма и ссылку на видеовстречу при подключённых инструментах. "
    "Подключения и сценарии настраиваются для каждой компании отдельно. "
    "Стоимость и доступность конкретной интеграции уточняются у команды DELNO. "
    "Сайт: https://dlno.ru. Контакт: office@dlno.ru. Телефон: 8-800-555-94-18."
)
_SYSTEM = (
    "Ты публичный консультант DELNO. Отвечай по-русски ясно и коротко. "
    "Используй только факты ниже; если точных данных нет, честно скажи, что уточнит команда. "
    "Не говори, что интеграция уже подключена у собеседника. Не раскрывай внутренние названия, "
    "архитектуру или данные других компаний. Не вызывай инструменты и не обещай выполнить действие "
    "в чужом кабинете. Если человек хочет связаться с командой, предложи оставить имя и телефон "
    "в этом чате либо на dlno.ru.\n\nФакты: " + _FACTS
)


def _phone(text: str) -> str | None:
    match = _PHONE.search(text)
    if not match:
        return None
    digits = re.sub(r"\D", "", match.group())
    if len(digits) != 11 or digits[0] not in "78":
        return None
    return "+7" + digits[1:]


def answer_public_bot(
    db: Session, ctx: TenantContext, conversation: Conversation, *,
    message: str, display_name: str | None, source: str,
) -> str:
    """Offer contact collection, then answer from public facts without any tools."""
    meta = dict(conversation.meta or {})
    low = message.lower()
    wants_contact = any(word in low for word in _CONTACT_WORDS)
    phone = _phone(message)
    if meta.get("contact_requested") and meta.get("pending_phone") and "да, свяж" in low:
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
        return "Спасибо! Передал контакт команде DELNO. С вами свяжутся."
    if phone:
        meta["contact_requested"] = True
        meta["pending_phone"] = phone
        conversation.meta = meta
        return (
            "Могу передать ваш номер команде DELNO. Подтвердите ответом «да, свяжитесь со мной» "
            "и напишите, как к вам обращаться. Данные нужны только для ответа на заявку."
        )
    if wants_contact:
        meta["contact_requested"] = True
        conversation.meta = meta
        return (
            "Напишите имя и телефон, затем подтвердите «да, свяжитесь со мной». "
            "Данные нужны только для ответа на заявку."
        )

    history = (
        db.query(Message).filter(Message.tenant_id == ctx.tenant_id, Message.conversation_id == conversation.id)
        .order_by(Message.created_at.desc()).limit(9).all()
    )
    messages = [{"role": "system", "content": _SYSTEM}]
    messages.extend({"role": row.role, "content": row.body[:1500]} for row in reversed(history) if row.role in {"user", "assistant"})
    completion = chat_for_tenant(db, ctx, messages=messages, max_tokens=450)
    if completion.get("ok"):
        try:
            text = str(completion["data"]["choices"][0]["message"].get("content") or "").strip()
            if text:
                return text[:4000]
        except (KeyError, IndexError, TypeError):
            pass
    return "Расскажу о DELNO: ИИ-секретарь отвечает клиентам в подключённых каналах и помогает с записью. Что вас интересует?"
