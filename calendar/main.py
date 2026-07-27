"""
ava-calendar — standalone Mail.ru CalDAV service.

API-compatible with the calendar routes previously embedded in ava-mailer:
  POST /api/calendar/check
  POST /api/calendar/suggest
  POST /api/calendar/create

Telemost is optional via CONFERENCE_BASE_URL (ava-conference).
"""

from __future__ import annotations

import json
import logging
import os
from datetime import timedelta
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

load_dotenv()

import caldav_client as cal
import conference_client
import mailer_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("ava-calendar")

WEBHOOK_TOKEN = os.getenv("WEBHOOK_TOKEN", "").strip()
SERVICE_NAME = "ava-calendar"

app = FastAPI(title="Quantum Labs Calendar", version="0.1.0")


def _check_token(x_webhook_token: Optional[str] = None) -> None:
    if not WEBHOOK_TOKEN:
        return
    if (x_webhook_token or "").strip() != WEBHOOK_TOKEN:
        raise HTTPException(status_code=401, detail="unauthorized")


def _safe_json_loads(raw: bytes) -> dict:
    text = raw.decode("utf-8", errors="replace").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return json.loads(text, strict=False)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    body = await request.body()
    logger.error(
        "[VALIDATION] %s BODY=%s ERRORS=%s",
        request.url.path,
        body.decode("utf-8", errors="replace"),
        exc.errors(),
    )
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "message": "Ошибка в данных запроса"},
    )


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
    end: Optional[str] = None
    create_telemost: Optional[bool] = None
    send_telemost_invite: bool = False
    invitees: List[str] = Field(default_factory=list)


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": SERVICE_NAME,
        "caldav_configured": cal.credentials_configured(),
        "timezone": cal.CALENDAR_TIMEZONE,
        "default_duration_min": cal.CALENDAR_DEFAULT_DURATION_MIN,
        "conference_base": conference_client.CONFERENCE_BASE_URL,
    }


@app.post("/api/calendar/check")
def calendar_check(
    req: CalendarCheckRequest,
    x_webhook_token: Optional[str] = Header(None),
):
    _check_token(x_webhook_token)
    start_dt = cal.parse_dt(req.start, req.timezone)
    end_dt = start_dt + timedelta(minutes=cal.CALENDAR_DEFAULT_DURATION_MIN)
    free = cal.slot_is_free(start_dt, end_dt)
    return {
        "ok": True,
        "free": free,
        "start": start_dt.isoformat(),
        "end": end_dt.isoformat(),
        "label": cal.format_slot(start_dt),
        "duration_min": cal.CALENDAR_DEFAULT_DURATION_MIN,
    }


@app.post("/api/calendar/suggest")
def calendar_suggest(
    req: CalendarSuggestRequest,
    x_webhook_token: Optional[str] = Header(None),
):
    _check_token(x_webhook_token)
    start_dt = cal.parse_dt(req.start, req.timezone)
    suggestions = cal.suggest_slots(
        desired_start=start_dt,
        duration_min=req.duration_min or cal.CALENDAR_DEFAULT_DURATION_MIN,
        suggestions_count=req.suggestions_count,
        search_hours_ahead=req.search_hours_ahead,
    )
    return {
        "ok": True,
        "suggestions": suggestions,
        "count": len(suggestions),
    }


@app.post("/api/calendar/create")
async def calendar_create(
    request: Request,
    x_webhook_token: Optional[str] = Header(None),
):
    _check_token(x_webhook_token)
    raw = await request.body()
    try:
        payload = _safe_json_loads(raw)
        req = CalendarCreateRequest.model_validate(payload)
    except Exception as exc:
        logger.error("[CREATE BAD REQUEST] BODY=%s err=%s", raw[:500], exc)
        return JSONResponse(
            status_code=400,
            content={
                "ok": False,
                "created": False,
                "reason": "bad_request",
                "message": "Не удалось разобрать данные для создания встречи",
                "error": str(exc),
            },
        )

    if request.headers.get("x-ava-e2e-dry-run", "").strip().lower() in ("1", "true", "yes"):
        return {
            "ok": True,
            "created": True,
            "dry_run": True,
            "message": "E2E dry-run: календарь не трогаем",
            "telemost_created": False,
            "telemost_join_url": "",
        }

    try:
        start_dt = cal.parse_dt(req.start, req.timezone)
        end_dt = (
            cal.parse_dt(req.end, req.timezone)
            if req.end
            else start_dt + timedelta(minutes=cal.CALENDAR_DEFAULT_DURATION_MIN)
        )
        summary = cal.clean_text(req.summary) or "Созвон с клиентом"
        description = cal.clean_text(req.description)
        location = cal.clean_text(req.location)
        attendee_email = cal.clean_email(req.attendee_email)

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

        if not cal.slot_is_free(start_dt, end_dt):
            return {
                "ok": False,
                "created": False,
                "reason": "slot_busy",
                "message": "Это время уже занято",
                "start": start_dt.isoformat(),
                "end": end_dt.isoformat(),
            }

        want_telemost = (
            conference_client.CREATE_TELEMOST_BY_DEFAULT
            if req.create_telemost is None
            else bool(req.create_telemost)
        )
        telemost_id = ""
        telemost_join_url = ""
        telemost_error = ""
        if want_telemost:
            invitees = list(req.invitees)
            if attendee_email and attendee_email not in invitees:
                invitees.append(attendee_email)
            conf = conference_client.create_telemost(
                title=summary,
                invitees=invitees if req.send_telemost_invite else [],
                when_text=cal.format_slot(start_dt),
                message=description[:500],
                send_invites=bool(req.send_telemost_invite and invitees),
            )
            if conf.get("ok") and conf.get("join_url"):
                telemost_join_url = conf["join_url"]
                telemost_id = conf.get("conference_id") or ""
                link_line = f"Ссылка на видеовстречу: {telemost_join_url}"
                if link_line not in description:
                    description = f"{description}\n\n{link_line}".strip() if description else link_line
                location = telemost_join_url
            else:
                telemost_error = str(conf.get("error") or conf.get("message") or "telemost_create_failed")
                logger.warning("[CREATE] telemost soft-fail: %s", telemost_error)

        event = cal.create_event(
            start_dt=start_dt,
            end_dt=end_dt,
            summary=summary,
            description=description,
            location=location,
            attendee_email=attendee_email,
            event_url=telemost_join_url or "",
        )

        message = "Встреча успешно создана"
        if telemost_join_url:
            message += f". ВКС: {telemost_join_url}"
        elif want_telemost and telemost_error:
            message += f". Телемост не создан ({telemost_error})"

        welcome: dict = {"ok": False, "skipped": True}
        if attendee_email:
            welcome = mailer_client.queue_welcome_presentation(
                attendee_email=attendee_email,
                summary=summary,
                description=description,
                meeting_start=start_dt.isoformat(),
                telemost_join_url=telemost_join_url,
            )
            if welcome.get("ok") and welcome.get("queued"):
                message += ". Welcome-письмо поставлено в очередь"
            elif not welcome.get("skipped"):
                logger.warning("[CREATE] welcome soft-fail: %s", welcome)

        return {
            "ok": True,
            "created": True,
            "message": message,
            "event_url": str(getattr(event, "url", "") or ""),
            "telemost_created": bool(telemost_join_url),
            "telemost_id": telemost_id,
            "telemost_join_url": telemost_join_url,
            "telemost_error": telemost_error,
            "welcome_email_queued": bool(welcome.get("ok") and welcome.get("queued")),
            "start": start_dt.isoformat(),
            "end": end_dt.isoformat(),
            "duration_min": int((end_dt - start_dt).total_seconds() // 60),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("[CREATE ERROR] %s", exc)
        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "created": False,
                "reason": "calendar_create_failed",
                "message": "Не удалось создать событие в календаре",
                "error": str(exc),
            },
        )
