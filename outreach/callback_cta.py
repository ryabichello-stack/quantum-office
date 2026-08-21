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

_DEFAULT_TITLE = "Если интересно — можем перезвонить"
_DEFAULT_BUTTON = "Перезвонить"
_DEFAULT_GREETING = "Здравствуйте! Это Quantum Labs — вы оставили заявку на звонок с письма."
_DEFAULT_SCRIPT = (
    "Ты — голосовой ассистент Quantum Labs. Клиент оставил заявку «перезвоните» "
    "из email-рассылки. Представься коротко, уточни удобное время и тему разговора, "
    "кратко расскажи про платёжную инфраструктуру Quantum Payouts и предложи "
    "следующий шаг (созвон с менеджером / демо). Будь вежлив и конкретен."
)
_DEFAULT_LEAD = "Одна короткая страница — и мы наберём ваш номер."


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
    # On by default: CTA is part of every letter unless explicitly disabled.
    return _cfg_bool(settings, "CALLBACK_CTA_ENABLED", True)


def dial_enabled(settings: Any = None) -> bool:
    # On by default: form submit should trigger AVA/Mango callback unless explicitly off.
    return _cfg_bool(settings, "CALLBACK_DIAL_ENABLED", True)


def notify_enabled(settings: Any = None) -> bool:
    return _cfg_bool(settings, "CALLBACK_NOTIFY_ENABLED", True)


def dial_mode(settings: Any = None) -> str:
    # Default ARI dial: Mango VPBX API is often disabled ("Service disabled" 401).
    mode = (_cfg(settings, "CALLBACK_DIAL_MODE", "dial") or "dial").strip().lower()
    if mode not in {"notify_only", "mango_callback", "dial"}:
        return "dial"
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


def cta_lead(settings: Any = None) -> str:
    return (_cfg(settings, "CALLBACK_CTA_LEAD", _DEFAULT_LEAD) or _DEFAULT_LEAD).strip()


def settings_snapshot(settings: Any = None) -> dict[str, Any]:
    return {
        "CALLBACK_CTA_ENABLED": "true" if cta_enabled(settings) else "false",
        "CALLBACK_DIAL_ENABLED": "true" if dial_enabled(settings) else "false",
        "CALLBACK_NOTIFY_ENABLED": "true" if notify_enabled(settings) else "false",
        "CALLBACK_DIAL_MODE": dial_mode(settings),
        "CALLBACK_CTA_TITLE": cta_title(settings),
        "CALLBACK_CTA_LEAD": cta_lead(settings),
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


def build_callback_cta_html(
    *,
    url: str,
    settings: Any = None,
    reply_mailto: str | None = None,
) -> str:
    """Callback block styled like the canonical red-orange CTA."""
    from content.email_chrome import cta_block_html

    return cta_block_html(
        url=url,
        title=cta_title(settings),
        lead=cta_lead(settings),
        button=cta_button(settings),
        reply_mailto=reply_mailto or notify_email(settings),
    )


def build_callback_cta_plain(
    *,
    url: str,
    settings: Any = None,
    reply_mailto: str | None = None,
) -> str:
    title = cta_title(settings)
    lead = cta_lead(settings)
    button = cta_button(settings)
    return f"\n\n{title}\n{lead}\n{button}: {url}\n"



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


def _ari_dial(*, phone: str, fio: str, settings: Any = None) -> dict[str, Any]:
    greeting = scenario_greeting(settings)
    script = scenario_script(settings)
    if fio:
        script = f"Клиент представился как: {fio}.\n\n" + script
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
    return {"ok": bool(result.get("ok", True)), "mode": "dial", "result": result}


def _mango_callback_failed(result: dict[str, Any]) -> bool:
    if result.get("ok"):
        return False
    http = result.get("http")
    mango = result.get("mango") if isinstance(result.get("mango"), dict) else {}
    msg = str(mango.get("message") or result.get("detail") or "").lower()
    if http in {401, 403, 503}:
        return True
    if "service disabled" in msg or "unauthorized" in msg:
        return True
    return not bool(result.get("ok"))


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
        if result.get("ok"):
            return {"ok": True, "mode": mode, "result": result}
        # Mango VPBX API often returns 401 "Service disabled" — fall back to ARI.
        if _mango_callback_failed(result):
            fallback = _ari_dial(phone=phone, fio=fio, settings=settings)
            fallback["fallback_from"] = "mango_callback"
            fallback["mango_error"] = {
                "http": result.get("http"),
                "mango": result.get("mango"),
            }
            return fallback
        return {"ok": False, "mode": mode, "result": result}

    return _ari_dial(phone=phone, fio=fio, settings=settings)


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

    dial_info: dict[str, Any] = {"ok": True, "skipped": True, "mode": "notify_only"}
    if dial_enabled(settings) and dial_mode(settings) != "notify_only":
        try:
            dial_info = trigger_dial(phone=phone_n, fio=name, settings=settings)
        except Exception as exc:  # noqa: BLE001
            dial_info = {"ok": False, "error": str(exc)[:400], "mode": dial_mode(settings)}
            logger.exception("callback dial failed")

    notify_ok = False
    notify_error = None
    to_addr = notify_email(settings)
    if notify_enabled(settings):
        try:
            dial_status = "пропущен (только уведомление)"
            if dial_info.get("skipped"):
                dial_status = "выключен"
            elif dial_info.get("ok"):
                dial_status = f"OK ({dial_info.get('mode')})"
                if dial_info.get("fallback_from"):
                    dial_status += f", fallback с {dial_info.get('fallback_from')}"
            else:
                dial_status = f"ОШИБКА ({dial_info.get('mode')}): {dial_info.get('error') or dial_info}"
            body = (
                f"Заказан звонок из email-рассылки Quantum Labs\n\n"
                f"ФИО: {name}\n"
                f"Телефон: +{phone_n}\n"
                f"Исходный email: {source_email or verified.get('email') or '—'}\n"
                f"Outbox id: {verified.get('outbox_id')}\n"
                f"Режим звонка: {dial_mode(settings)}\n"
                f"Автозвонок: {'вкл' if dial_enabled(settings) else 'выкл'}\n"
                f"Результат набора: {dial_status}\n"
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
    if dial_info.get("ok") and not dial_info.get("skipped"):
        msg = "Заявка принята. Сейчас набираем ваш номер."
    else:
        msg = "Заявка принята. Мы свяжемся с вами в ближайшее время."
    return {
        "ok": ok,
        "id": req_id,
        "fio": name,
        "phone": phone_n,
        "notify_ok": notify_ok,
        "notify_error": notify_error,
        "notify_to": to_addr if notify_ok else None,
        "dial": dial_info,
        "message": msg,
    }


def form_page_html(
    *,
    token: str,
    settings: Any = None,
    prefill_phone: str = "",
    prefill_fio: str = "",
    error: str = "",
    done: bool = False,
    done_message: str = "",
) -> str:
    """One-screen form — same look as the email card, autofocus, instant submit."""
    title = escape(cta_title(settings))
    lead = escape(cta_lead(settings))
    button = escape(cta_button(settings))
    err = f'<p class="err">{escape(error)}</p>' if error else ""
    if done:
        thanks = escape(
            done_message
            or "Спасибо! Заявка принята — перезвоним в ближайшие минуты."
        )
        body = (
            f"<h1>{title}</h1>"
            f"<p class='ok'>{thanks}</p>"
        )
    else:
        body = f"""
        <h1>{title}</h1>
        <p class="lead">{lead}</p>
        {err}
        <form method="post" action="" novalidate>
          <label>ФИО
            <input name="fio" type="text" required maxlength="200" autocomplete="name"
                   autofocus value="{escape(prefill_fio)}" placeholder="Иванов Иван Иванович" />
          </label>
          <label>Телефон
            <input name="phone" type="tel" required maxlength="32" autocomplete="tel"
                   inputmode="tel" value="{escape(prefill_phone)}" placeholder="+7 …" />
          </label>
          <button type="submit">{button}</button>
        </form>
        <p class="note">Заполнили — и мы сразу набираем номер.</p>
        """
    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
  <meta name="theme-color" content="#c4470f" />
  <title>{title} — Quantum Labs</title>
  <style>
    :root {{ color-scheme: light; }}
    * {{ box-sizing: border-box; }}
    body {{ margin:0; font:16px/1.55 "Segoe UI",Helvetica,Arial,sans-serif; color:#1a2229;
           background:#ebe6de; min-height:100vh; }}
    .bar {{ height:3px; background:#c4470f; }}
    .wrap {{ max-width:420px; margin:0 auto; padding:1.75rem 1.15rem 2.75rem; }}
    .card {{ background:#ffffff; border:1px solid #ddd6cb; padding:1.35rem 1.25rem 1.4rem; }}
    h1 {{ font:600 1.35rem/1.3 Georgia,"Times New Roman",serif; margin:0 0 0.5rem;
          letter-spacing:-0.015em; color:#1a2229; }}
    .lead {{ color:#5c6670; margin:0 0 1.15rem; font-size:0.95rem; line-height:1.5; }}
    label {{ display:block; margin:0 0 0.95rem; font-weight:600; font-size:0.72rem;
             letter-spacing:0.05em; text-transform:uppercase; color:#6a737b; }}
    input {{ display:block; width:100%; margin-top:0.45rem; padding:0.9rem 0.85rem; border:1px solid #d0d5da;
             background:#fff; font:16px/1.4 "Segoe UI",Helvetica,Arial,sans-serif; color:#1a2229; border-radius:4px; }}
    button {{ margin-top:0.45rem; width:100%; padding:1rem 1rem; border:0; background:#c4470f; color:#fff;
              font:600 1rem/1.2 "Segoe UI",Helvetica,Arial,sans-serif; cursor:pointer; border-radius:4px; }}
    .note {{ margin-top:0.95rem; font-size:0.8rem; color:#6a737b; }}
    .err {{ background:#fde8e4; color:#8a2a12; padding:0.7rem 0.8rem; margin:0 0 0.95rem; border-radius:4px; }}
    .ok {{ background:#e7f5ea; color:#1d5c2e; padding:0.85rem 0.9rem; margin:0; border-radius:4px; }}
    .brand {{ font-size:0.72rem; letter-spacing:0.14em; text-transform:uppercase; color:#6a737b; margin:0 0 1.1rem; font-weight:600; }}
  </style>
</head>
<body>
  <div class="bar"></div>
  <div class="wrap">
    <div class="brand">Quantum Labs</div>
    <div class="card">{body}</div>
  </div>
</body>
</html>"""
