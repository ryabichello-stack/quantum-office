import re
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


def _wants_conference_create(message: str) -> bool:
    """«создай видеовстречу / Telemost» — DIY create_conference (stub-capable)."""
    low = (message or "").lower()
    markers = (
        "видеовстреч",
        "видеоконференц",
        "конференц",
        "telemost",
        "телемост",
        "google meet",
        "zoom",
        "вкс",
        "create_conference",
        "create a meeting",
    )
    create = any(
        m in low
        for m in (
            "создай",
            "создать",
            "организуй",
            "организовать",
            "сделай встреч",
            "create conference",
            "create a meeting",
            "schedule a call",
        )
    )
    return create and any(m in low for m in markers)


def _conference_provider(message: str) -> str:
    low = (message or "").lower()
    if "zoom" in low:
        return "zoom"
    if "meet" in low or "google" in low:
        return "google_meet"
    if "teams" in low:
        return "teams"
    if "jitsi" in low:
        return "jitsi"
    # Telemost / default
    return "yandex"


def _conference_title(message: str) -> str:
    import re

    m = re.search(r"названи[ея]\s+(.+)$", message or "", re.I)
    if m:
        return m.group(1).strip(" .,\"'«»")[:200] or "Встреча DELNO"
    m = re.search(r"[«\"]([^»\"]{3,120})[»\"]", message or "")
    if m:
        return m.group(1).strip()[:200]
    return "Встреча DELNO"


def _wants_office_health(message: str) -> bool:
    low = (message or "").lower()
    return any(
        m in low
        for m in (
            "hermes.health",
            "office.health",
            "статус офиса",
            "здоровье офиса",
            "office health",
            "проверь офис",
            "health офиса",
            "регистраци",  # «проверь регистрацию SIP»
            "sip registered",
            "проверь sip",
            "статус sip",
        )
    )


def _wants_phones_list(message: str) -> bool:
    low = (message or "").lower()
    asks = any(
        m in low
        for m in (
            "phones.list",
            "телефонн",
            "мои номер",
            "номера did",
            "list phones",
            "какие номер",
            "покажи номер",
            "перечисли номер",
            "список номер",
        )
    )
    phoneish = any(m in low for m in ("телефон", "номер", "did", "phones", "линии"))
    return asks or (
        phoneish
        and any(m in low for m in ("перечисл", "покажи", "список", "какие", "list"))
    )


def _wants_calls_list(message: str) -> bool:
    """«покажи звонки / история звонков» — DIY calls.list (not phones.list / dial)."""
    low = (message or "").lower()
    if any(m in low for m in ("позвони", "набери", "набрать", "calls.dial", "dial ")):
        return False
    if "calls.list" in low:
        return True
    callish = any(
        m in low
        for m in (
            "звонк",
            "call history",
            "call log",
            "recent calls",
            "list calls",
        )
    )
    ask = any(
        m in low
        for m in (
            "покажи",
            "перечисл",
            "список",
            "какие",
            "история",
            "последн",
            "list",
            "recent",
        )
    )
    return callish and ask


def _wants_telephony_script(message: str) -> bool:
    """Ava script get/propose — DIY so Nous cannot skip telephony.script_* tools."""
    low = (message or "").lower()
    if "telephony.script_get" in low or "telephony.script_propose" in low:
        return True
    scriptish = any(
        m in low
        for m in (
            "сценари",
            "скрипт секретар",
            "скрипт ava",
            "скрипт авы",
            "ava script",
            "secretary script",
        )
    )
    ask = any(
        m in low
        for m in (
            "покажи",
            "какой",
            "какая",
            "предложи",
            "сгенерир",
            "создай",
            "надиктуй",
            "готов",
            "есть ли",
            "проверь",
            "сохрани",
            "сохранить",
            "запиши",
            "get",
            "propose",
            "save",
        )
    )
    # Avoid stealing generic «создай конференцию» / CRM — need scriptish.
    return scriptish and ask


def _telephony_script_wants_propose(message: str) -> bool:
    low = (message or "").lower()
    if "telephony.script_propose" in low:
        return True
    if _telephony_script_wants_save(message):
        return False
    return any(
        m in low
        for m in (
            "предложи",
            "сгенерир",
            "создай сценари",
            "надиктуй",
            "черновик",
            "propose",
        )
    )


def _telephony_script_wants_save(message: str) -> bool:
    low = (message or "").lower()
    if "telephony.script_save" in low:
        return True
    return any(
        m in low
        for m in (
            "сохрани сценари",
            "сохранить сценари",
            "сохрани скрипт",
            "запиши сценари",
            "save script",
            "script_save",
        )
    )


def _wants_get_knowledge(message: str) -> bool:
    low = (message or "").lower()
    kb = any(
        m in low
        for m in (
            "get_knowledge",
            "базе знаний",
            "база знаний",
            "базу знаний",
            "knowledge base",
            "в kb",
            "из kb",
            "что известно о компан",
            "что в баз",
        )
    )
    ask = any(
        m in low
        for m in (
            "найди",
            "поиск",
            "кратко",
            "расскажи",
            "что ",
            "покажи",
            "get_knowledge",
            "про ",
        )
    )
    return kb and ask


def _wants_channel_connect_flow(message: str) -> bool:
    """Telegram/MAX connect chooser, bot help, or QR path — DIY before Nous."""
    from app.services.channel_chooser import wants_channel_connect_intent

    if wants_channel_connect_intent(message) is not None:
        return True
    low = (message or "").lower()
    return _asks_setup_progress(low) and any(
        m in low for m in ("телеграм", "telegram", "макс", "max", "тг")
    )


def _wants_files_cloud_status(message: str) -> bool:
    low = (message or "").lower()
    # Imperative connect («подключи / настрой») → vault form, not status DIY.
    # Past/participle «подключены» is status and must stay here.
    if any(
        m in low
        for m in (
            "подключи",
            "подключить",
            "настрой",
            "настроить",
            "открой форму",
            "пришли форму",
        )
    ):
        return False
    return any(
        m in low
        for m in (
            "files.cloud_status",
            "какие облак",
            "какие диск",
            "облака подключен",
            "облако подключен",
            "статус облак",
            "cloud status",
            "cloud disks",
        )
    ) and any(
        m in low
        for m in (
            "облак",
            "диск",
            "yadisk",
            "cloud",
            "drive",
            "onedrive",
            "mail.ru",
            "файлы",
            "files.cloud",
            "яндекс",
        )
    )


def _wants_hermes_capabilities(message: str) -> bool:
    low = (message or "").lower()
    return any(
        m in low
        for m in (
            "hermes.capabilities",
            "office.connectors",
            "какие коннектор",
            "готовые коннектор",
            "какие тул",
            "какие инструмент",
            "что подключено",
            "capabilities",
            "готовность подключен",
            "статус коннектор",
        )
    )


def _wants_billing_summary(message: str) -> bool:
    low = (message or "").lower()
    return any(
        m in low
        for m in (
            "billing.summary",
            "баланс биллинг",
            "баланс токен",
            "покажи баланс",
            "billing",
            "тариф",
            "сколько токен",
            "usage summary",
        )
    ) and any(
        m in low
        for m in (
            "баланс",
            "биллинг",
            "billing",
            "тариф",
            "токен",
            "usage",
            "summary",
            "покажи",
            "показать",
        )
    )


def _wants_crm_funnel(message: str) -> bool:
    low = (message or "").lower()
    return any(
        m in low
        for m in (
            "crm.funnel",
            "crm воронк",
            "воронк",
            "воронку",
            "funnel",
            "crm статус",
        )
    ) and any(
        m in low
        for m in (
            "покажи",
            "показать",
            "кратко",
            "статус",
            "воронк",
            "funnel",
            "crm",
        )
    )


def _extract_http_urls(message: str) -> list[str]:
    from app.services.web_browser import extract_urls

    return extract_urls(message or "")


def _wants_agent_orchestration(message: str) -> bool:
    """Compound / multi-step goals → full agent loop (Nous or DIY LLM), not a single DIY shortcut."""
    low = (message or "").lower()
    markers = (
        "по шагам",
        "по шагу",
        "составь план",
        "составить план",
        "разложи задач",
        "разложи на",
        "выполни план",
        "выполняй по",
        "сначала ",
        " потом ",
        " затем ",
        "после этого",
        "и потом",
        "действуй",
        "сам через tool",
        "через tools",
        "агентн",
        "оркестр",
    )
    if any(m in low for m in markers):
        return True
    if re.search(
        r"(?:^|\n)\s*[1][\).\]]\s+\S[\s\S]{0,400}(?:^|\n)\s*[2][\).\]]\s+\S",
        low,
    ):
        return True
    hits = 0
    if _extract_http_urls(message) or any(x in low for x in ("сайт", "ссылк", "instagram", "t.me")):
        hits += 1
    if any(x in low for x in ("баз знан", "в знани", "knowledge", "в kb", "импорт сайт")):
        hits += 1
    if any(x in low for x in ("скрипт", "сценари", "обзвон", "ava")):
        hits += 1
    if any(x in low for x in ("письм", "mail", "smtp", "отправь на")):
        hits += 1
    if any(x in low for x in ("календар", "встреч", "конферен", "telemost", "слот")):
        hits += 1
    if any(x in low for x in ("crm", "лид", "воронк")):
        hits += 1
    if any(x in low for x in ("облак", "яндекс диск", "gdrive", "файл")):
        hits += 1
    return hits >= 2


def _tool_calls_from_nous(nous: dict) -> list:
    """Surface Hermes/Nous steps as tool_calls for the thinking UI."""
    out: list = []
    hermes = nous.get("hermes") if isinstance(nous.get("hermes"), dict) else {}
    for key in ("steps", "tool_calls", "tools", "actions"):
        raw = hermes.get(key) or nous.get(key)
        if not isinstance(raw, list):
            continue
        for item in raw[:20]:
            if not isinstance(item, dict):
                continue
            tool = (
                item.get("tool")
                or item.get("name")
                or item.get("tool_id")
                or item.get("kind")
                or item.get("safe_summary")
            )
            if not tool:
                continue
            out.append(
                {
                    "tool": str(tool)[:120],
                    "ok": item.get("ok", item.get("status") in (None, "ok", "completed", "succeeded", "done")),
                    "detail": str(item.get("safe_summary") or item.get("status") or "")[:160],
                }
            )
    if not out and nous.get("tool_ids"):
        out.append(
            {
                "tool": "hermes.agent_run",
                "ok": True,
                "detail": f"pack={nous.get('pack_mode') or '—'} tools={len(nous.get('tool_ids') or [])}",
            }
        )
    return out


def _wants_web_research(message: str) -> bool:
    """User pasted a link or asked Hermes to open/study a site / public channel."""
    if _extract_http_urls(message):
        return True
    low = (message or "").lower()
    verbs = (
        "зайди",
        "зайди на",
        "зайди в",
        "открой",
        "открой сайт",
        "посмотри",
        "посмотреть",
        "просканируй",
        "проскан",
        "проанализируй",
        "изучи",
        "собери информацию",
        "что за сайт",
        "расскажи про сайт",
        "browse",
        "fetch",
    )
    targets = (
        "сайт",
        "ссылк",
        "url",
        "instagram",
        "инстаграм",
        "телеграм",
        "telegram",
        "t.me",
        "макс",
        " max",
        "группу",
        "канал",
        "страниц",
    )
    if any(v in low for v in verbs) and any(t in low for t in targets):
        return True
    # Bare domain-ish without scheme: example.com / company.ru/path
    if re.search(r"(?<!@)\b[a-z0-9][a-z0-9.-]+\.(ru|com|org|net|io|ai|рф)\b", low):
        if any(v in low for v in ("сайт", "открой", "зайди", "посмотри", "изучи", "проскан")):
            return True
    return False


def _summarize_web_dossier(question: str, dossier: str, *, note: str = "") -> str:
    """LLM summary grounded in browsed text; fallback to extract if model unavailable."""
    body = (dossier or "").strip()
    if not body:
        return note or "Не удалось снять текст со страницы (возможна авторизация или блокировка)."
    try:
        from app.services.model_provider import get_model_provider

        provider = get_model_provider()
        system = (
            "Ты Hermes. Тебе дали ДОСЬЕ страниц, которые уже открыл браузер. "
            "Ответь по-русски связно и по делу: чем занимается, продукты/услуги, "
            "аудитория, контакты, ключевые факты. Только факты из досье — "
            "не выдумывай. Если данных мало — скажи честно. "
            "Не упоминай базу знаний tenant, если её не было в досье."
        )
        user = f"Запрос владельца:\n{question}\n\n"
        if note:
            user += f"Замечание браузера: {note}\n\n"
        user += f"Досье:\n{body[:28000]}"
        out = provider.chat_completion(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=1200,
        )
        if out.get("ok"):
            data = out.get("data") if isinstance(out.get("data"), dict) else out
            text = ""
            try:
                text = str(data["choices"][0]["message"]["content"] or "")
            except Exception:  # noqa: BLE001
                text = str(out.get("reply") or out.get("content") or "")
            text = (text or "").strip()
            if text:
                return text
    except Exception:  # noqa: BLE001
        pass
    preview = body[:3500].strip()
    head = "Открыл страницы в браузере. Краткое содержимое:\n\n"
    if note:
        head = f"{note}\n\n" + head
    return head + preview


def _wants_mail_draft(message: str) -> bool:
    """«отправь письмо / черновик» with a clear recipient — DIY send_mail_draft."""
    low = (message or "").lower()
    import re

    has_addr = bool(re.search(r"[\w.+-]+@[\w.-]+\.\w+", message or ""))
    has_mail = any(
        m in low
        for m in (
            "письм",
            "email",
            "e-mail",
            "черновик письм",
            "send_mail",
            "отправь на",
        )
    )
    has_send = any(
        m in low
        for m in (
            "отправь",
            "отправ",
            "написать",
            "напиши",
            "send ",
            "черновик",
        )
    )
    return has_addr and has_mail and has_send


def _mail_draft_fields(message: str) -> dict[str, str]:
    import re

    text = message or ""
    addr_m = re.search(r"([\w.+-]+@[\w.-]+\.\w+)", text)
    to = addr_m.group(1) if addr_m else ""
    subj = ""
    body = ""
    sm = re.search(r"тем[ае]\s+(.+?)(?:\s+тел[оа]\b|$)", text, re.I)
    if sm:
        subj = sm.group(1).strip(" .,\"'«»")[:200]
    bm = re.search(r"тел[оа]\s+(.+)$", text, re.I)
    if bm:
        body = bm.group(1).strip()[:4000]
    if not subj:
        subj = "Сообщение от Hermes"
    if not body:
        body = text.strip()[:2000] or "—"
    return {"to": to, "subject": subj, "body": body}


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
    # Messenger steps (telegram/max) use the dual-path chooser DIY, not the vault yet.
    progress_kind = _form_kind_for_setup_next(setup_next_id, setup_substep)
    if progress_kind and _asks_setup_progress(low):
        if progress_kind in ("telegram_bot", "max_bot"):
            return None
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
    # Do NOT use bare «подключ» — it matches status «подключены».
    connectish = any(
        m in low
        for m in (
            "подключи",
            "подключить",
            "подключим",
            "подключение",
            "настрой",
            "настроить",
            "открой",
            "пришли",
            "токен",
            "botfather",
            "подключить:",
            "настроить:",
        )
    )
    # Telegram / MAX: vault form only after bot-path choice (or explicit open_form).
    # Bare «подключи телеграм» → channel chooser DIY (pros/cons), not the token form.
    from app.services.channel_chooser import explicit_bot_form_kind

    bot_kind = explicit_bot_form_kind(message)
    if bot_kind:
        return bot_kind
    # Legacy: open_form kind name spoken aloud.
    if "telegram_bot" in low or "форму telegram" in low:
        return "telegram_bot"
    if "max_bot" in low or "форму max" in low:
        return "max_bot"
    # Status inventory («какие облака подключены») → DIY, never vault form —
    # even when setup_next is still files.
    if _wants_files_cloud_status(message):
        return None
    # Files / cloud disks — connect intent opens vault even after setup_complete
    # (conduct phase still needs CredentialFormCard; Nous cannot show it).
    cloudish = any(
        m in low
        for m in (
            "файл",
            "диск",
            "yadisk",
            "яндекс",
            "облак",
            "mail.ru",
            "gdrive",
            "onedrive",
            "google",
            "гугл",
            "drive",
        )
    )
    if (connectish or setup_next_id == "files") and cloudish:
        if "mail.ru" in low or "mailru" in low:
            return "files_mailru"
        if "gdrive" in low or "google" in low or "гугл" in low:
            return "files_gdrive"
        if "onedrive" in low:
            return "files_onedrive"
        return "files_yadisk"
    return None


def _finish_diy(
    db: Session,
    ctx: TenantContext,
    body: OperatorChatRequest,
    *,
    modality: str,
    engine: str,
    reply: str,
    tool_calls: list | None = None,
    pending_credential_form: dict | None = None,
    suggested_actions: list | None = None,
    pending_channel_chooser: dict | None = None,
    office_loop: dict | None = None,
    hermes_run: dict | None = None,
    pending_download: dict | None = None,
    extra: dict | None = None,
) -> dict:
    """Persist DIY/Nous turn into conversation history, then return cabinet payload."""
    from app.operator.agent import persist_operator_exchange

    calls = list(tool_calls or [])
    actions = list(suggested_actions or [])
    meta: dict = {"engine": engine, "tool_calls": calls}
    if actions:
        meta["suggested_actions"] = actions
    if pending_credential_form:
        meta["pending_credential_form"] = {
            "kind": pending_credential_form.get("kind"),
            "title": pending_credential_form.get("title"),
        }
    if pending_download:
        meta["pending_download"] = {
            "filename": pending_download.get("filename"),
            "title": pending_download.get("title"),
        }
    conv_id = persist_operator_exchange(
        db,
        ctx,
        message=body.message or "",
        reply=reply or "",
        channel=body.channel or "web",
        conversation_id=body.conversation_id,
        input_modality=modality,
        assistant_meta=meta,
    )
    out: dict = {
        "ok": True,
        "engine": engine,
        "channel": body.channel,
        "conversation_id": conv_id,
        "reply": reply,
        "tool_calls": calls,
        "modality": modality,
        "sources": [],
        "pending_confirmation": None,
    }
    if pending_credential_form is not None:
        out["pending_credential_form"] = pending_credential_form
    if actions:
        out["suggested_actions"] = actions
    if pending_channel_chooser is not None:
        out["pending_channel_chooser"] = pending_channel_chooser
    if office_loop is not None:
        out["office_loop"] = office_loop
    if hermes_run is not None:
        out["hermes_run"] = hermes_run
    if pending_download is not None:
        out["pending_download"] = pending_download
    if extra:
        out.update(extra)
    return out


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

    # Compound / multi-step goals → agent loop (Nous or DIY LLM), not a single shortcut.
    agent_mode = _wants_agent_orchestration(message)

    # Attachments + clear single-intent shortcuts stay on DIY — unless agent_mode.
    prefer_diy = (not agent_mode) and (
        bool(attachments)
        or _wants_media_generation(message)
        or _wants_calendar_slots(message)
        or _wants_conference_create(message)
        or _wants_mail_draft(message)
        or _wants_office_health(message)
        or _wants_crm_funnel(message)
        or _wants_phones_list(message)
        or _wants_calls_list(message)
        or _wants_telephony_script(message)
        or _wants_billing_summary(message)
        or _wants_get_knowledge(message)
        or _wants_hermes_capabilities(message)
        or _wants_files_cloud_status(message)
        or _wants_channel_connect_flow(message)
        or _wants_web_research(message)
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

    # Telegram / MAX: chooser → bot steps / QR before vault form.
    # Do NOT steal general «настрой офис / план по шагам» just because setup_next is telegram.
    if (
        not attachments
        and not agent_mode
        and (_wants_channel_connect_flow(message) or setup_next_id in ("telegram", "max"))
    ):
        from app.services import channel_chooser, channel_qr
        from app.operator.tools import register_builtin_tools
        from app.operator.tools.registry import ToolResult, registry

        channel = channel_chooser.wants_channel_connect_intent(message)
        if channel is None and setup_next_id in ("telegram", "max"):
            low_msg = (message or "").lower()
            channel_named = any(
                m in low_msg for m in ("телеграм", "telegram", "тг", "макс", "max", "канал")
            )
            # Only steal for explicit channel connect — not bare «настрой офис».
            if channel_named and (
                _asks_setup_progress(low_msg)
                or channel_chooser.wants_bot_path(message)
                or channel_chooser.wants_qr_path(message)
                or channel_chooser.wants_bot_help(message)
                or any(
                    m in low_msg
                    for m in ("подключи", "подключить", "настрой телеграм", "настроить телеграм", "настрой max", "настроить max")
                )
            ):
                channel = "telegram" if setup_next_id == "telegram" else "max"
        if channel:
            # Explicit bot / help → form (+ steps). QR → start session. Else chooser.
            if channel_chooser.wants_qr_path(message) and not channel_chooser.wants_bot_path(message):
                channel_chooser.cancel_stale_pending_qr(db, ctx, channel)
                qr_start = channel_qr.start_qr_login(db, ctx, channel_type=channel)
                blob = channel_chooser.qr_path_reply(channel, qr_start=qr_start)
                tool_calls = [
                    {
                        "tool": "channels.qr.start",
                        "ok": bool(qr_start.get("ok")),
                        "channel": channel,
                        "account_id": qr_start.get("account_id"),
                    }
                ]
                form = None
                fallback = blob.get("fallback_form_kind")
                if fallback:
                    register_builtin_tools()
                    form_res = registry.run(db, ctx, "credentials.open_form", kind=fallback)
                    if isinstance(form_res, ToolResult) and form_res.ok:
                        form = (form_res.data or {}).get("pending_credential_form")
                        tool_calls.append(
                            {"tool": "credentials.open_form", "ok": True, "kind": fallback}
                        )
                return _finish_diy(
                    db,
                    ctx,
                    body,
                    modality=modality,
                    engine="diy_channel_qr",
                    reply=blob["reply"],
                    tool_calls=tool_calls,
                    pending_credential_form=form if isinstance(form, dict) else None,
                    suggested_actions=blob.get("suggested_actions") or [],
                    office_loop=loop_preview,
                )

            if channel_chooser.wants_bot_path(message) or channel_chooser.wants_bot_help(message):
                channel_chooser.cancel_stale_pending_qr(db, ctx, channel)
                blob = (
                    channel_chooser.bot_help_reply(channel)
                    if channel_chooser.wants_bot_help(message)
                    else channel_chooser.bot_path_reply(channel)
                )
                register_builtin_tools()
                form_kind_bot = str(blob["form_kind"])
                form_res = registry.run(db, ctx, "credentials.open_form", kind=form_kind_bot)
                form = None
                if isinstance(form_res, ToolResult) and form_res.ok:
                    form = (form_res.data or {}).get("pending_credential_form")
                return _finish_diy(
                    db,
                    ctx,
                    body,
                    modality=modality,
                    engine="diy_channel_bot_path",
                    reply=blob["reply"],
                    tool_calls=[
                        {
                            "tool": "credentials.open_form",
                            "ok": isinstance(form_res, ToolResult) and bool(form_res.ok),
                            "kind": form_kind_bot,
                        }
                    ],
                    pending_credential_form=form if isinstance(form, dict) else None,
                    suggested_actions=blob.get("suggested_actions") or [],
                    pending_channel_chooser={"channel": channel, "mode": "bot"},
                    office_loop=loop_preview,
                )

            # Generic connect → ask which mode.
            blob = channel_chooser.chooser_reply(channel)
            return _finish_diy(
                db,
                ctx,
                body,
                modality=modality,
                engine="diy_channel_chooser",
                reply=blob["reply"],
                tool_calls=[{"tool": "channel.chooser", "ok": True, "channel": channel}],
                suggested_actions=blob.get("suggested_actions") or [],
                pending_channel_chooser=blob.get("pending_channel_chooser"),
                office_loop=loop_preview,
            )

    form_kind = _credential_form_kind_from_message(
        message, setup_next_id=setup_next_id, setup_substep=setup_substep
    )
    if form_kind and not attachments and not agent_mode:
        from app.operator.tools import register_builtin_tools
        from app.operator.tools.registry import ToolResult, registry

        register_builtin_tools()
        result = registry.run(db, ctx, "credentials.open_form", kind=form_kind)
        if isinstance(result, ToolResult) and result.ok:
            form = (result.data or {}).get("pending_credential_form")
            return _finish_diy(
                db,
                ctx,
                body,
                modality=modality,
                engine="diy_credential_form",
                reply=result.message
                or "Открыл безопасную форму. Секрет не пишите в чат — только в форме.",
                tool_calls=[{"tool": "credentials.open_form", "ok": True, "kind": form_kind}],
                pending_credential_form=form if isinstance(form, dict) else None,
                office_loop=loop_preview,
            )

    # Fast-path: pasted URL / «зайди на сайт» → real browser research (not KB).
    # Skip when agent_mode — the agent must plan browse → KB → next tools itself.
    if _wants_web_research(message) and not attachments and not agent_mode:
        from app.operator.tools import register_builtin_tools
        from app.operator.tools.registry import ToolResult, registry
        from app.services import web_browser

        register_builtin_tools()
        urls = _extract_http_urls(message)
        if not urls:
            # Bare domain in text
            m_dom = re.search(
                r"(?<!@)\b([a-z0-9][a-z0-9.-]+\.(?:ru|com|org|net|io|ai))\b",
                message,
                flags=re.I,
            )
            if m_dom:
                urls = [f"https://{m_dom.group(1)}"]
        if urls:
            primary = urls[0]
            result = registry.run(
                db, ctx, "web.research", url=primary, max_pages=5, also_search=True
            )
            if isinstance(result, ToolResult) and result.ok:
                data = result.data or {}
                reply = _summarize_web_dossier(
                    message,
                    str(data.get("dossier") or ""),
                    note=str(data.get("note") or ""),
                )
                pages = data.get("pages") or []
                page_bits = " · ".join(
                    f"{p.get('title') or p.get('url')}" for p in pages[:4] if isinstance(p, dict)
                )
                if page_bits:
                    reply = f"Зашёл в браузере: {page_bits}\n\n{reply}"
                trace = data.get("tool_trace") or [{"tool": "web.research", "ok": True, "url": primary}]
                return _finish_diy(
                    db,
                    ctx,
                    body,
                    modality=modality,
                    engine="diy_web_research",
                    reply=reply,
                    tool_calls=trace if isinstance(trace, list) else [{"tool": "web.research", "ok": True}],
                )
            # If research tool failed, try a single browse then search.
            browsed = web_browser.browse_page(primary)
            calls = [
                {
                    "tool": "web.browse",
                    "ok": bool(browsed.get("ok")),
                    "url": browsed.get("url") or primary,
                    "title": browsed.get("title") or "",
                    "engine": browsed.get("engine") or "",
                    "chars": browsed.get("chars") or 0,
                }
            ]
            if browsed.get("ok") and browsed.get("text"):
                reply = _summarize_web_dossier(
                    message,
                    f"### {browsed.get('title')}\nURL: {browsed.get('url')}\n{browsed.get('text')}",
                    note=str(browsed.get("playwright_error") or ""),
                )
                return _finish_diy(
                    db,
                    ctx,
                    body,
                    modality=modality,
                    engine="diy_web_research",
                    reply=f"Зашёл на {browsed.get('url')}:\n\n{reply}",
                    tool_calls=calls,
                )
            err = result.message if isinstance(result, ToolResult) else browsed.get("error")
            message = f"{message}\n\n[system: web.research failed: {err}]"
        else:
            # Verb intent without URL — search then browse top hits.
            q = re.sub(
                r"(зайди|открой|посмотри|изучи|просканируй|проанализируй|на сайт|сайт)\s*",
                " ",
                message,
                flags=re.I,
            ).strip() or message
            searched = web_browser.search_web(q, limit=5)
            calls = [
                {
                    "tool": "web.search",
                    "ok": bool(searched.get("ok")),
                    "query": q,
                    "count": len(searched.get("items") or []),
                }
            ]
            items = searched.get("items") or []
            if items:
                top = str(items[0].get("url") or "")
                research = web_browser.research_site(top, max_pages=4, also_search=False)
                calls.extend(research.get("tool_trace") or [])
                if research.get("ok"):
                    reply = _summarize_web_dossier(
                        message,
                        str(research.get("dossier") or ""),
                        note=str(research.get("note") or ""),
                    )
                    return _finish_diy(
                        db,
                        ctx,
                        body,
                        modality=modality,
                        engine="diy_web_research",
                        reply=reply,
                        tool_calls=calls,
                    )
            message = f"{message}\n\n[system: web research — no URL and search empty]"

    # Fast-path: never rely on the LLM to "agree" to draw — call generate_image now.
    if _wants_media_generation(message) and not attachments and not agent_mode:
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
            return _finish_diy(
                db,
                ctx,
                body,
                modality=modality,
                engine="diy_generate_image",
                reply=f"{caption}\n\n{md}".strip() if md else caption,
                tool_calls=[{"tool": "generate_image", "ok": True, "model": data.get("model")}],
            )
        err = result.message if isinstance(result, ToolResult) else "image_failed"
        # Fall through to DIY LLM with the error context so the owner sees a clear reply.
        message = f"{message}\n\n[system: generate_image failed: {err}]"

    # Conduct fast-path: calendar slots (Nous often fails to call the MCP tool).
    if _wants_calendar_slots(message) and not attachments and not agent_mode:
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
            nested = data.get("data") if isinstance(data.get("data"), dict) else {}
            upstream = data.get("upstream") if isinstance(data.get("upstream"), dict) else {}
            if not upstream and isinstance(nested.get("upstream"), dict):
                upstream = nested["upstream"]
            suggestions = (
                data.get("suggestions")
                or nested.get("suggestions")
                or upstream.get("suggestions")
                or upstream.get("slots")
                or upstream.get("items")
                or []
            )
            if not isinstance(suggestions, list):
                suggestions = []
            lines = []
            for i, slot in enumerate(suggestions[:5], 1):
                if isinstance(slot, dict):
                    label = (
                        slot.get("label")
                        or slot.get("start")
                        or slot.get("when")
                        or slot.get("datetime")
                        or str(slot)
                    )
                else:
                    label = str(slot)
                lines.append(f"{i}. {label}")
            body_txt = "\n".join(lines) if lines else (result.message or "Слоты получены.")
            stub = bool(
                data.get("stub")
                or nested.get("stub")
                or upstream.get("stub")
                or any(isinstance(s, dict) and s.get("stub") for s in suggestions)
            )
            note = " (черновик/stub — CalDAV ещё без живых кредов)" if stub else ""
            return _finish_diy(
                db,
                ctx,
                body,
                modality=modality,
                engine="diy_calendar_slots",
                reply=f"Варианты слотов на {start} · {duration} мин{note}:\n{body_txt}",
                tool_calls=[
                    {
                        "tool": "suggest_calendar_slots",
                        "ok": True,
                        "start": start,
                        "duration_min": duration,
                        "stub": stub,
                    }
                ],
            )
        err = result.message if isinstance(result, ToolResult) else "calendar_failed"
        message = f"{message}\n\n[system: suggest_calendar_slots failed: {err}]"

    # Conduct fast-path: create conference (Nous often asks for Telemost login instead of tool).
    if _wants_conference_create(message) and not attachments and not agent_mode:
        from app.operator.tools import register_builtin_tools
        from app.operator.tools.registry import ToolResult, registry

        register_builtin_tools()
        title = _conference_title(message)
        provider = _conference_provider(message)
        when_text = message.strip()[:240]
        result = registry.run(
            db,
            ctx,
            "create_conference",
            title=title,
            provider=provider,
            when_text=when_text,
        )
        if isinstance(result, ToolResult) and result.ok:
            data = result.data or {}
            nested = data.get("data") if isinstance(data.get("data"), dict) else {}
            upstream = data.get("upstream") if isinstance(data.get("upstream"), dict) else {}
            if not upstream and isinstance(nested.get("upstream"), dict):
                upstream = nested["upstream"]
            join_url = (
                data.get("join_url")
                or nested.get("join_url")
                or upstream.get("join_url")
                or upstream.get("url")
            )
            stub = bool(data.get("stub") or nested.get("stub") or upstream.get("stub"))
            note = " (stub — provider без живых кредов)" if stub else ""
            link = f"\nСсылка: {join_url}" if join_url else ""
            return _finish_diy(
                db,
                ctx,
                body,
                modality=modality,
                engine="diy_create_conference",
                reply=(
                    f"Создал конференцию «{title}» ({provider}){note}.{link}\n"
                    f"{result.message or ''}"
                ).strip(),
                tool_calls=[
                    {
                        "tool": "create_conference",
                        "ok": True,
                        "title": title,
                        "provider": provider,
                        "stub": stub,
                        "join_url": join_url,
                    }
                ],
            )
        err = result.message if isinstance(result, ToolResult) else "conference_failed"
        message = f"{message}\n\n[system: create_conference failed: {err}]"

    # Conduct fast-path: mail draft (Nous often claims send_mail_draft unavailable).
    if _wants_mail_draft(message) and not attachments and not agent_mode:
        from app.operator.tools import register_builtin_tools
        from app.operator.tools.registry import ToolResult, registry

        register_builtin_tools()
        fields = _mail_draft_fields(message)
        result = registry.run(
            db,
            ctx,
            "send_mail_draft",
            to=fields["to"],
            subject=fields["subject"],
            body=fields["body"],
        )
        if isinstance(result, ToolResult) and result.ok:
            data = result.data or {}
            nested = data.get("data") if isinstance(data.get("data"), dict) else {}
            stub = bool(data.get("stub") or nested.get("stub") or not data.get("configured", True))
            note = " (stub/dry-run — SMTP ещё без живых кредов)" if stub else ""
            return _finish_diy(
                db,
                ctx,
                body,
                modality=modality,
                engine="diy_send_mail_draft",
                reply=(
                    f"Черновик письма{note}:\n"
                    f"Кому: {fields['to']}\n"
                    f"Тема: {fields['subject']}\n"
                    f"Текст: {fields['body'][:400]}\n"
                    f"{result.message or ''}"
                ).strip(),
                tool_calls=[
                    {
                        "tool": "send_mail_draft",
                        "ok": True,
                        "to": fields["to"],
                        "stub": stub,
                    }
                ],
            )
        err = result.message if isinstance(result, ToolResult) else "mail_failed"
        message = f"{message}\n\n[system: send_mail_draft failed: {err}]"

    # Conduct fast-path: office health (Nous invents missing office.health).
    if _wants_office_health(message) and not attachments and not agent_mode:
        from app.operator.tools import register_builtin_tools
        from app.operator.tools.registry import ToolResult, registry

        register_builtin_tools()
        result = registry.run(db, ctx, "hermes.health")
        if isinstance(result, ToolResult) and result.ok:
            data = result.data or {}
            healthy = bool(data.get("healthy"))
            alerts = data.get("alerts") or []
            alert_lines = []
            for a in alerts[:5]:
                if isinstance(a, dict):
                    alert_lines.append(
                        f"- {a.get('code') or 'alert'}: {a.get('message_ru') or a.get('message') or ''}"
                    )
            body_txt = "\n".join(alert_lines) if alert_lines else "Алертов нет."
            return _finish_diy(
                db,
                ctx,
                body,
                modality=modality,
                engine="diy_hermes_health",
                reply=(
                    f"{'Офис в норме.' if healthy else 'Есть проблемы по офису.'}\n"
                    f"{data.get('message_ru') or result.message or ''}\n{body_txt}"
                ).strip(),
                tool_calls=[{"tool": "hermes.health", "ok": True, "healthy": healthy}],
            )
        err = result.message if isinstance(result, ToolResult) else "health_failed"
        message = f"{message}\n\n[system: hermes.health failed: {err}]"

    if _wants_crm_funnel(message) and not attachments and not agent_mode:
        from app.operator.tools import register_builtin_tools
        from app.operator.tools.registry import ToolResult, registry

        register_builtin_tools()
        result = registry.run(db, ctx, "crm.funnel")
        if isinstance(result, ToolResult) and result.ok:
            data = result.data or {}
            stages = data.get("stages") or data.get("funnel") or data.get("items") or []
            lines = []
            if isinstance(stages, dict):
                for k, v in stages.items():
                    lines.append(f"- {k}: {v}")
            elif isinstance(stages, list):
                for s in stages[:12]:
                    if isinstance(s, dict):
                        lines.append(
                            f"- {s.get('stage') or s.get('name') or s}: "
                            f"{s.get('count') if 'count' in s else s.get('leads') or s}"
                        )
                    else:
                        lines.append(f"- {s}")
            if not lines:
                import json as _json

                body_txt = _json.dumps(data, ensure_ascii=False)[:800]
            else:
                body_txt = "\n".join(lines)
            return _finish_diy(
                db,
                ctx,
                body,
                modality=modality,
                engine="diy_crm_funnel",
                reply=f"CRM воронка:\n{body_txt}\n{result.message or ''}".strip(),
                tool_calls=[{"tool": "crm.funnel", "ok": True}],
            )
        err = result.message if isinstance(result, ToolResult) else "crm_failed"
        message = f"{message}\n\n[system: crm.funnel failed: {err}]"

    if _wants_phones_list(message) and not attachments and not agent_mode:
        from app.operator.tools import register_builtin_tools
        from app.operator.tools.registry import ToolResult, registry

        register_builtin_tools()
        result = registry.run(db, ctx, "phones.list")
        if isinstance(result, ToolResult) and result.ok:
            data = result.data or {}
            items = data.get("items") or data.get("phones") or data.get("numbers") or []
            if isinstance(data, list):
                items = data
            lines = []
            for p in items[:20] if isinstance(items, list) else []:
                if isinstance(p, dict):
                    lines.append(
                        f"- {p.get('e164') or p.get('number') or p}: "
                        f"{p.get('status') or '—'} ({p.get('label') or 'did'})"
                    )
                else:
                    lines.append(f"- {p}")
            body_txt = "\n".join(lines) if lines else "Активных DID пока нет."
            return _finish_diy(
                db,
                ctx,
                body,
                modality=modality,
                engine="diy_phones_list",
                reply=f"Телефонные номера:\n{body_txt}\n{result.message or ''}".strip(),
                tool_calls=[{"tool": "phones.list", "ok": True, "count": len(lines)}],
            )
        err = result.message if isinstance(result, ToolResult) else "phones_failed"
        message = f"{message}\n\n[system: phones.list failed: {err}]"

    if _wants_calls_list(message) and not attachments and not agent_mode:
        from app.operator.tools import register_builtin_tools
        from app.operator.tools.registry import ToolResult, registry

        register_builtin_tools()
        result = registry.run(db, ctx, "calls.list", limit=20)
        if isinstance(result, ToolResult) and result.ok:
            data = result.data or {}
            items = data.get("items") if isinstance(data, dict) else data
            lines = []
            for c in items[:20] if isinstance(items, list) else []:
                if not isinstance(c, dict):
                    lines.append(f"- {c}")
                    continue
                direction = c.get("direction") or "?"
                status = c.get("status") or "—"
                peer = c.get("to_e164") or c.get("from_e164") or c.get("did_e164") or "—"
                when = (c.get("started_at") or c.get("created_at") or "")[:19]
                outcome = c.get("outcome") or ""
                extra = f" / {outcome}" if outcome else ""
                lines.append(f"- {when} {direction} {peer}: {status}{extra}")
            body_txt = "\n".join(lines) if lines else "Звонков пока нет."
            return _finish_diy(
                db,
                ctx,
                body,
                modality=modality,
                engine="diy_calls_list",
                reply=f"Последние звонки:\n{body_txt}\n{result.message or ''}".strip(),
                tool_calls=[
                    {
                        "tool": "calls.list",
                        "ok": True,
                        "count": len(lines),
                    }
                ],
            )
        err = result.message if isinstance(result, ToolResult) else "calls_failed"
        message = f"{message}\n\n[system: calls.list failed: {err}]"

    if _wants_telephony_script(message) and not attachments and not agent_mode:
        from app.operator.tools import register_builtin_tools
        from app.operator.tools.registry import ToolResult, registry

        register_builtin_tools()
        if _telephony_script_wants_save(message):
            tool_name = "telephony.script_save"
        elif _telephony_script_wants_propose(message):
            tool_name = "telephony.script_propose"
        else:
            tool_name = "telephony.script_get"
        result = registry.run(db, ctx, tool_name)
        if isinstance(result, ToolResult) and result.ok:
            data = result.data or {}
            if tool_name == "telephony.script_propose":
                draft = str(data.get("draft") or "")[:3500]
                reply = (result.message or "Черновик сценария готов.").strip()
                if draft and draft not in reply:
                    reply = f"{reply}\n\n{draft}".strip()
            elif tool_name == "telephony.script_save":
                reply = (result.message or data.get("message_ru") or "Сценарий сохранён.").strip()
            else:
                script = str(
                    data.get("script")
                    or data.get("body")
                    or (data.get("telephony") or {}).get("script")
                    or ""
                )[:3500]
                configured = bool(data.get("configured"))
                head = result.message or (
                    "Сценарий сохранён." if configured else "Сценария ещё нет."
                )
                reply = f"{head}\n\n{script}".strip() if script else str(head)
            return _finish_diy(
                db,
                ctx,
                body,
                modality=modality,
                engine="diy_telephony_script",
                reply=reply,
                tool_calls=[{"tool": tool_name, "ok": True}],
            )
        err = result.message if isinstance(result, ToolResult) else "script_failed"
        message = f"{message}\n\n[system: {tool_name} failed: {err}]"

    if _wants_billing_summary(message) and not attachments and not agent_mode:
        from app.operator.tools import register_builtin_tools
        from app.operator.tools.registry import ToolResult, registry

        register_builtin_tools()
        result = registry.run(db, ctx, "billing.summary")
        if isinstance(result, ToolResult) and result.ok:
            data = result.data or {}
            reply = (
                result.message
                or data.get("message_ru")
                or (
                    f"Баланс: {data.get('balance') if 'balance' in data else data.get('tokens_remaining', '—')}\n"
                    f"Тариф: {data.get('tariff') or data.get('rub_per_1k') or '—'}"
                )
            )
            return _finish_diy(
                db,
                ctx,
                body,
                modality=modality,
                engine="diy_billing_summary",
                reply=str(reply).strip(),
                tool_calls=[{"tool": "billing.summary", "ok": True}],
            )
        err = result.message if isinstance(result, ToolResult) else "billing_failed"
        message = f"{message}\n\n[system: billing.summary failed: {err}]"

    if _wants_get_knowledge(message) and not attachments and not agent_mode:
        from app.operator.tools import register_builtin_tools
        from app.operator.tools.registry import ToolResult, registry

        register_builtin_tools()
        # Prefer an explicit query after «про/о»; else whole message.
        import re

        q = message
        m = re.search(r"(?:про|о|about|query\s*=\s*)\s+(.+)$", message or "", re.I)
        if m:
            q = m.group(1).strip(" .,\"'«»")[:400] or message
        result = registry.run(db, ctx, "get_knowledge", query=q[:400] or "компания")
        if isinstance(result, ToolResult) and result.ok:
            data = result.data or {}
            # KnowledgeAdapter returns matches[] + aggregated text (not snippets/hits).
            matches = data.get("matches") or data.get("results") or data.get("hits") or []
            lines = []
            if isinstance(matches, list):
                for s in matches[:5]:
                    if isinstance(s, dict):
                        lines.append(
                            f"- {s.get('title') or s.get('source') or 'doc'}: "
                            f"{(s.get('snippet') or s.get('text') or s.get('body') or '')[:280]}"
                        )
                    else:
                        lines.append(f"- {str(s)[:280]}")
            body_txt = "\n".join(lines) if lines else (
                str(data.get("text") or result.message or "")[:1200] or "Пусто."
            )
            return _finish_diy(
                db,
                ctx,
                body,
                modality=modality,
                engine="diy_get_knowledge",
                reply=f"Из базы знаний:\n{body_txt}".strip(),
                tool_calls=[
                    {
                        "tool": "get_knowledge",
                        "ok": True,
                        "query": q[:120],
                        "hits": len(matches) if isinstance(matches, list) else 0,
                    }
                ],
            )
        err = result.message if isinstance(result, ToolResult) else "kb_failed"
        message = f"{message}\n\n[system: get_knowledge failed: {err}]"

    if _wants_hermes_capabilities(message) and not attachments and not agent_mode:
        from app.operator.tools import register_builtin_tools
        from app.operator.tools.registry import ToolResult, registry

        register_builtin_tools()
        result = registry.run(db, ctx, "hermes.capabilities")
        if isinstance(result, ToolResult) and result.ok:
            data = result.data or {}
            connectors = data.get("connectors") or []
            lines = []
            if isinstance(connectors, list):
                for c in connectors[:12]:
                    if not isinstance(c, dict):
                        continue
                    usable = c.get("usable")
                    ready = c.get("ready") if "ready" in c else usable
                    flag = "ok" if ready or usable else "нет"
                    lines.append(
                        f"- {c.get('kind') or c.get('label') or '?'}: {flag}"
                        + (f" — {c.get('detail') or c.get('message') or ''}" if c.get("detail") or c.get("message") else "")
                    )
            missing = data.get("missing") or []
            miss_txt = ", ".join(str(m) for m in missing) if missing else "нет"
            body_txt = "\n".join(lines) if lines else (result.message or "—")
            return _finish_diy(
                db,
                ctx,
                body,
                modality=modality,
                engine="diy_hermes_capabilities",
                reply=(
                    f"Готовность коннекторов:\n{body_txt}\n"
                    f"Требуют настройки: {miss_txt}\n"
                    f"{result.message or ''}"
                ).strip(),
                tool_calls=[{"tool": "hermes.capabilities", "ok": True}],
            )
        err = result.message if isinstance(result, ToolResult) else "capabilities_failed"
        message = f"{message}\n\n[system: hermes.capabilities failed: {err}]"

    if _wants_files_cloud_status(message) and not attachments and not agent_mode:
        from app.operator.tools import register_builtin_tools
        from app.operator.tools.registry import ToolResult, registry

        register_builtin_tools()
        result = registry.run(db, ctx, "files.cloud_status")
        if isinstance(result, ToolResult) and result.ok:
            # Tool message already lists each cloud; prefer it over re-formatting.
            reply = (result.message or "").strip() or "Облака не настроены."
            return _finish_diy(
                db,
                ctx,
                body,
                modality=modality,
                engine="diy_files_cloud_status",
                reply=reply,
                tool_calls=[{"tool": "files.cloud_status", "ok": True}],
            )
        err = result.message if isinstance(result, ToolResult) else "files_cloud_failed"
        message = f"{message}\n\n[system: files.cloud_status failed: {err}]"

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
                reply = (
                    nous.get("output")
                    or (nous.get("hermes") or {}).get("output")
                    or "Hermes run started — progress via /v1/hermes-nous/runs/{run_id}."
                )
                if agent_mode and reply and not str(reply).lstrip().startswith(("1.", "1)", "План", "Шаг")):
                    # Keep UI honest: agent was asked to plan; prefix if runtime omitted it.
                    reply = f"План выполнен агентом (режим {pack_mode}).\n\n{reply}"
                return _finish_diy(
                    db,
                    ctx,
                    body,
                    modality=modality,
                    engine="nous_hermes_agent",
                    reply=reply,
                    tool_calls=_tool_calls_from_nous(nous),
                    hermes_run=nous,
                )
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
