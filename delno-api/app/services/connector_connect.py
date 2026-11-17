"""Connect mail, calendar, and video by a real probe — not a settings flag.

A company is connected only after a successful read (calendar events, SMTP
login, or a provider check) that used credentials from that tenant's vault.
``connectors.*.enabled`` does not count.
"""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

from sqlalchemy.orm import Session

from app.adapters.connectors.http_client import post_json
from app.core.config import get_settings
from app.core.tenant import TenantContext
from app.models.tenant import Tenant
from app.services.calendar_accounts import credentials_for_calendar
from app.services.tenant_vault import save_secret

HONEST_KINDS = frozenset({"calendar", "mail", "conference"})

_EXAMPLE = "ivan@example.ru"

PROVIDERS: dict[str, list[dict[str, Any]]] = {
    "calendar": [
        {
            "id": "google",
            "title": "Google Calendar",
            "auth": "oauth",
            "vault_kind": "calendar_google",
            "foreign": True,
            "example_login": _EXAMPLE,
            "hint": (
                "OAuth Google: кнопка откроет accounts.google.com, если на сервере заданы "
                "GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET и GOOGLE_OAUTH_REDIRECT_URI. "
                "Эти значения не вводятся в кабинет. Либо вставьте access token — он уйдёт в сейф, "
                f"и мы сразу прочитаем события. Пример ящика: {_EXAMPLE}."
            ),
            "password_label": "Access token (если без кнопки OAuth)",
            "login_optional": True,
        },
        {
            "id": "yandex",
            "title": "Яндекс.Календарь",
            "auth": "app_password",
            "vault_kind": "calendar_yandex",
            "foreign": False,
            "example_login": _EXAMPLE,
            "hint": (
                f"Логин как {_EXAMPLE}. Пароль — пароль приложения, не пароль от Яндекс ID. "
                "Где взять: id.yandex.ru → Безопасность → Пароли приложений. "
                "Ссылку CalDAV смотрите в настройках календаря (доступ по CalDAV)."
            ),
            "password_label": "Пароль приложения",
            "login_optional": False,
            "needs_calendar_url": True,
        },
        {
            "id": "mailru",
            "title": "Календарь Mail.ru",
            "auth": "app_password",
            "vault_kind": "calendar_mailru",
            "foreign": False,
            "example_login": _EXAMPLE,
            "hint": (
                f"Логин как {_EXAMPLE}. Пароль — пароль для внешнего приложения из настроек Mail.ru, "
                "не пароль от почты. Ссылку календаря CalDAV копируют в настройках календаря."
            ),
            "password_label": "Пароль приложения",
            "login_optional": False,
            "needs_calendar_url": True,
        },
        {
            "id": "outlook",
            "title": "Outlook / Microsoft Graph",
            "auth": "graph_token",
            "vault_kind": "calendar_outlook",
            "foreign": True,
            "example_login": _EXAMPLE,
            "hint": (
                f"Токен Microsoft Graph с правом Calendars.Read. Пример ящика: {_EXAMPLE}. "
                "Данные у Microsoft вне РФ — нужно согласие. Подключено только после чтения событий."
            ),
            "password_label": "Graph access token",
            "login_optional": True,
        },
        {
            "id": "delno",
            "title": "Календарь DELNO",
            "auth": "internal",
            "vault_kind": "",
            "foreign": False,
            "example_login": "",
            "hint": (
                "Внутренний календарь этой компании. Внешний пароль не нужен. "
                "Статус «подключено» появится только после успешного чтения списка событий."
            ),
            "password_label": "",
            "login_optional": True,
        },
    ],
    "mail": [
        {
            "id": "yandex",
            "title": "Почта Яндекса",
            "auth": "app_password",
            "vault_kind": "mail_yandex",
            "foreign": False,
            "example_login": _EXAMPLE,
            "hint": (
                f"Логин как {_EXAMPLE}. Пароль приложения: id.yandex.ru → Безопасность → "
                "Пароли приложений. Обычный пароль от ящика не принимаем. "
                "Подключено только после входа на SMTP."
            ),
            "password_label": "Пароль приложения",
            "login_optional": False,
        },
        {
            "id": "mailru",
            "title": "Почта Mail.ru",
            "auth": "app_password",
            "vault_kind": "mail_mailru",
            "foreign": False,
            "example_login": _EXAMPLE,
            "hint": (
                f"Логин как {_EXAMPLE}. Пароль для внешнего приложения в настройках Mail ID, "
                "не пароль от входа на сайт."
            ),
            "password_label": "Пароль приложения",
            "login_optional": False,
        },
        {
            "id": "regru",
            "title": "Почта Reg.ru / хостинг",
            "auth": "app_password",
            "vault_kind": "mail_regru",
            "foreign": False,
            "example_login": _EXAMPLE,
            "hint": (
                f"Ящик на хостинге (SMTP mail.hosting.reg.ru), логин как {_EXAMPLE}. "
                "Пароль ящика или SMTP-пароль из панели хостинга. "
                "Подключено только после успешного входа на SMTP."
            ),
            "password_label": "Пароль ящика / SMTP",
            "login_optional": False,
        },
        {
            "id": "google",
            "title": "Почта Google",
            "auth": "app_password",
            "vault_kind": "mail_google",
            "foreign": True,
            "example_login": _EXAMPLE,
            "hint": (
                f"Логин как {_EXAMPLE}. Пароль приложения Google (Account → Security → App passwords), "
                "не пароль от аккаунта. Данные у Google вне РФ — нужно согласие."
            ),
            "password_label": "Пароль приложения",
            "login_optional": False,
        },
        {
            "id": "outlook",
            "title": "Почта Outlook",
            "auth": "app_password",
            "vault_kind": "mail_outlook",
            "foreign": True,
            "example_login": _EXAMPLE,
            "hint": (
                f"Логин как {_EXAMPLE}. Пароль приложения Microsoft, не пароль от учётной записи. "
                "Данные у Microsoft вне РФ — нужно согласие."
            ),
            "password_label": "Пароль приложения",
            "login_optional": False,
        },
    ],
    "conference": [
        {
            "id": "yandex",
            "title": "Яндекс Телемост",
            "auth": "token",
            "vault_kind": "conference_yandex",
            "foreign": False,
            "example_login": _EXAMPLE,
            "hint": (
                "OAuth-токен Телемоста этой компании, не общий токен сервера. "
                f"Пример организатора: {_EXAMPLE}. Подключено только если провайдер принял токен."
            ),
            "password_label": "OAuth-токен Телемоста",
            "login_optional": True,
        },
        {
            "id": "google_meet",
            "title": "Google Meet",
            "auth": "token",
            "vault_kind": "conference_google",
            "foreign": True,
            "example_login": _EXAMPLE,
            "hint": (
                f"Access token календаря Google с правом создавать встречи. Пример: {_EXAMPLE}. "
                "Данные у Google вне РФ — нужно согласие."
            ),
            "password_label": "Access token",
            "login_optional": True,
        },
        {
            "id": "zoom",
            "title": "Zoom",
            "auth": "token",
            "vault_kind": "conference_zoom",
            "foreign": True,
            "example_login": _EXAMPLE,
            "hint": "Access token Zoom этой компании. Общий серверный токен не используется.",
            "password_label": "Access token Zoom",
            "login_optional": True,
        },
        {
            "id": "teams",
            "title": "Microsoft Teams",
            "auth": "token",
            "vault_kind": "conference_teams",
            "foreign": True,
            "example_login": _EXAMPLE,
            "hint": "Graph token с правом OnlineMeetings. Данные у Microsoft вне РФ — нужно согласие.",
            "password_label": "Graph token",
            "login_optional": True,
        },
        {
            "id": "jitsi",
            "title": "Jitsi",
            "auth": "internal",
            "vault_kind": "",
            "foreign": False,
            "example_login": "",
            "hint": (
                "Комната собирается для этой компании, без общего пароля сервера. "
                "Подключено только если ссылка комнаты прочиталась обратно."
            ),
            "password_label": "",
            "login_optional": True,
        },
    ],
}

_CAL_SOURCE = {"google": "google", "yandex": "yandex", "mailru": "mailru", "outlook": "outlook"}


class ProbeError(Exception):
    def __init__(self, code: str, message_ru: str):
        self.code = code
        self.message_ru = message_ru
        super().__init__(code)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _settings(tenant: Tenant) -> dict[str, Any]:
    return dict(tenant.settings) if isinstance(tenant.settings, dict) else {}


def _provider(kind: str, provider_id: str) -> dict[str, Any] | None:
    wanted = (provider_id or "").strip().lower()
    for item in PROVIDERS.get(kind) or []:
        if item["id"] == wanted:
            return item
    return None


def catalog(kind: str) -> list[dict[str, Any]]:
    """Public form specs. No secrets."""
    out = []
    for item in PROVIDERS.get(kind) or []:
        out.append(
            {
                "id": item["id"],
                "title": item["title"],
                "auth": item["auth"],
                "example_login": item.get("example_login") or "",
                "hint": item["hint"],
                "password_label": item.get("password_label") or "",
                "login_optional": bool(item.get("login_optional")),
                "needs_calendar_url": bool(item.get("needs_calendar_url")),
                "foreign": bool(item.get("foreign")),
            }
        )
    return out


def _internal_events(db: Session, ctx: TenantContext) -> list[dict[str, Any]]:
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    raw = (_settings(tenant).get("delno_calendar") or {}).get("events")
    if not isinstance(raw, list):
        raw = []
    events = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        events.append(
            {
                "summary": str(item.get("summary") or "")[:200],
                "start": item.get("start"),
                "end": item.get("end"),
            }
        )
    return events


def read_calendar_events(
    db: Session,
    ctx: TenantContext,
    provider: str,
    creds: dict[str, str] | None,
) -> list[dict[str, Any]]:
    if provider == "delno":
        return _internal_events(db, ctx)
    base = (get_settings().calendar_base_url or "").strip()
    if not base:
        raise ProbeError(
            "broker_unavailable",
            "События не прочитаны: delno-calendar не настроен. Подключение не засчитано.",
        )
    source = _CAL_SOURCE.get(provider) or provider
    code, body, err = post_json(
        base,
        "/api/calendar/events",
        json={
            "source": source,
            "tenant_id": str(ctx.tenant_id),
            "credentials": creds or {},
        },
        token=(get_settings().office_webhook_token or None),
        headers={"X-Tenant-Id": str(ctx.tenant_id)},
    )
    if err or not isinstance(body, dict) or not body.get("ok"):
        raise ProbeError("read_failed", _read_failure_message(code, err))
    events = body.get("events")
    return events if isinstance(events, list) else []


def probe_mail_login(
    db: Session,
    ctx: TenantContext,
    provider: str,
    creds: dict[str, str],
) -> dict[str, Any]:
    base = (get_settings().mailer_base_url or "").strip()
    if not base:
        raise ProbeError(
            "broker_unavailable",
            "Почта не проверена: почтовый сервис недоступен. Подключение не засчитано.",
        )
    code, body, err = post_json(
        base,
        "/api/mail/probe",
        json={
            "tenant_id": str(ctx.tenant_id),
            "provider": provider,
            "username": creds.get("username") or creds.get("login") or "",
            "password": creds.get("password") or "",
        },
        token=(get_settings().office_webhook_token or None),
        headers={"X-Tenant-Id": str(ctx.tenant_id)},
    )
    if err or not isinstance(body, dict) or not body.get("ok"):
        message = ""
        if isinstance(body, dict):
            message = str(body.get("message_ru") or "")
        raise ProbeError("auth_failed", message or _read_failure_message(code, err))
    return {"ok": True}


def probe_conference(
    db: Session,
    ctx: TenantContext,
    provider: str,
    creds: dict[str, str] | None,
) -> dict[str, Any]:
    if provider == "jitsi":
        room = f"delno-{ctx.tenant_slug}-{str(ctx.tenant_id)[:8]}"
        url = f"https://meet.jit.si/{room}"
        if not url.startswith("https://") or room not in url:
            raise ProbeError("read_failed", "Ссылку комнаты не удалось прочитать.")
        return {"ok": True, "join_url": url}
    base = (get_settings().conference_base_url or "").strip()
    if not base:
        raise ProbeError(
            "broker_unavailable",
            "Видеовстреча не проверена: сервис конференций недоступен. Подключение не засчитано.",
        )
    token = str((creds or {}).get("token") or "")
    code, body, err = post_json(
        base,
        "/api/conferences/probe",
        json={"tenant_id": str(ctx.tenant_id), "provider": provider, "token": token},
        token=(get_settings().office_webhook_token or None),
    )
    if err or not isinstance(body, dict) or not body.get("ok"):
        message = str(body.get("message_ru") or "") if isinstance(body, dict) else ""
        raise ProbeError("auth_failed", message or _read_failure_message(code, err))
    return {"ok": True}


def _read_failure_message(code: int, err: str | None) -> str:
    text = (err or "").lower()
    if code in {401, 403} or any(word in text for word in ("401", "403", "unauth", "forbidden", "invalid")):
        return "Провайдер отклонил доступ. Проверьте пароль приложения или токен."
    return "Не удалось прочитать данные провайдера. Подключение не засчитано."


def _vault_creds(db: Session, ctx: TenantContext, spec: dict[str, Any]) -> dict[str, str] | None:
    kind = spec.get("vault_kind") or ""
    if spec["auth"] == "internal" or not kind:
        return {}
    if str(kind).startswith("calendar_"):
        source = {"calendar_google": "google", "calendar_yandex": "yandex", "calendar_mailru": "mailru", "calendar_outlook": "outlook"}[
            kind
        ]
        return credentials_for_calendar(db, ctx, source)
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    blob = (_settings(tenant).get("secrets") or {}) if isinstance(_settings(tenant).get("secrets"), dict) else {}
    row = blob.get(kind) if isinstance(blob.get(kind), dict) else None
    if not isinstance(row, dict):
        return None
    if spec.get("foreign") and not row.get("foreign_consent_at"):
        return None
    password = str(row.get("password") or "").strip()
    login = str(row.get("login") or "").strip()
    if spec["auth"] == "app_password":
        if not (login and password):
            return None
        return {"username": login, "login": login, "password": password}
    if not password:
        return None
    return {"token": password}


def _run_probe(db: Session, ctx: TenantContext, kind: str, spec: dict[str, Any]) -> dict[str, Any]:
    creds = _vault_creds(db, ctx, spec)
    if creds is None:
        raise ProbeError(
            "vault_missing",
            "В сейфе нет данных этого провайдера. Подключение не засчитано.",
        )
    if kind == "calendar":
        events = read_calendar_events(db, ctx, spec["id"], creds)
        return {"probe": "calendar_events_read", "count": len(events)}
    if kind == "mail":
        probe_mail_login(db, ctx, spec["id"], creds)
        return {"probe": "smtp_login"}
    if kind == "conference":
        probe_conference(db, ctx, spec["id"], creds)
        return {"probe": "conference_probe"}
    raise ProbeError("unsupported_kind", "Этот тип подключения не проверяем.")


def _write_link(
    db: Session,
    ctx: TenantContext,
    *,
    kind: str,
    provider: str,
    status: str,
    error: str | None,
    message_ru: str,
    probe: str | None,
) -> dict[str, Any]:
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    settings = _settings(tenant)
    links = dict(settings.get("connector_links") or {})
    row = {
        "provider": provider,
        "status": status,
        "checked_at": _now(),
        "error": error,
        "message_ru": message_ru[:300],
        "probe": probe,
        "verified_by": "probe",
    }
    links[kind] = row
    settings["connector_links"] = links
    tenant.settings = settings
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return public_link(row)


def public_link(row: dict[str, Any] | None) -> dict[str, Any]:
    raw = row or {}
    verified = raw.get("verified_by") == "probe"
    status = str(raw.get("status") or "disconnected")
    if status == "connected" and not verified:
        status = "disconnected"
    return {
        "provider": raw.get("provider"),
        "status": status if status in {"connected", "failed", "disconnected"} else "disconnected",
        "checked_at": raw.get("checked_at"),
        "error": raw.get("error"),
        "message_ru": raw.get("message_ru") or "",
        "probe": raw.get("probe"),
    }


def link_status(db: Session, ctx: TenantContext, kind: str) -> dict[str, Any]:
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    links = _settings(tenant).get("connector_links")
    row = links.get(kind) if isinstance(links, dict) else None
    if not isinstance(row, dict):
        return public_link(None)
    published = public_link(row)
    if published["status"] != "connected":
        return published
    spec = _provider(kind, str(row.get("provider") or ""))
    if spec is None:
        return public_link(None)
    if spec["auth"] != "internal" and _vault_creds(db, ctx, spec) is None:
        return {
            "provider": spec["id"],
            "status": "disconnected",
            "checked_at": row.get("checked_at"),
            "error": "vault_missing",
            "message_ru": "В сейфе больше нет данных, подключение сброшено.",
            "probe": row.get("probe"),
        }
    return published


def mail_delivery_access(db: Session, ctx: TenantContext) -> dict[str, Any] | None:
    """Return only this tenant's verified mail account for an outbound call."""
    current = link_status(db, ctx, "mail")
    if current["status"] != "connected":
        return None
    spec = _provider("mail", str(current.get("provider") or ""))
    if spec is None:
        return None
    creds = _vault_creds(db, ctx, spec)
    if not creds:
        return None
    return {
        "tenant_id": str(ctx.tenant_id),
        "provider": spec["id"],
        "username": creds["username"],
        "password": creds["password"],
    }


def conference_delivery_access(db: Session, ctx: TenantContext, provider: str) -> dict[str, Any] | None:
    """Return only a verified provider token belonging to this tenant."""
    if provider == "jitsi":
        return {"tenant_id": str(ctx.tenant_id), "provider": provider, "token": ""}
    current = link_status(db, ctx, "conference")
    if current["status"] != "connected" or current.get("provider") != provider:
        return None
    spec = _provider("conference", provider)
    creds = _vault_creds(db, ctx, spec) if spec else None
    if not creds or not creds.get("token"):
        return None
    return {"tenant_id": str(ctx.tenant_id), "provider": provider, "token": creds["token"]}


def connect_provider(
    db: Session,
    ctx: TenantContext,
    *,
    kind: str,
    provider: str,
    login: str | None = None,
    password: str | None = None,
    calendar_url: str | None = None,
    foreign_consent: bool = False,
) -> dict[str, Any]:
    if kind not in HONEST_KINDS:
        return {"ok": False, "error": "unsupported_kind", "message_ru": "Такой тип не подключаем этим флоу."}
    spec = _provider(kind, provider)
    if spec is None:
        return {"ok": False, "error": "unknown_provider", "message_ru": "Выберите провайдера из списка."}
    if spec["auth"] != "internal":
        if spec.get("foreign") and not foreign_consent:
            return {
                "ok": False,
                "error": "foreign_consent_required",
                "message_ru": "Нужно согласие: данные этого провайдера обрабатываются вне РФ.",
            }
        if not spec.get("login_optional") and not (login or "").strip():
            return {"ok": False, "error": "login_required", "message_ru": f"Укажите логин, например {_EXAMPLE}."}
        if spec.get("needs_calendar_url") and not (calendar_url or "").strip():
            return {
                "ok": False,
                "error": "calendar_url_required",
                "message_ru": "Нужна ссылка CalDAV календаря. Пароль от аккаунта не подойдёт.",
            }
        if not (password or "").strip():
            return {"ok": False, "error": "password_required", "message_ru": "Нужен пароль приложения или токен."}
        saved = save_secret(
            db,
            ctx,
            kind=spec["vault_kind"],
            login=login,
            password=password,
            foreign_consent=foreign_consent,
            extra={"calendar_url": calendar_url or ""},
        )
        if not saved.get("ok"):
            return {
                "ok": False,
                "error": saved.get("error") or "save_failed",
                "message_ru": "Не удалось сохранить данные в сейф.",
            }
    try:
        meta = _run_probe(db, ctx, kind, spec)
    except ProbeError as exc:
        link = _write_link(
            db,
            ctx,
            kind=kind,
            provider=spec["id"],
            status="failed",
            error=exc.code,
            message_ru=exc.message_ru,
            probe=None,
        )
        return {"ok": False, "error": exc.code, "message_ru": exc.message_ru, "connection": link}
    noun = { "calendar": "Календарь", "mail": "Почта", "conference": "Видеовстречи" }[kind]
    count = meta.get("count")
    if kind == "calendar":
        message = (
            f"{noun} ответил. Событий: {count}. Подключено."
            if count
            else f"{noun} ответил, событий сейчас нет. Подключено."
        )
    else:
        message = f"{noun}: проверка прошла. Подключено."
    link = _write_link(
        db,
        ctx,
        kind=kind,
        provider=spec["id"],
        status="connected",
        error=None,
        message_ru=message,
        probe=str(meta.get("probe") or ""),
    )
    return {"ok": True, "connection": link, "message_ru": message}


def reprobe(db: Session, ctx: TenantContext, *, kind: str) -> dict[str, Any]:
    current = link_status(db, ctx, kind)
    provider = str(current.get("provider") or "")
    spec = _provider(kind, provider)
    if spec is None:
        return {
            "ok": False,
            "error": "not_connected",
            "message_ru": "Сначала выберите провайдера и сохраните данные в сейф.",
            "connection": current,
        }
    try:
        meta = _run_probe(db, ctx, kind, spec)
    except ProbeError as exc:
        link = _write_link(
            db,
            ctx,
            kind=kind,
            provider=spec["id"],
            status="failed",
            error=exc.code,
            message_ru=exc.message_ru,
            probe=None,
        )
        return {"ok": False, "error": exc.code, "message_ru": exc.message_ru, "connection": link}
    link = _write_link(
        db,
        ctx,
        kind=kind,
        provider=spec["id"],
        status="connected",
        error=None,
        message_ru="Повторная проверка прошла. Подключено.",
        probe=str(meta.get("probe") or ""),
    )
    return {"ok": True, "connection": link, "message_ru": link["message_ru"]}


def google_oauth_start(db: Session, ctx: TenantContext) -> dict[str, Any]:
    client_id = (os.getenv("GOOGLE_OAUTH_CLIENT_ID") or "").strip()
    client_secret = (os.getenv("GOOGLE_OAUTH_CLIENT_SECRET") or "").strip()
    redirect_uri = (os.getenv("GOOGLE_OAUTH_REDIRECT_URI") or "").strip()
    if not (client_id and client_secret and redirect_uri):
        return {
            "ok": False,
            "error": "oauth_not_configured",
            "message_ru": (
                "Кнопка Google недоступна: на сервере не заданы GOOGLE_OAUTH_CLIENT_ID, "
                "GOOGLE_OAUTH_CLIENT_SECRET и GOOGLE_OAUTH_REDIRECT_URI. "
                "Секрет в кабинет не подставляется. Можно вставить access token в форму."
            ),
        }
    state = secrets.token_urlsafe(24)
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    settings = _settings(tenant)
    pending = dict(settings.get("oauth_states") or {})
    pending[state] = {"kind": "calendar", "provider": "google", "created_at": _now()}
    settings["oauth_states"] = pending
    tenant.settings = settings
    db.add(tenant)
    db.commit()
    query = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "https://www.googleapis.com/auth/calendar.readonly",
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
        }
    )
    return {
        "ok": True,
        "authorize_url": f"https://accounts.google.com/o/oauth2/v2/auth?{query}",
        "state": state,
    }


def exchange_google_code(code: str) -> str:
    """Exchange an auth code. Tests replace this. Does not log the code or tokens."""
    import httpx

    client_id = (os.getenv("GOOGLE_OAUTH_CLIENT_ID") or "").strip()
    client_secret = (os.getenv("GOOGLE_OAUTH_CLIENT_SECRET") or "").strip()
    redirect_uri = (os.getenv("GOOGLE_OAUTH_REDIRECT_URI") or "").strip()
    response = httpx.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=20.0,
    )
    if response.status_code >= 400:
        raise ProbeError("oauth_exchange_failed", "Google не выдал токен. Подключение не засчитано.")
    payload = response.json()
    token = str(payload.get("access_token") or "").strip()
    if not token:
        raise ProbeError("oauth_exchange_failed", "Google не выдал токен. Подключение не засчитано.")
    return token


def google_oauth_finish(db: Session, ctx: TenantContext, *, code: str, state: str) -> dict[str, Any]:
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    settings = _settings(tenant)
    pending = dict(settings.get("oauth_states") or {})
    expected = pending.get((state or "").strip())
    if not isinstance(expected, dict) or expected.get("provider") != "google":
        return {"ok": False, "error": "state_mismatch", "message_ru": "Сессия OAuth не совпала. Начните подключение снова."}
    pending.pop((state or "").strip(), None)
    settings["oauth_states"] = pending
    tenant.settings = settings
    db.add(tenant)
    db.commit()
    try:
        token = exchange_google_code((code or "").strip())
    except ProbeError as exc:
        link = _write_link(
            db,
            ctx,
            kind="calendar",
            provider="google",
            status="failed",
            error=exc.code,
            message_ru=exc.message_ru,
            probe=None,
        )
        return {"ok": False, "error": exc.code, "message_ru": exc.message_ru, "connection": link}
    return connect_provider(
        db,
        ctx,
        kind="calendar",
        provider="google",
        password=token,
        foreign_consent=True,
    )
