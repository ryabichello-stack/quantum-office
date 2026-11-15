"""Owner's own calendar / mail accounts: honest «connected» only after a real check.

Calendar: CalDAV discovery + a real REPORT of the next 14 days of events.
Mail: a real SMTP login (no message is sent).
Credentials come from the tenant vault (settings.secrets.<kind>); never logged.

Google / Outlook need OAuth — not available yet; Hermes must say so plainly.
"""

from __future__ import annotations

import base64
import smtplib
import ssl
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Any

CALDAV_BASES = {
    "calendar_yandex": "https://caldav.yandex.ru/",
    "calendar_mailru": "https://calendar.mail.ru/principals/",
}
SMTP_HOSTS = {
    "mail_yandex": ("smtp.yandex.ru", 465),
    "mail_mailru": ("smtp.mail.ru", 465),
}
ACCOUNT_KINDS = frozenset(set(CALDAV_BASES) | set(SMTP_HOSTS))

_NS = {"d": "DAV:", "c": "urn:ietf:params:xml:ns:caldav"}
_TIMEOUT = 15


def connector_kind_for(kind: str) -> str | None:
    if kind.startswith("calendar_"):
        return "calendar"
    if kind.startswith("mail_"):
        return "mail"
    return None


def _auth(login: str, password: str) -> str:
    return "Basic " + base64.b64encode(f"{login}:{password}".encode()).decode()


def _dav(method: str, url: str, login: str, password: str, body: str, depth: str) -> tuple[int, ET.Element | None]:
    req = urllib.request.Request(
        url,
        data=body.encode(),
        method=method,
        headers={
            "Authorization": _auth(login, password),
            "Content-Type": "application/xml; charset=utf-8",
            "Depth": depth,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:  # noqa: S310 — fixed hosts
            raw = resp.read()
            code = resp.status
    except urllib.error.HTTPError as exc:
        return exc.code, None
    try:
        return code, ET.fromstring(raw) if raw else None
    except ET.ParseError:
        return code, None


def _href(root: ET.Element | None, path: str) -> str | None:
    if root is None:
        return None
    node = root.find(path, _NS)
    return (node.text or "").strip() if node is not None and node.text else None


def check_caldav(kind: str, login: str, password: str) -> dict[str, Any]:
    """Real read: principal → calendar-home → calendars → events in the next 14 days."""
    base = CALDAV_BASES[kind]
    principal_q = (
        '<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop>'
        "<d:current-user-principal/></d:prop></d:propfind>"
    )
    code, root = _dav("PROPFIND", base, login, password, principal_q, "0")
    if code in (401, 403):
        return {"ok": False, "code": "auth", "message_ru": "Календарь не пустил: логин или пароль приложения не подошли."}
    principal = _href(root, ".//d:current-user-principal/d:href")
    if not principal:
        return {"ok": False, "code": "discovery", "message_ru": "Не нашёл календарь по этому адресу (сервер не ответил как CalDAV)."}
    home_q = (
        '<?xml version="1.0"?><d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
        "<d:prop><c:calendar-home-set/></d:prop></d:propfind>"
    )
    _code, root = _dav("PROPFIND", urllib.parse.urljoin(base, principal), login, password, home_q, "0")
    home = _href(root, ".//c:calendar-home-set/d:href")
    if not home:
        return {"ok": False, "code": "discovery", "message_ru": "Вход прошёл, но список календарей не нашёлся."}
    list_q = (
        '<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop><d:resourcetype/>'
        "<d:displayname/></d:prop></d:propfind>"
    )
    _code, root = _dav("PROPFIND", urllib.parse.urljoin(base, home), login, password, list_q, "1")
    calendars = []
    for resp in (root.findall("d:response", _NS) if root is not None else []):
        if resp.find(".//d:resourcetype/c:calendar", _NS) is not None:
            href = _href(resp, "d:href")
            if href:
                calendars.append(href)
    if not calendars:
        return {"ok": False, "code": "no_calendars", "message_ru": "Вход прошёл, но календарей в аккаунте нет."}
    now = datetime.now(timezone.utc)
    fmt = "%Y%m%dT%H%M%SZ"
    report_q = (
        '<?xml version="1.0"?><c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
        "<d:prop><d:getetag/></d:prop><c:filter><c:comp-filter name=\"VCALENDAR\">"
        f'<c:comp-filter name="VEVENT"><c:time-range start="{now.strftime(fmt)}" '
        f'end="{(now + timedelta(days=14)).strftime(fmt)}"/></c:comp-filter>'
        "</c:comp-filter></c:filter></c:calendar-query>"
    )
    code, root = _dav("REPORT", urllib.parse.urljoin(base, calendars[0]), login, password, report_q, "1")
    if code not in (200, 207):
        return {"ok": False, "code": "read_failed", "message_ru": "Календарь нашёлся, но события прочитать не удалось."}
    events = len(root.findall("d:response", _NS)) if root is not None else 0
    return {
        "ok": True,
        "code": "verified",
        "calendars": len(calendars),
        "events_14d": events,
        "message_ru": f"Календарь проверен: вижу {len(calendars)} календар(я/ей), событий на 2 недели — {events}.",
    }


def check_smtp(kind: str, login: str, password: str) -> dict[str, Any]:
    host, port = SMTP_HOSTS[kind]
    try:
        with smtplib.SMTP_SSL(host, port, timeout=_TIMEOUT, context=ssl.create_default_context()) as smtp:
            smtp.login(login, password)
    except smtplib.SMTPAuthenticationError:
        return {"ok": False, "code": "auth", "message_ru": "Почта не пустила: логин или пароль приложения не подошли."}
    except Exception:  # noqa: BLE001
        return {"ok": False, "code": "unreachable", "message_ru": "Не удалось связаться с почтовым сервером."}
    return {"ok": True, "code": "verified", "message_ru": "Почта проверена: вход по паролю приложения прошёл."}


def verify_account(kind: str, login: str, password: str) -> dict[str, Any]:
    if not login or not password:
        return {"ok": False, "code": "missing", "message_ru": "Нужны адрес и пароль приложения."}
    if kind in CALDAV_BASES:
        return check_caldav(kind, login, password)
    if kind in SMTP_HOSTS:
        return check_smtp(kind, login, password)
    return {"ok": False, "code": "unsupported", "message_ru": "Такой аккаунт пока не поддерживается."}


def verified_accounts(settings: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """{connector_kind: {kind, at, ...}} for accounts that passed a real check."""
    secrets = (settings or {}).get("secrets") if isinstance(settings, dict) else None
    out: dict[str, dict[str, Any]] = {}
    for kind, row in (secrets or {}).items():
        if kind in ACCOUNT_KINDS and isinstance(row, dict) and row.get("verified_at"):
            ck = connector_kind_for(kind)
            if ck:
                out[ck] = {"kind": kind, "at": row.get("verified_at"), "summary": row.get("verified_summary")}
    return out
