from fastapi import FastAPI, Request, Header, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from fastapi.exceptions import RequestValidationError
from dotenv import load_dotenv
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from openai import OpenAI
import smtplib
import os
import json
import re
import urllib.error
import urllib.request
from typing import Optional, Tuple
from datetime import timedelta

import pytz
from dateutil import parser as dtparser
import caldav
from icalendar import Calendar, Event
from pydantic import BaseModel
import logging

# --------------------
# ENV (must load before yandex_oauth reads os.environ)
# --------------------
load_dotenv("/opt/ava-mailer/.env")

import yandex_oauth

# --------------------
# ENV
# --------------------

app = FastAPI(title="AVA Mailer")

logger = logging.getLogger("uvicorn.error")

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    body = await request.body()
    logger.error(
        "[VALIDATION ERROR] %s BODY=%s ERRORS=%s",
        request.url.path,
        body.decode("utf-8", errors="replace"),
        exc.errors(),
    )
    return JSONResponse(
        status_code=422,
        content={
            "detail": exc.errors(),
            "message": "Ошибка в данных запроса"
        },
    )

@app.middleware("http")
async def log_calendar_requests(request: Request, call_next):
    """Логируем календарные запросы и возвращаем body обратно в request."""
    if not request.url.path.startswith("/api/calendar"):
        return await call_next(request)

    body = await request.body()
    logger.error(
        "[CALENDAR REQUEST] %s BODY=%s",
        request.url.path,
        body.decode("utf-8", errors="replace"),
    )

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    request = Request(request.scope, receive)
    response = await call_next(request)

    logger.error(
        "[CALENDAR RESPONSE] %s STATUS=%s",
        request.url.path,
        response.status_code,
    )
    return response

WEBHOOK_TOKEN = os.getenv("WEBHOOK_TOKEN", "")
LOG_FILE = "/opt/ava-mailer/webhook.log"


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default

SMTP_HOST = os.getenv("MAIL_SMTP_HOST")
SMTP_PORT = int(os.getenv("MAIL_SMTP_PORT", "465"))
SMTP_USER = os.getenv("MAIL_USERNAME")
SMTP_PASS = os.getenv("MAIL_PASSWORD")
MAIL_TO_DEFAULT = os.getenv("MAIL_TO_DEFAULT")
SMTP_TIMEOUT_SECONDS = _env_float("MAIL_SMTP_TIMEOUT_SECONDS", 6.0)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_TIMEOUT_SECONDS = _env_float("OPENAI_TIMEOUT_SECONDS", 25.0)

client = OpenAI(api_key=OPENAI_API_KEY, timeout=OPENAI_TIMEOUT_SECONDS)

#календарь
MAILRU_CALDAV_URL = os.getenv("MAILRU_CALDAV_URL", "https://calendar.mail.ru")
MAILRU_CALDAV_USERNAME = os.getenv("MAILRU_CALDAV_USERNAME", "")
MAILRU_CALDAV_PASSWORD = os.getenv("MAILRU_CALDAV_PASSWORD", "")
MAILRU_CALENDAR_URL = os.getenv("MAILRU_CALENDAR_URL", "").strip()
CALENDAR_DEFAULT_DURATION_MIN = int(os.getenv("CALENDAR_DEFAULT_DURATION_MIN", "30"))
CALENDAR_TIMEZONE = os.getenv("CALENDAR_TIMEZONE", "Europe/Moscow")

YANDEX_TELEMOST_OAUTH_TOKEN = os.getenv("YANDEX_TELEMOST_OAUTH_TOKEN", "").strip()
TELEMOST_ENABLED = os.getenv("TELEMOST_ENABLED", "true").lower() in ("1", "true", "yes", "on")
TELEMOST_WAITING_ROOM_LEVEL = os.getenv("TELEMOST_WAITING_ROOM_LEVEL", "PUBLIC").strip() or "PUBLIC"
TELEMOST_REQUIRED = os.getenv("TELEMOST_REQUIRED", "false").lower() in ("1", "true", "yes", "on")
TELEMOST_API_URL = os.getenv(
    "TELEMOST_API_URL",
    "https://cloud-api.yandex.net/v1/telemost-api/conferences",
).strip()
TELEMOST_TIMEOUT_SECONDS = _env_float("TELEMOST_TIMEOUT_SECONDS", 6.0)

WELCOME_EMAIL_ENABLED = os.getenv("WELCOME_EMAIL_ENABLED", "true").lower() in (
    "1", "true", "yes", "on",
)
WELCOME_PDF_PATH = os.getenv(
    "WELCOME_PDF_PATH",
    "/opt/ava-mailer/assets/quantum-labs-presentation.pdf",
).strip()
WELCOME_COMPANY_NAME = os.getenv("WELCOME_COMPANY_NAME", "Quantum Labs").strip()
WELCOME_CONTACT_EMAIL = os.getenv("WELCOME_CONTACT_EMAIL", SMTP_USER or "").strip()
WELCOME_CONTACT_PHONE = os.getenv("WELCOME_CONTACT_PHONE", "8 (800) 555-94-18").strip()
WELCOME_CONTACT_WEBSITE = os.getenv("WELCOME_CONTACT_WEBSITE", "https://quantumlabs.ru").strip()
WELCOME_EMAIL_SUBJECT = os.getenv(
    "WELCOME_EMAIL_SUBJECT",
    "Quantum Labs — презентация компании",
).strip()


# --------------------
# LOGGING
# --------------------
def write_log(data: dict):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")

# --------------------
# EMAIL SENDER
# --------------------
def send_email(subject: str, body: str):
    send_email_to(MAIL_TO_DEFAULT, subject, body)


def send_email_to(
    to: str,
    subject: str,
    body: str,
    *,
    reply_to: Optional[str] = None,
    attachments: Optional[list] = None,
) -> None:
    """Send email to a specific recipient; optional PDF attachments."""
    msg = MIMEMultipart()
    msg["From"] = SMTP_USER
    msg["To"] = to
    msg["Subject"] = subject
    if reply_to:
        msg["Reply-To"] = reply_to

    msg.attach(MIMEText(body, "plain", "utf-8"))

    for attachment in attachments or []:
        path = attachment.get("path", "")
        filename = attachment.get("filename") or os.path.basename(path)
        if not path or not os.path.isfile(path):
            logger.warning("[WELCOME EMAIL] attachment missing: %s", path)
            continue
        with open(path, "rb") as f:
            payload = f.read()
        subtype = attachment.get("subtype", "octet-stream")
        part = MIMEApplication(payload, _subtype=subtype)
        part.add_header("Content-Disposition", "attachment", filename=filename)
        msg.attach(part)

    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT_SECONDS) as server:
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)


def _extract_client_name(summary: str, description: str) -> str:
    for text in (description, summary):
        match = re.search(r"Имя:\s*(.+)", text, re.IGNORECASE)
        if match:
            name = match.group(1).strip().split("\n", 1)[0].strip()
            if name:
                return name
        match = re.search(r"Созвон с клиентом:\s*(.+)", text, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            if name:
                return name
    return ""


def _build_welcome_email_body(
    client_name: str,
    meeting_start: datetime,
    telemost_join_url: str = "",
) -> str:
    company = WELCOME_COMPANY_NAME or "Quantum Labs"
    contact_email = WELCOME_CONTACT_EMAIL or SMTP_USER or "office@quantumlabs.ru"
    contact_phone = WELCOME_CONTACT_PHONE or "8 (800) 555-94-18"

    greeting = f"Здравствуйте, {client_name}!" if client_name else "Здравствуйте!"

    parts = [
        greeting,
        "",
        f"Спасибо за интерес к услугам {company}!",
        "Мы рады приветствовать вас.",
    ]

    if meeting_start:
        parts.append(
            f"Напоминаем: встреча с нашей командой запланирована на "
            f"{meeting_start.strftime('%d.%m.%Y в %H:%M')} (МСК)."
        )

    if telemost_join_url:
        parts.extend([
            "",
            "Ссылка на видеовстречу в Яндекс.Телемост:",
            telemost_join_url,
        ])

    parts.extend([
        "",
        "К этому письму прикреплена презентация нашей компании (PDF) — в ней кратко "
        "описаны наши возможности и подход к работе.",
        "",
        "Мы всегда будем рады ответить на ваши вопросы — просто ответьте на это письмо "
        "или свяжитесь с нами удобным способом.",
        "",
        "_____",
        "",
        "С уважением,",
        "",
        f'Команда "{company}"',
        "",
        f"email: {contact_email}",
        "",
        f"тел: {contact_phone}",
    ])

    return "\n".join(parts)


def _send_welcome_presentation_email(
    attendee_email: str,
    summary: str,
    description: str,
    meeting_start: datetime,
    telemost_join_url: str = "",
) -> Tuple[bool, bool, str]:
    """
    Send separate welcome email with company presentation PDF.
    Returns: (sent, pdf_attached, error_reason)
    """
    if not WELCOME_EMAIL_ENABLED:
        return False, False, "disabled"
    if not attendee_email:
        return False, False, "no_attendee_email"
    if not all([SMTP_HOST, SMTP_USER, SMTP_PASS]):
        return False, False, "smtp_not_configured"

    client_name = _extract_client_name(summary, description)
    body = _build_welcome_email_body(client_name, meeting_start, telemost_join_url)
    attachments = []
    pdf_attached = False
    if WELCOME_PDF_PATH and os.path.isfile(WELCOME_PDF_PATH):
        attachments.append(
            {
                "path": WELCOME_PDF_PATH,
                "filename": os.path.basename(WELCOME_PDF_PATH),
                "subtype": "pdf",
            }
        )
        pdf_attached = True
    else:
        logger.warning("[WELCOME EMAIL] PDF not found at %s", WELCOME_PDF_PATH)

    try:
        send_email_to(
            attendee_email,
            WELCOME_EMAIL_SUBJECT,
            body,
            reply_to=WELCOME_CONTACT_EMAIL or SMTP_USER,
            attachments=attachments,
        )
        logger.info(
            "[WELCOME EMAIL] sent to=%s pdf_attached=%s",
            attendee_email,
            pdf_attached,
        )
        return True, pdf_attached, ""
    except Exception as e:
        logger.exception("[WELCOME EMAIL] failed to=%s", attendee_email)
        return False, False, str(e)


def _send_welcome_presentation_email_logged(
    attendee_email: str,
    summary: str,
    description: str,
    meeting_start_iso: str,
    telemost_join_url: str = "",
) -> None:
    try:
        meeting_start = datetime.fromisoformat(meeting_start_iso)
    except Exception:
        meeting_start = datetime.now(_tz(CALENDAR_TIMEZONE))

    sent, pdf_attached, error = _send_welcome_presentation_email(
        attendee_email=attendee_email,
        summary=summary,
        description=description,
        meeting_start=meeting_start,
        telemost_join_url=telemost_join_url,
    )
    write_log(
        {
            "status": "welcome_email_sent" if sent else "welcome_email_failed",
            "attendee_email": attendee_email,
            "pdf_attached": pdf_attached,
            "error": error,
        }
    )


# --------------------
# TRANSCRIPT NORMALIZER
# --------------------
def transcript_to_text(transcript):
    if isinstance(transcript, list):
        return "\n".join(
            item.get("content", "") if isinstance(item, dict) else str(item)
            for item in transcript
        )
    return str(transcript)


# --------------------
# GPT EXTRACTOR (КЛЮЧЕВОЕ МЕСТО)
# --------------------
_BAD_NAME_RE = re.compile(
    r"^(алло|денежк|деньги|здравствуйте|слушаю|quantum|квантум)\b",
    re.IGNORECASE,
)


def _sanitize_extracted_name(name: Optional[str]) -> str:
    if not name or not isinstance(name, str):
        return ""
    cleaned = name.strip()
    if not cleaned or _BAD_NAME_RE.search(cleaned):
        return ""
    if "денеж" in cleaned.lower():
        return ""
    return cleaned


def extract_structured_data(text: str, caller_number: str, caller_name: str):

    prompt = f"""
Ты извлекаешь только явно подтвержденные данные из телефонного разговора.

Верни СТРОГО JSON и ничего кроме JSON:

{{
  "name": "",
  "phone": "",
  "email": "",
  "meeting": false,
  "meeting_time": "",
  "company": "",
  "interest": "",
  "summary": ""
}}

Очень важные правила:
1. Не додумывай факты.
2. Заполняй поле только если информация была явно сказана в разговоре.
3. Если данных нет или есть сомнение — ставь пустую строку.
4. Не придумывай детали про комиссии, лимиты, банки, объемы выплат, договоры, интеграции и другие темы, если этого не было в transcript.
5. Если клиент только попросил встречу, то summary должно отражать только это.
6. Email извлекай только если он был явно продиктован.
7. Телефон бери из разговора, если он был явно продиктован. Если не был продиктован, используй caller_number.
8. meeting = true только если клиент явно хочет встречу или согласовал встречу.
9. meeting_time заполняй только тем, что было явно сказано, например: "завтра 15:00".
10. interest должен быть очень кратким и только по фактам из разговора.
11. summary должно быть коротким, 1-3 предложения, строго без выдуманных деталей.
12. company заполняй только если клиент явно назвал компанию.

Дополнительные правила для email:
13. Если собеседник говорит фразы вроде "мой email", "моя почта", "запишите email", "электронная почта", "мой имейл", то следующие продиктованные символы и слова почти наверняка относятся к email.
14. Email всегда возвращай в стандартном ASCII-формате, только латиница, цифры и допустимые символы. Никогда не возвращай email кириллицей.
15. Интерпретируй:
    - "собака" как "@"
    - "точка" как "."
    - "тире" или "дефис" как "-"
    - "нижнее подчеркивание" как "_"
16. Если домен почты продиктован по-русски, переводи его в стандартный латинский домен:
    - "яндекс" -> "yandex.ru"
    - "майл" или "мейл" -> "mail.ru"
    - "bk" -> "bk.ru"
    - "inbox" -> "inbox.ru"
    - "list" -> "list.ru"
    - "gmail", "джимейл", "гугл почта" -> "gmail.com"
    - "icloud" -> "icloud.com"
    - "outlook" -> "outlook.com"
17. Если сказано "яндекс ру", "майл ру", "gmail com" и подобные домены по частям, собирай их в обычный email.
18. Если доменная зона очевидно подразумевается стандартным сервисом, восстанови её:
    - "yandex" -> "yandex.ru"
    - "mail" -> "mail.ru"
    - "gmail" -> "gmail.com"
19. Если email продиктован неполно или слишком неуверенно, верни пустую строку вместо догадки.

Правила для name:
20. Имя заполняй только если в разговоре клиент явно назвал себя и это было подтверждено.
21. Не используй как имя слова, похожие на ошибку распознавания: "денежка", "деньги", "алло", "здравствуйте", "квантум", "лабс", "quantum".
22. Если в transcript клиент говорил "меня зовут Денис" / "я Денис", а в summary фигурирует другое слово — верни "Денис".
23. Если имя неясно или выглядит как мусор STT — оставь name пустым, не выдумывай.

Примеры:
- "мой email 1234 точка 1 собака яндекс ру" -> "1234.1@yandex.ru"
- "моя почта abicmo собака yandex" -> "abicmo@yandex.ru"
- "запишите email test тире sale собака gmail точка com" -> "test-sale@gmail.com"

Метаданные звонка:
caller_name: {caller_name}
caller_number: {caller_number}

Transcript:
{text}
"""

    response = client.responses.create(
        model=os.getenv("OPENAI_MODEL", "gpt-5-mini"),
        input=prompt
    )

    try:
        data = json.loads(response.output_text)
        if isinstance(data, dict):
            data["name"] = _sanitize_extracted_name(data.get("name"))
        return data
    except Exception:
        return {
            "name": _sanitize_extracted_name(caller_name),
            "phone": caller_number,
            "email": "",
            "meeting": False,
            "meeting_time": "",
            "company": "",
            "interest": "",
            "summary": text[:500]
        }


# --------------------
# EMAIL BUILDER
# --------------------
def _normalize_phone_digits(value: str) -> str:
    return re.sub(r"\D", "", str(value or ""))


# Номера/идентификаторы тестов (E2E, smoke) — письма менеджеру не отправляем
_POST_CALL_SKIP_PHONES = {
    _normalize_phone_digits("79990001122"),
    _normalize_phone_digits("79001234567"),
}
_POST_CALL_SKIP_CALLER_IDS = {"tester", "rdv1", "codex-smoke"}


def _transcript_user_turns(payload: dict) -> list:
    transcript = payload.get("transcript")
    if not isinstance(transcript, list):
        return []
    turns = []
    for item in transcript:
        if not isinstance(item, dict):
            continue
        if str(item.get("role") or "").lower() != "user":
            continue
        if str(item.get("content") or "").strip():
            turns.append(item)
    return turns


def _is_outbound_call(payload: dict) -> bool:
    """True for AVA outbound / console dial calls (not inbound default)."""
    from post_call_policy import is_outbound_call

    return is_outbound_call(payload)


def _should_send_lead_email(payload: dict) -> tuple[bool, str]:
    """Return (send, skip_reason). Lead emails are for inbound only."""
    call_id = str(payload.get("call_id") or "").strip()
    if call_id.startswith("codex-smoke"):
        return False, "codex_smoke_test"

    if _is_outbound_call(payload):
        return False, "outbound_no_lead_email"

    caller_raw = str(
        payload.get("caller_number")
        or payload.get("caller")
        or payload.get("phone")
        or ""
    ).strip()
    caller_lower = caller_raw.lower()
    if caller_lower in _POST_CALL_SKIP_CALLER_IDS:
        return False, "internal_test_caller_id"

    phone_digits = _normalize_phone_digits(caller_raw)
    if phone_digits in _POST_CALL_SKIP_PHONES:
        return False, "e2e_test_number"

    # Ручные curl без call_id и без номера
    if not call_id and not phone_digits:
        return False, "empty_call_metadata"

    user_turns = _transcript_user_turns(payload)
    try:
        duration = int(payload.get("call_duration") or 0)
    except (TypeError, ValueError):
        duration = 0

    # Только приветствие ассистента, клиент не говорил — не спамим «лидами»
    if not user_turns and duration < 90:
        return False, "no_user_speech"

    return True, ""


def _booking_fields_from_payload(payload: dict) -> dict:
    """Meeting fields from ai-engine post-call webhook (calendar tool)."""
    telemost = (payload.get("telemost_join_url") or "").strip()
    meeting_display = (payload.get("meeting_time_display") or "").strip()
    meeting_start = (payload.get("meeting_start") or "").strip()
    if not meeting_display and meeting_start:
        meeting_display = meeting_start
    company = (payload.get("meeting_company") or "").strip()
    attendee = (payload.get("attendee_email") or "").strip()
    return {
        "telemost_join_url": telemost,
        "meeting_time_display": meeting_display,
        "meeting_company": company,
        "attendee_email": attendee,
    }


def build_email(data: dict, payload: dict):
    meeting_value = "да" if data.get("meeting") else "нет"
    booking = _booking_fields_from_payload(payload)

    subject_name = data.get("name") or "без имени"
    subject = f"Новый лид: {subject_name}"

    company = (data.get("company") or "").strip() or booking.get("meeting_company") or ""
    email = (data.get("email") or "").strip() or booking.get("attendee_email") or ""
    meeting_when = booking.get("meeting_time_display") or data.get("meeting_time", "") or ""
    telemost = booking.get("telemost_join_url") or ""

    if booking.get("meeting_time_display") or telemost:
        meeting_value = "да"

    body_lines = [
        "НОВЫЙ ЛИД (AVA)",
        "",
        f"Имя: {data.get('name', '')}",
        f"Телефон: {data.get('phone', '')}",
        f"Email: {email}",
    ]
    if company:
        body_lines.append(f"Компания: {company}")
    body_lines.extend(
        [
            "",
            f"Интерес: {data.get('interest', '')}",
            f"Встреча: {meeting_value}",
        ]
    )
    if meeting_when:
        body_lines.append(f"Дата и время встречи: {meeting_when}")
    if telemost:
        body_lines.append(f"Телемост: {telemost}")
    body_lines.extend(
        [
            "",
            "Резюме:",
            data.get("summary", ""),
            "",
            "---",
            "",
            f"Call ID: {payload.get('call_id', '')}",
        ]
    )
    return subject, "\n".join(body_lines)



def _fanout_lead_to_crm(structured: dict, payload: dict) -> None:
    """Push structured lead to ava-outreach → Bitrix (email still sent separately)."""
    url = (os.getenv("OUTREACH_CRM_URL") or "").strip()
    if not url:
        return
    token = (os.getenv("OUTREACH_CRM_TOKEN") or WEBHOOK_TOKEN or "").strip()
    booking = _booking_fields_from_payload(payload)
    meeting = bool(structured.get("meeting"))
    if booking.get("meeting_time_display") or booking.get("telemost_join_url"):
        meeting = True
    body = {
        "call_id": payload.get("call_id", "") or "",
        "source": "ava-phone",
        "name": (structured.get("name") or "") or "",
        "phone": (structured.get("phone") or payload.get("caller_number") or "") or "",
        "email": (structured.get("email") or booking.get("attendee_email") or "") or "",
        "company": (structured.get("company") or booking.get("meeting_company") or "") or "",
        "interest": (structured.get("interest") or "") or "",
        "summary": (structured.get("summary") or "") or "",
        "meeting": meeting,
        "meeting_time": (
            booking.get("meeting_time_display")
            or structured.get("meeting_time")
            or ""
        ),
        "meeting_start": booking.get("meeting_start") or payload.get("meeting_start") or "",
        "telemost_join_url": booking.get("telemost_join_url") or "",
        "attendee_email": booking.get("attendee_email") or "",
        "caller_number": payload.get("caller_number") or "",
        "call_duration": payload.get("call_duration"),
    }
    try:
        import httpx

        resp = httpx.post(
            url,
            json=body,
            headers={"X-Webhook-Token": token, "Content-Type": "application/json"},
            timeout=20.0,
        )
        if resp.status_code >= 400:
            logger.warning(
                "[POST CALL] CRM fan-out HTTP %s call_id=%s body=%s",
                resp.status_code,
                payload.get("call_id"),
                (resp.text or "")[:300],
            )
            write_log(
                {
                    "status": "crm_fanout_error",
                    "call_id": payload.get("call_id", ""),
                    "http": resp.status_code,
                    "response": (resp.text or "")[:500],
                }
            )
        else:
            logger.info(
                "[POST CALL] CRM fan-out ok call_id=%s status=%s",
                payload.get("call_id"),
                resp.status_code,
            )
            try:
                write_log(
                    {
                        "status": "crm_fanout_ok",
                        "call_id": payload.get("call_id", ""),
                        "result": resp.json(),
                    }
                )
            except Exception:
                write_log(
                    {
                        "status": "crm_fanout_ok",
                        "call_id": payload.get("call_id", ""),
                    }
                )
    except Exception as exc:
        logger.exception("[POST CALL] CRM fan-out failed call_id=%s", payload.get("call_id"))
        write_log(
            {
                "status": "crm_fanout_error",
                "call_id": payload.get("call_id", ""),
                "error": str(exc),
            }
        )


def _process_post_call_payload(payload: dict) -> None:
    call_id = payload.get("call_id", "")
    try:
        send_lead, skip_reason = _should_send_lead_email(payload)
        if not send_lead:
            logger.info(
                "[POST CALL] lead email skipped call_id=%s reason=%s caller=%s",
                call_id,
                skip_reason,
                payload.get("caller_number"),
            )
            write_log(
                {
                    "status": "lead_email_skipped",
                    "call_id": call_id,
                    "reason": skip_reason,
                    "caller_number": payload.get("caller_number"),
                }
            )
            return

        transcript = transcript_to_text(payload.get("transcript", ""))
        caller_number = (
            payload.get("caller_number")
            or payload.get("caller")
            or payload.get("phone")
            or ""
        )
        caller_name = payload.get("caller_name", "")
        fallback_used = False
        try:
            structured = extract_structured_data(
                transcript,
                caller_number,
                caller_name,
            )
        except Exception as e:
            fallback_used = True
            logger.exception("[POST CALL] extraction failed call_id=%s", call_id)
            structured = {
                "name": _sanitize_extracted_name(caller_name),
                "phone": caller_number,
                "email": "",
                "meeting": False,
                "meeting_time": "",
                "company": "",
                "interest": "",
                "summary": (
                    "AI-разбор не успел выполниться, ниже сырой transcript:\n"
                    + (transcript or "")[:1000]
                ),
                "extraction_error": str(e),
            }
        subject, body = build_email(structured, payload)
        send_email(subject, body)
        write_log(
            {
                "status": "ok",
                "call_id": call_id,
                "structured": structured,
                "fallback_used": fallback_used,
            }
        )
        try:
            _fanout_lead_to_crm(structured, payload)
        except Exception:
            logger.exception("[POST CALL] CRM fan-out wrapper failed call_id=%s", call_id)
    except Exception as e:
        logger.exception("[POST CALL] failed call_id=%s", call_id)
        write_log(
            {
                "status": "post_call_error",
                "call_id": call_id,
                "error": str(e),
            }
        )


# --------------------
# CALENDAR REQUEST MODELS
# --------------------
class CalendarCheckRequest(BaseModel):
    start: str
    timezone: Optional[str] = None


class CalendarSuggestRequest(BaseModel):
    start: str
    duration_min: int = 30
    suggestions_count: int = 3
    search_hours_ahead: int = 72
    timezone: Optional[str] = None


class CalendarCreateRequest(BaseModel):
    start: str
    summary: str = "Созвон с клиентом"
    description: Optional[str] = ""
    location: Optional[str] = None
    attendee_email: Optional[str] = None
    timezone: Optional[str] = None
    # Необязательное поле: если не передано, backend сам считает +30 минут.
    end: Optional[str] = None

# --------------------
# CALENDAR HELPERS
# --------------------

def _safe_json_loads(raw: bytes) -> dict:
    """
    AVA иногда подставляет многострочный description как реальные переводы строк,
    а не как экранированные \n. strict=False разрешает control characters внутри строк.
    """
    text = raw.decode("utf-8", errors="replace").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return json.loads(text, strict=False)


def _clean_text(value: Optional[str]) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _clean_email(value: Optional[str]) -> str:
    email = _clean_text(value).replace(" ", "")
    if not email:
        return ""
    if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return email
    logger.error("[CALENDAR EMAIL SKIPPED] invalid attendee_email=%r", email)
    return ""
def _tz(name: Optional[str]) -> pytz.BaseTzInfo:
    try:
        return pytz.timezone(name or CALENDAR_TIMEZONE)
    except Exception:
        return pytz.timezone(CALENDAR_TIMEZONE)


def _parse_dt(value: str, tz_name: Optional[str] = None) -> datetime:
    tz = _tz(tz_name)
    dt = dtparser.parse(value)

    if dt.tzinfo is None:
        dt = tz.localize(dt)
    else:
        dt = dt.astimezone(tz)

    return dt


def _get_calendar():
    if not MAILRU_CALDAV_USERNAME or not MAILRU_CALDAV_PASSWORD:
        raise HTTPException(status_code=500, detail="Mail.ru calendar credentials are not configured")

    if not MAILRU_CALENDAR_URL:
        raise HTTPException(status_code=500, detail="MAILRU_CALENDAR_URL is not configured")

    client = caldav.DAVClient(
        url=MAILRU_CALDAV_URL,
        username=MAILRU_CALDAV_USERNAME,
        password=MAILRU_CALDAV_PASSWORD,
    )

    return caldav.Calendar(client=client, url=MAILRU_CALENDAR_URL)


def _find_conflicts(start_dt: datetime, end_dt: datetime):
    cal = _get_calendar()
    return cal.search(start=start_dt, end=end_dt, event=True)


def _slot_is_free(start_dt: datetime, end_dt: datetime) -> bool:
    conflicts = _find_conflicts(start_dt, end_dt)
    return len(conflicts) == 0


def _format_slot(dt: datetime) -> str:
    return dt.strftime("%d.%m.%Y %H:%M")


def _create_ics(
    start_dt: datetime,
    end_dt: datetime,
    summary: str,
    description: str = "",
    location: str = "",
    attendee_email: str = "",
    event_url: str = "",
) -> str:
    cal = Calendar()
    cal.add("prodid", "-//Quantum Labs//AVA Mail.ru Calendar//RU")
    cal.add("version", "2.0")

    event = Event()
    event.add("summary", summary)
    event.add("dtstart", start_dt)
    event.add("dtend", end_dt)
    event.add("dtstamp", datetime.utcnow())
    event.add("description", description or "")

    if location:
        event.add("location", location)

    url = _clean_text(event_url)
    if not url and location.startswith("http"):
        url = location
    if url:
        event.add("url", url)

    if attendee_email:
        event.add("attendee", f"MAILTO:{attendee_email}")

    cal.add_component(event)
    return cal.to_ical().decode("utf-8")


def _create_event(
    start_dt: datetime,
    end_dt: datetime,
    summary: str,
    description: str = "",
    location: str = "",
    attendee_email: str = "",
    event_url: str = "",
):
    cal = _get_calendar()
    ics = _create_ics(
        start_dt=start_dt,
        end_dt=end_dt,
        summary=summary,
        description=description,
        location=location,
        attendee_email=attendee_email,
        event_url=event_url,
    )
    return cal.save_event(ics)


def _create_telemost_conference(
    *,
    title: str = "",
    description: str = "",
) -> Tuple[Optional[str], Optional[str]]:
    """
    Create a Yandex Telemost conference and return (conference_id, join_url).
    Requires OAuth token with telemost-api:conferences.create scope.
    """
    if not TELEMOST_ENABLED:
        return None, None

    access_token = yandex_oauth.get_access_token()
    if not access_token:
        logger.warning(
            "[TELEMOST] skipped: no OAuth access token. "
            "Open /oauth/yandex/start?token=<WEBHOOK_TOKEN> once to authorize."
        )
        return None, None

    payload = {"waiting_room_level": TELEMOST_WAITING_ROOM_LEVEL}
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        TELEMOST_API_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"OAuth {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=TELEMOST_TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8", errors="replace")
            data = json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        logger.error(
            "[TELEMOST HTTP ERROR] status=%s body=%s",
            exc.code,
            err_body[:500],
        )
        return None, None
    except Exception as exc:
        logger.exception("[TELEMOST ERROR] %s", exc)
        return None, None

    conference_id = _clean_text(data.get("id"))
    join_url = _clean_text(data.get("join_url"))
    if not join_url:
        logger.error("[TELEMOST] API response missing join_url: %s", data)
        return conference_id or None, None

    logger.info(
        "[TELEMOST] conference created id=%s join_url=%s title=%r",
        conference_id,
        join_url,
        title[:80] if title else "",
    )
    return conference_id or None, join_url


def _append_telemost_to_event_text(
    description: str,
    join_url: str,
    *,
    summary: str = "",
) -> Tuple[str, str, str]:
    """Return (description, location) enriched with Telemost join link."""
    link_line = f"Ссылка на видеовстречу: {join_url}"
    base = (description or "").strip()
    if link_line not in base:
        base = f"{base}\n\n{link_line}".strip() if base else link_line
    location = join_url
    return base, location


def _suggest_slots(
    desired_start: datetime,
    duration_min: int = 30,
    suggestions_count: int = 3,
    search_hours_ahead: int = 72,
):
    suggestions = []
    current = desired_start
    end_limit = desired_start + timedelta(hours=search_hours_ahead)
    duration = timedelta(minutes=duration_min)

    while current + duration <= end_limit and len(suggestions) < suggestions_count:
        candidate_end = current + duration

        if _slot_is_free(current, candidate_end):
            suggestions.append({
                "start": current.isoformat(),
                "end": candidate_end.isoformat(),
                "label": _format_slot(current),
            })

        current += timedelta(minutes=30)

    return suggestions

# --------------------
# COMPANY KNOWLEDGE (AVA voice agent)
# Prefer standalone ava-knowledge (:8017); fallback to local markdown search.
# --------------------
KNOWLEDGE_SERVICE_URL = os.getenv(
    "KNOWLEDGE_SERVICE_URL",
    "http://127.0.0.1:8017",
).rstrip("/")
KNOWLEDGE_QUANTUM_LABS_PATH = os.getenv(
    "KNOWLEDGE_QUANTUM_LABS_PATH",
    "/root/ava/config/knowledge/quantum_labs.md",
).strip()


class KnowledgeQueryRequest(BaseModel):
    topic: str = ""
    topic_id: str = ""
    q: str = ""
    limit: int = 4
    max_chars: int = 4500


def _load_company_knowledge() -> str:
    path = KNOWLEDGE_QUANTUM_LABS_PATH
    if not path or not os.path.isfile(path):
        return ""
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _search_company_knowledge(topic: str, full_text: str, max_chars: int = 3500) -> str:
    topic = (topic or "").strip().lower()
    if not full_text:
        return "База знаний временно недоступна. Расскажи кратко про массовые выплаты и предложи встречу."
    if not topic:
        return full_text[:max_chars]

    keywords = [w for w in re.split(r"[\s,;.]+", topic) if len(w) >= 2]
    if not keywords:
        return full_text[:max_chars]

    sections: list[str] = []
    current: list[str] = []
    for line in full_text.splitlines():
        if re.match(r"^#{2,3}\s+", line) and current:
            sections.append("\n".join(current).strip())
            current = [line]
        else:
            current.append(line)
    if current:
        sections.append("\n".join(current).strip())

    scored: list[tuple[int, float, int, str]] = []
    for sec in sections:
        low = sec.lower()
        heading = sec.splitlines()[0].lower() if sec.splitlines() else ""
        score = 0
        for kw in keywords:
            score += low.count(kw)
            if kw in heading:
                score += 4
        if topic and topic in low:
            score += 8
        if any(marker in heading for marker in ("вопрос", "ответ", "faq", "частые")):
            score += 2
        if score:
            density = score / max(1.0, len(sec) / 1000)
            scored.append((score, density, len(sec), sec))
    scored.sort(key=lambda x: (-x[0], -x[1], x[2]))

    if not scored:
        # fallback: lines containing any keyword
        hits = [
            ln
            for ln in full_text.splitlines()
            if any(kw in ln.lower() for kw in keywords)
        ]
        blob = "\n".join(hits[:40]).strip()
        return (blob or full_text)[:max_chars]

    out = "\n\n".join(s for _, _, _, s in scored[:4])
    return out[:max_chars]


def _proxy_knowledge_query(req: KnowledgeQueryRequest) -> Optional[dict]:
    """Forward to ava-knowledge when available."""
    if not KNOWLEDGE_SERVICE_URL:
        return None
    payload = {
        "topic": (req.topic or req.q or "").strip(),
        "topic_id": (req.topic_id or "").strip(),
        "limit": req.limit,
        "max_chars": req.max_chars,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{KNOWLEDGE_SERVICE_URL}/api/knowledge/query",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=6) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            data = json.loads(raw) if raw else {}
            if isinstance(data, dict) and data.get("ok"):
                data.setdefault("via", "ava-knowledge")
                return data
    except Exception as exc:
        logger.warning("knowledge service proxy failed: %s", exc)
    return None


@app.post("/api/knowledge/query")
def knowledge_query(req: KnowledgeQueryRequest):
    proxied = _proxy_knowledge_query(req)
    if proxied:
        return proxied
    text = _load_company_knowledge()
    snippet = _search_company_knowledge(req.topic or req.q, text, max_chars=req.max_chars or 3500)
    return {
        "ok": True,
        "topic": (req.topic or req.q or "").strip(),
        "topic_id": (req.topic_id or "").strip() or None,
        "text": snippet,
        "chars": len(snippet),
        "via": "mailer-local",
    }


# --------------------
# HEALTH
# --------------------
@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/oauth/yandex/status")
def yandex_oauth_status(x_webhook_token: str = Header(None)):
    if x_webhook_token != WEBHOOK_TOKEN:
        raise HTTPException(status_code=401, detail="bad token")
    status = yandex_oauth.oauth_status()
    status["authorize_url_hint"] = "/oauth/yandex/start?token=<WEBHOOK_TOKEN>"
    return status


@app.get("/oauth/yandex/start")
def yandex_oauth_start(token: str = ""):
    if token != WEBHOOK_TOKEN:
        raise HTTPException(status_code=401, detail="bad token")
    if not yandex_oauth.oauth_configured():
        raise HTTPException(
            status_code=500,
            detail="Set YANDEX_OAUTH_CLIENT_ID, YANDEX_OAUTH_CLIENT_SECRET, YANDEX_OAUTH_REDIRECT_URI in .env",
        )
    return RedirectResponse(yandex_oauth.build_authorize_url(), status_code=302)


@app.get("/oauth/yandex/callback")
def yandex_oauth_callback(code: str = "", error: str = "", error_description: str = ""):
    return _yandex_oauth_finish(code=code, error=error, error_description=error_description)


@app.get("/oauth/yandex/manual")
def yandex_oauth_manual_page(token: str = ""):
    if token != WEBHOOK_TOKEN:
        raise HTTPException(status_code=401, detail="bad token")
    auth_url = yandex_oauth.build_authorize_url()
    return HTMLResponse(
        f"""
        <h1>Яндекс OAuth — ручной код</h1>
        <ol>
          <li><a href="{auth_url}" target="_blank">Открыть авторизацию Яндекса</a></li>
          <li>Разрешите доступ и скопируйте код с экрана</li>
          <li>Вставьте код ниже</li>
        </ol>
        <form method="post" action="/oauth/yandex/manual?token={token}">
          <input name="code" size="40" placeholder="код подтверждения" required />
          <button type="submit">Сохранить токен</button>
        </form>
        """
    )


@app.get("/oauth/yandex/exchange")
def yandex_oauth_exchange(code: str = "", token: str = ""):
    """Альтернатива форме: ?token=...&code=..."""
    if token != WEBHOOK_TOKEN:
        raise HTTPException(status_code=401, detail="bad token")
    return _yandex_oauth_finish(code=code.strip())


@app.post("/oauth/yandex/manual")
async def yandex_oauth_manual_submit(request: Request, token: str = ""):
    if token != WEBHOOK_TOKEN:
        raise HTTPException(status_code=401, detail="bad token")
    form = await request.form()
    code = str(form.get("code") or "").strip()
    return _yandex_oauth_finish(code=code)


def _yandex_oauth_finish(code: str = "", error: str = "", error_description: str = ""):
    if error:
        return HTMLResponse(
            f"<h1>Ошибка авторизации Яндекс</h1><p>{error}: {error_description}</p>",
            status_code=400,
        )
    if not code:
        return HTMLResponse("<h1>Нет кода авторизации</h1>", status_code=400)

    result = yandex_oauth.exchange_authorization_code(code)
    if not result.get("ok"):
        err = result.get("error") or {}
        return HTMLResponse(
            "<h1>Не удалось получить токен</h1>"
            f"<pre>{json.dumps(err, ensure_ascii=False, indent=2)}</pre>",
            status_code=502,
        )

    return HTMLResponse(
        """
        <h1>Яндекс OAuth подключён</h1>
        <p>Refresh-токен сохранён. Телемост будет создаваться при записи в календарь.</p>
        <p>Можно закрыть эту страницу.</p>
        """
    )


# --------------------
# CALENDAR API
# --------------------
@app.post("/api/calendar/check")
def calendar_check(req: CalendarCheckRequest):
    start_dt = _parse_dt(req.start, req.timezone)
    end_dt = start_dt + timedelta(minutes=CALENDAR_DEFAULT_DURATION_MIN)

    free = _slot_is_free(start_dt, end_dt)

    return {
        "ok": True,
        "free": free,
        "start": start_dt.isoformat(),
        "end": end_dt.isoformat(),
        "duration_min": CALENDAR_DEFAULT_DURATION_MIN,
    }


@app.post("/api/calendar/suggest")
def calendar_suggest(req: CalendarSuggestRequest):
    start_dt = _parse_dt(req.start, req.timezone)

    suggestions = _suggest_slots(
        desired_start=start_dt,
        duration_min=req.duration_min,
        suggestions_count=req.suggestions_count,
        search_hours_ahead=req.search_hours_ahead,
    )

    return {
        "ok": True,
        "suggestions": suggestions,
    }


@app.post("/api/calendar/create")
async def calendar_create(request: Request, background_tasks: BackgroundTasks):
    """
    Создание события через ручной парсинг Request, чтобы не получать 422 из-за
    сырого многострочного JSON от AVA.
    """
    raw = await request.body()

    try:
        payload = _safe_json_loads(raw)
        req = CalendarCreateRequest(**payload)
    except Exception as e:
        logger.exception(
            "[CALENDAR CREATE BAD REQUEST] BODY=%s",
            raw.decode("utf-8", errors="replace"),
        )
        return JSONResponse(
            status_code=400,
            content={
                "ok": False,
                "created": False,
                "reason": "bad_request",
                "message": "Не удалось разобрать данные для создания встречи",
                "error": str(e),
            },
        )

    if request.headers.get("x-ava-e2e-dry-run", "").strip() in ("1", "true", "yes"):
        return {
            "ok": True,
            "created": True,
            "dry_run": True,
            "message": "E2E dry-run: календарь и welcome не трогаем",
            "welcome_email_queued": False,
            "welcome_email_sent": False,
            "telemost_created": False,
            "telemost_join_url": "",
        }

    try:
        start_dt = _parse_dt(req.start, req.timezone)
        end_dt = _parse_dt(req.end, req.timezone) if req.end else start_dt + timedelta(minutes=CALENDAR_DEFAULT_DURATION_MIN)

        summary = _clean_text(req.summary) or "Созвон с клиентом"
        description = _clean_text(req.description)
        location = _clean_text(req.location)
        attendee_email = _clean_email(req.attendee_email)

        if end_dt <= start_dt:
            return JSONResponse(
                status_code=400,
                content={
                    "ok": False,
                    "created": False,
                    "reason": "bad_time_range",
                    "message": "Время окончания встречи должно быть позже времени начала",
                },
            )

        if not _slot_is_free(start_dt, end_dt):
            return {
                "ok": False,
                "created": False,
                "reason": "slot_busy",
                "message": "Это время уже занято",
                "start": start_dt.isoformat(),
                "end": end_dt.isoformat(),
            }

        telemost_id = None
        telemost_join_url = None
        if TELEMOST_ENABLED:
            telemost_id, telemost_join_url = _create_telemost_conference(
                title=summary,
                description=description,
            )
            if TELEMOST_REQUIRED and not telemost_join_url:
                return JSONResponse(
                    status_code=502,
                    content={
                        "ok": False,
                        "created": False,
                        "reason": "telemost_create_failed",
                        "message": "Не удалось создать видеовстречу в Яндекс.Телемост",
                    },
                )
            if telemost_join_url:
                description, location = _append_telemost_to_event_text(
                    description,
                    telemost_join_url,
                    summary=summary,
                )

        event = _create_event(
            start_dt=start_dt,
            end_dt=end_dt,
            summary=summary,
            description=description,
            location=location,
            attendee_email=attendee_email,
            event_url=telemost_join_url or "",
        )

        welcome_sent = False
        welcome_pdf_attached = False
        welcome_error = ""
        welcome_queued = False
        if attendee_email:
            background_tasks.add_task(
                _send_welcome_presentation_email_logged,
                attendee_email,
                summary,
                description,
                start_dt.isoformat(),
                telemost_join_url or "",
            )
            welcome_queued = True

        return {
            "ok": True,
            "created": True,
            "message": "Встреча успешно создана",
            "event_url": str(getattr(event, "url", "")),
            "telemost_created": bool(telemost_join_url),
            "telemost_id": telemost_id or "",
            "telemost_join_url": telemost_join_url or "",
            "start": start_dt.isoformat(),
            "end": end_dt.isoformat(),
            "duration_min": CALENDAR_DEFAULT_DURATION_MIN,
            "attendee_email_used": bool(attendee_email),
            "welcome_email_sent": welcome_sent,
            "welcome_email_queued": welcome_queued,
            "welcome_pdf_attached": welcome_pdf_attached,
            "welcome_email_error": welcome_error,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            "[CALENDAR CREATE ERROR] payload=%s",
            json.dumps(payload, ensure_ascii=False),
        )
        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "created": False,
                "reason": "calendar_create_failed",
                "message": "Не удалось создать встречу в календаре",
                "error": str(e),
            },
        )

# --------------------
# WELCOME (used by ava-calendar after create)
# --------------------
class WelcomePresentationRequest(BaseModel):
    attendee_email: str = ""
    summary: str = ""
    description: str = ""
    meeting_start: str = ""
    telemost_join_url: str = ""


@app.post("/api/welcome/presentation")
async def welcome_presentation(
    req: WelcomePresentationRequest,
    background_tasks: BackgroundTasks,
    x_webhook_token: str = Header(None),
):
    """Queue welcome PDF email. Called by ava-calendar after booking."""
    if x_webhook_token != WEBHOOK_TOKEN:
        raise HTTPException(status_code=401, detail="bad token")
    email = (req.attendee_email or "").strip()
    if not email:
        return {"ok": False, "queued": False, "error": "attendee_email_required"}
    background_tasks.add_task(
        _send_welcome_presentation_email_logged,
        email,
        req.summary or "",
        req.description or "",
        req.meeting_start or "",
        req.telemost_join_url or "",
    )
    return {
        "ok": True,
        "queued": True,
        "email_queued": True,
        "attendee_email": email,
        "message": "Письмо с презентацией поставлено в очередь на отправку",
    }


# --------------------
# WEBHOOK
# --------------------
@app.post("/api/ava/post-call")
async def post_call(request: Request, background_tasks: BackgroundTasks, x_webhook_token: str = Header(None)):

    if x_webhook_token != WEBHOOK_TOKEN:
        raise HTTPException(status_code=401, detail="bad token")

    raw = await request.body()
    text = raw.decode("utf-8", errors="ignore")

    if not text.strip():
        return {"status": "empty"}

    try:
        payload = json.loads(text)
    except Exception as e:
        write_log({"error": str(e), "raw": text})
        return JSONResponse({"status": "bad json"}, status_code=400)

    # E2E / smoke: без GPT и без письма «Новый лид» (только ручной запуск с --live-emails)
    if request.headers.get("x-ava-e2e-dry-run", "").strip() in ("1", "true", "yes"):
        write_log(
            {
                "status": "dry_run",
                "call_id": payload.get("call_id", ""),
                "caller_number": payload.get("caller_number"),
            }
        )
        return {
            "status": "dry_run",
            "queued": False,
            "lead_email_skipped": True,
            "call_id": payload.get("call_id", ""),
        }

    background_tasks.add_task(_process_post_call_payload, payload)
    write_log(
        {
            "status": "queued",
            "call_id": payload.get("call_id", ""),
        }
    )

    return {
        "status": "queued",
        "queued": True,
        "call_id": payload.get("call_id", ""),
    }
