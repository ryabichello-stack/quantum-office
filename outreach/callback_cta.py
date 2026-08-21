"""Email «Заказать звонок»: CTA → public form → notify + optional AVA dial.

Email clients do not reliably support interactive forms, so the letter gets a
button that opens a signed landing page with FIO + phone. On submit we always
notify staff by email and optionally trigger Console outbound (Mango callback
or ARI dial with a scenario from settings).
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import urllib.error
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any, Iterator
from email.mime.text import MIMEText
from email.utils import formataddr, make_msgid
import smtplib

from modules.tracking import short_hmac, tracking_public_base

logger = logging.getLogger("ava-outreach.callback-cta")

_DEFAULT_TITLE = "Хотите, перезвоним?"
_DEFAULT_BUTTON = "Заказать звонок"
_DEFAULT_GREETING = "Здравствуйте! Это Quantum Labs — вы оставили заявку на звонок с письма."
_DEFAULT_SCRIPT = (
    "Ты — голосовой ассистент Quantum Labs. Клиент оставил заявку «перезвоните» "
    "из email-рассылки. Представься коротко, уточни удобное время и тему разговора, "
    "кратко расскажи про платёжную инфраструктуру Quantum Payouts и предложи "
    "следующий шаг (созвон с менеджером / демо). Будь вежлив и конкретен."
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _data_dir() -> Path:
    return Path(os.getenv("DATA_DIR", "/opt/ava-outreach/data"))


def _db_path() -> Path:
    return _data_dir() / "callback_cta.sqlite3"


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS callback_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                token TEXT,
                outbox_id INTEGER,
                source_email TEXT,
                fio TEXT NOT NULL,
                phone TEXT NOT NULL,
                notify_ok INTEGER NOT NULL DEFAULT 0,
                dial_mode TEXT,
                dial_ok INTEGER,
                dial_detail TEXT,
                user_agent TEXT,
                ip TEXT
            )
            """
        )


def _cfg(settings: Any, key: str, default: str = "") -> str:
    if settings is not None:
        try:
            val = settings.get(key, default)
            if val is not None and str(val) != "":
                return str(val)
        except Exception:  # noqa: BLE001
            pass
    return os.getenv(key, default) or default


def _cfg_bool(settings: Any, key: str, default: bool = False) -> bool:
    if settings is not None and hasattr(settings, "get_bool"):
        try:
            return bool(settings.get_bool(key, default))
        except Exception:  # noqa: BLE001
            pass
    raw = _cfg(settings, key, "true" if default else "false")
    return str(raw).lower() in ("1", "true", "yes", "on")


def cta_enabled(settings: Any = None) -> bool:
    return _cfg_bool(settings, "CALLBACK_CTA_ENABLED", False)


def dial_enabled(settings: Any = None) -> bool:
    return _cfg_bool(settings, "CALLBACK_DIAL_ENABLED", False)


def notify_enabled(settings: Any = None) -> bool:
    return _cfg_bool(settings, "CALLBACK_NOTIFY_ENABLED", True)


def dial_mode(settings: Any = None) -> str:
    mode = (_cfg(settings, "CALLBACK_DIAL_MODE", "mango_callback") or "mango_callback").strip().lower()
    if mode not in {"notify_only", "mango_callback", "dial"}:
        return "mango_callback"
    return mode


def cta_title(settings: Any = None) -> str:
    return (_cfg(settings, "CALLBACK_CTA_TITLE", _DEFAULT_TITLE) or _DEFAULT_TITLE).strip()


def cta_button(settings: Any = None) -> str:
    return (_cfg(settings, "CALLBACK_CTA_BUTTON", _DEFAULT_BUTTON) or _DEFAULT_BUTTON).strip()


def scenario_greeting(settings: Any = None) -> str:
    return (_cfg(settings, "CALLBACK_SCENARIO_GREETING", _DEFAULT_GREETING) or _DEFAULT_GREETING).strip()


def scenario_script(settings: Any = None) -> str:
    return (_cfg(settings, "CALLBACK_SCENARIO_SCRIPT", _DEFAULT_SCRIPT) or _DEFAULT_SCRIPT).strip()


def notify_email(settings: Any = None) -> str:
    return (
        _cfg(settings, "CALLBACK_NOTIFY_EMAIL", "")
        or _cfg(settings, "REPLY_NOTIFY_EMAIL", "")
        or os.getenv("MAIL_REPLY_TO", "")
        or os.getenv("MAIL_USERNAME", "")
        or ""
    ).strip()


def settings_snapshot(settings: Any = None) -> dict[str, Any]:
    return {
        "CALLBACK_CTA_ENABLED": "true" if cta_enabled(settings) else "false",
        "CALLBACK_DIAL_ENABLED": "true" if dial_enabled(settings) else "false",
        "CALLBACK_NOTIFY_ENABLED": "true" if notify_enabled(settings) else "false",
        "CALLBACK_DIAL_MODE": dial_mode(settings),
        "CALLBACK_CTA_TITLE": cta_title(settings),
        "CALLBACK_CTA_BUTTON": cta_button(settings),
        "CALLBACK_NOTIFY_EMAIL": notify_email(settings),
        "CALLBACK_SCENARIO_GREETING": scenario_greeting(settings),
        "CALLBACK_SCENARIO_SCRIPT": scenario_script(settings),
        "CONSOLE_BASE": (os.getenv("CONSOLE_BASE") or "http://127.0.0.1:8013").rstrip("/"),
        "CONSOLE_TOKEN_CONFIGURED": bool((os.getenv("CONSOLE_TOKEN") or "").strip()),
    }


def make_callback_token(*, outbox_id: int, email: str) -> str:
    em = (email or "").strip().lower() or "campaign"
    oid = int(outbox_id or 0)
    sig = short_hmac(f"cb:{oid}:{em}", n=12)
    return f"{oid}.{sig}"


def parse_callback_token(token: str) -> dict[str, Any] | None:
    raw = (token or "").strip()
    if "." not in raw:
        return None
    oid_s, sig = raw.split(".", 1)
    if not sig or len(sig) < 8:
        return None
    try:
        oid = int(oid_s)
    except ValueError:
        return None
    return {"outbox_id": oid, "token": raw, "sig": sig}


def verify_callback_token(token: str, *, email: str | None = None) -> dict[str, Any] | None:
    """Verify HMAC. If email is unknown, try empty/campaign aliases for oid=0."""
    parsed = parse_callback_token(token)
    if not parsed:
        return None
    oid = int(parsed["outbox_id"])
    candidates = []
    if email:
        candidates.append((email or "").strip().lower())
    candidates.extend(["campaign", "", "preview"])
    # unique preserve order
    seen: set[str] = set()
    for em in candidates:
        if em in seen:
            continue
        seen.add(em)
        expect = make_callback_token(outbox_id=oid, email=em or "campaign")
        if hmac_equal(token, expect):
            return {"outbox_id": oid, "email": em or None, "token": token}
    return None


def hmac_equal(a: str, b: str) -> bool:
    import hmac as _hmac

    return _hmac.compare_digest((a or "").encode(), (b or "").encode())


def callback_url_for(token: str, settings: Any = None) -> str:
    base = tracking_public_base(settings)
    return f"{base}/callback/{token}"


def build_callback_cta_html(*, url: str, settings: Any = None) -> str:
    title = escape(cta_title(settings))
    button = escape(cta_button(settings))
    href = escape(url, quote=True)
    return (
        '<div style="margin:1.4em 0 0.4em;padding:1.05em 1.15em;border:1px solid #e5e8eb;'
        'background:#f6f7f8;border-radius:2px">'
        f'<p style="margin:0 0 0.45em;font:600 15px/1.35 Manrope,Segoe UI,Helvetica,Arial,sans-serif;'
        f'color:#0f1b24">{title}</p>'
        '<p style="margin:0 0 0.85em;font:13px/1.45 Manrope,Segoe UI,Helvetica,Arial,sans-serif;'
        'color:#4a5560">Оставьте ФИО и телефон — свяжемся в ближайшие минуты.</p>'
        f'<a href="{href}" style="display:inline-block;padding:10px 16px;background:#1a1a1a;'
        f'color:#ffffff;text-decoration:none;font:600 13px/1 Manrope,Segoe UI,Helvetica,Arial,sans-serif">'
        f"{button}</a>"
        "</div>"
    )


def build_callback_cta_plain(*, url: str, settings: Any = None) -> str:
    title = cta_title(settings)
    button = cta_button(settings)
    return f"\n\n---\n{title}\n{button}: {url}\n"


def normalize_phone(raw: str) -> str | None:
    s = (raw or "").strip()
    if not s:
        return None
    digits = re.sub(r"\D", "", s)
    if digits.startswith("8") and len(digits) == 11:
        digits = "7" + digits[1:]
    if digits.startswith("7") and len(digits) == 11:
        return digits
    if len(digits) == 10:
        return "7" + digits
    if len(digits) >= 11:
        return digits
    return None


def normalize_fio(raw: str) -> str:
    parts = [p for p in re.split(r"\s+", (raw or "").strip()) if p]
    return " ".join(parts)[:200]


def _send_staff_notify(*, subject: str, body: str, to_addr: str) -> None:
    host = os.getenv("MAIL_SMTP_HOST", "").strip()
    port = int(os.getenv("MAIL_SMTP_PORT", "465"))
    user = os.getenv("MAIL_USERNAME", "").strip()
    password = os.getenv("MAIL_PASSWORD", "")
    if not (host and user and password and to_addr):
        raise RuntimeError("SMTP not configured for callback notify")
    msg = MIMEText(body, "plain", "utf-8")
    msg["From"] = formataddr((os.getenv("MAIL_FROM_NAME", "Quantum Labs Outreach"), user))
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg["Message-ID"] = make_msgid(domain=user.split("@")[-1] if "@" in user else "localhost")
    with smtplib.SMTP_SSL(host, port, timeout=20) as server:
        server.login(user, password)
        server.send_message(msg)


def _console_headers() -> dict[str, str]:
    tok = (os.getenv("CONSOLE_TOKEN") or "").strip()
    h = {"Content-Type": "application/json", "Accept": "application/json"}
    if tok:
        h["X-Console-Token"] = tok
        h["Authorization"] = f"Bearer {tok}"
    return h


def _console_post(path: str, payload: dict[str, Any], *, timeout: float = 45.0) -> dict[str, Any]:
    base = (os.getenv("CONSOLE_BASE") or "http://127.0.0.1:8013").rstrip("/")
    url = f"{base}{path}"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST", headers=_console_headers())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw else {"ok": True}
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"console HTTP {exc.code}: {err[:400]}") from exc
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"console unreachable: {exc}") from exc


def trigger_dial(*, phone: str, fio: str, settings: Any = None) -> dict[str, Any]:
    mode = dial_mode(settings)
    if not dial_enabled(settings) or mode == "notify_only":
        return {"ok": True, "skipped": True, "mode": "notify_only"}

    if not (os.getenv("CONSOLE_TOKEN") or "").strip():
        return {"ok": False, "error": "CONSOLE_TOKEN not configured", "mode": mode}

    if mode == "mango_callback":
        result = _console_post(
            "/api/outbound/callback",
            {"phone": phone, "command_id": f"email-cb-{phone[-4:]}"},
        )
        return {"ok": bool(result.get("ok")), "mode": mode, "result": result}

    # ARI dial with per-call scenario from Quantum panel settings
    greeting = scenario_greeting(settings)
    script = scenario_script(settings)
    if fio:
        script = (
            f"Клиент представился как: {fio}.\n\n" + script
        )
    result = _console_post(
        "/api/outbound/dial",
        {
            "phone": phone,
            "context": "outbound",
            "greeting": greeting,
            "script": script,
            "use_knowledge": True,
        },
    )
    return {"ok": bool(result.get("ok", True)), "mode": mode, "result": result}


def recent_requests(*, limit: int = 30) -> list[dict[str, Any]]:
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, created_at, outbox_id, source_email, fio, phone,
                   notify_ok, dial_mode, dial_ok, dial_detail
            FROM callback_requests
            ORDER BY id DESC
            LIMIT ?
            """,
            (max(1, min(int(limit), 200)),),
        ).fetchall()
    return [dict(r) for r in rows]


def process_callback_request(
    *,
    token: str,
    fio: str,
    phone: str,
    settings: Any = None,
    source_email: str | None = None,
    user_agent: str | None = None,
    ip: str | None = None,
) -> dict[str, Any]:
    init_db()
    verified = verify_callback_token(token, email=source_email)
    if not verified:
        return {"ok": False, "error": "bad_signature"}

    name = normalize_fio(fio)
    phone_n = normalize_phone(phone)
    if len(name) < 2:
        return {"ok": False, "error": "fio_required"}
    if not phone_n:
        return {"ok": False, "error": "phone_invalid"}

    # basic rate limit: same phone within 10 min
    with _connect() as conn:
        recent = conn.execute(
            """
            SELECT id FROM callback_requests
            WHERE phone = ? AND created_at >= datetime('now', '-10 minutes')
            LIMIT 1
            """,
            (phone_n,),
        ).fetchone()
        if recent:
            return {"ok": False, "error": "rate_limited"}

    notify_ok = False
    notify_error = None
    to_addr = notify_email(settings)
    if notify_enabled(settings):
        try:
            body = (
                f"Заказан звонок из email-рассылки Quantum Labs\n\n"
                f"ФИО: {name}\n"
                f"Телефон: +{phone_n}\n"
                f"Исходный email: {source_email or verified.get('email') or '—'}\n"
                f"Outbox id: {verified.get('outbox_id')}\n"
                f"Режим звонка: {dial_mode(settings)}\n"
                f"Автозвонок: {'вкл' if dial_enabled(settings) else 'выкл'}\n"
                f"Время (UTC): {_utc_now()}\n"
            )
            _send_staff_notify(
                subject=f"Заявка на звонок: {name} +{phone_n}",
                body=body,
                to_addr=to_addr,
            )
            notify_ok = True
        except Exception as exc:  # noqa: BLE001
            notify_error = str(exc)[:400]
            logger.exception("callback notify failed")

    dial_info: dict[str, Any] = {"ok": True, "skipped": True, "mode": "notify_only"}
    if dial_enabled(settings) and dial_mode(settings) != "notify_only":
        try:
            dial_info = trigger_dial(phone=phone_n, fio=name, settings=settings)
        except Exception as exc:  # noqa: BLE001
            dial_info = {"ok": False, "error": str(exc)[:400], "mode": dial_mode(settings)}
            logger.exception("callback dial failed")

    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO callback_requests(
                created_at, token, outbox_id, source_email, fio, phone,
                notify_ok, dial_mode, dial_ok, dial_detail, user_agent, ip
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _utc_now(),
                token[:120],
                int(verified.get("outbox_id") or 0),
                (source_email or verified.get("email") or "")[:200],
                name,
                phone_n,
                1 if notify_ok else 0,
                str(dial_info.get("mode") or ""),
                1 if dial_info.get("ok") else 0,
                json.dumps(dial_info, ensure_ascii=False)[:2000],
                (user_agent or "")[:300],
                (ip or "")[:80],
            ),
        )
        req_id = int(cur.lastrowid)

    ok = notify_ok or bool(dial_info.get("ok"))
    return {
        "ok": ok,
        "id": req_id,
        "fio": name,
        "phone": phone_n,
        "notify_ok": notify_ok,
        "notify_error": notify_error,
        "notify_to": to_addr if notify_ok else None,
        "dial": dial_info,
        "message": "Заявка принята. Мы свяжемся с вами в ближайшее время.",
    }


def form_page_html(
    *,
    token: str,
    settings: Any = None,
    prefill_phone: str = "",
    prefill_fio: str = "",
    error: str = "",
    done: bool = False,
) -> str:
    title = escape(cta_title(settings))
    button = escape(cta_button(settings))
    err = f'<p class="err">{escape(error)}</p>' if error else ""
    if done:
        body = (
            f"<h1>{title}</h1>"
            "<p class='ok'>Спасибо! Заявка принята — перезвоним в ближайшие минуты.</p>"
        )
    else:
        body = f"""
        <h1>{title}</h1>
        <p class="lead">Оставьте ФИО и номер телефона — робот или менеджер Quantum Labs свяжется с вами.</p>
        {err}
        <form method="post" action="" novalidate>
          <label>ФИО
            <input name="fio" type="text" required maxlength="200" autocomplete="name"
                   value="{escape(prefill_fio)}" placeholder="Иванов Иван Иванович" />
          </label>
          <label>Телефон
            <input name="phone" type="tel" required maxlength="32" autocomplete="tel"
                   value="{escape(prefill_phone)}" placeholder="+7 …" />
          </label>
          <button type="submit">{button}</button>
        </form>
        <p class="note">Нажимая кнопку, вы соглашаетесь на обратный звонок по указанному номеру.</p>
        """
    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title} — Quantum Labs</title>
  <style>
    :root {{ color-scheme: light; }}
    body {{ margin:0; font:15px/1.5 Manrope,Segoe UI,Helvetica,Arial,sans-serif; color:#0f1b24;
           background:linear-gradient(165deg,#f3f1ec 0%,#e8ecef 55%,#f7f5f1 100%); min-height:100vh; }}
    .wrap {{ max-width:420px; margin:0 auto; padding:2.5rem 1.25rem; }}
    h1 {{ font-size:1.35rem; margin:0 0 0.6rem; letter-spacing:-0.02em; }}
    .lead {{ color:#44525c; margin:0 0 1.2rem; }}
    label {{ display:block; margin:0 0 0.85rem; font-weight:600; font-size:0.86rem; }}
    input {{ display:block; width:100%; margin-top:0.35rem; padding:0.7rem 0.75rem; border:1px solid #cfd5da;
             background:#fff; font:inherit; box-sizing:border-box; }}
    button {{ margin-top:0.4rem; width:100%; padding:0.85rem 1rem; border:0; background:#1a1a1a; color:#fff;
              font:600 0.95rem Manrope,Segoe UI,sans-serif; cursor:pointer; }}
    .note {{ margin-top:1rem; font-size:0.78rem; color:#6a737b; }}
    .err {{ background:#fde8e4; color:#8a2a12; padding:0.65rem 0.75rem; margin:0 0 0.9rem; }}
    .ok {{ background:#e7f5ea; color:#1d5c2e; padding:0.75rem 0.85rem; }}
    .brand {{ font-size:0.75rem; letter-spacing:0.08em; text-transform:uppercase; color:#6a737b; margin-bottom:1.2rem; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="brand">Quantum Labs</div>
    {body}
  </div>
</body>
</html>"""
