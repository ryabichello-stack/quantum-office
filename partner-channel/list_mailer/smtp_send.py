from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, make_msgid
from html import escape
from pathlib import Path

from .store import ALLOWED_FROM, BLOCKED_FROM, ROOT

ENV_CANDIDATES = (ROOT / "smtp.local.env", ROOT / ".env")
FORBIDDEN_ENV_PATHS = (
    Path("/opt/ava-outreach/.env"),
    Path("/opt/ava-mailer/.env"),
)


def load_env() -> Path | None:
    for path in ENV_CANDIDATES:
        if not path.is_file():
            continue
        resolved = path.resolve()
        for bad in FORBIDDEN_ENV_PATHS:
            try:
                if resolved == bad.resolve():
                    raise SystemExit(f"Refusing outreach/mailer env: {bad}")
            except FileNotFoundError:
                pass
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip("'").strip('"')
            if key and key not in os.environ:
                os.environ[key] = val
        return path
    return None


def assert_from_ok(username: str) -> None:
    u = (username or "").strip().lower()
    if u in BLOCKED_FROM or u != ALLOWED_FROM:
        raise SystemExit(
            f"List-mailer refuses {username!r}. Must send only from {ALLOWED_FROM} "
            f"(isolated from office@ outreach limits)."
        )


def smtp_creds() -> tuple[str, int, str, str, str, str]:
    host = (os.getenv("PARTNER_MAIL_SMTP_HOST") or os.getenv("MAIL_SMTP_HOST") or "").strip()
    port = int(os.getenv("PARTNER_MAIL_SMTP_PORT") or os.getenv("MAIL_SMTP_PORT") or "465")
    user = (os.getenv("PARTNER_MAIL_USERNAME") or os.getenv("MAIL_USERNAME") or "").strip()
    password = os.getenv("PARTNER_MAIL_PASSWORD") or os.getenv("MAIL_PASSWORD") or ""
    from_name = (
        os.getenv("PARTNER_MAIL_FROM_NAME")
        or os.getenv("MAIL_FROM_NAME")
        or "Денис Рябов · Quantum Payouts"
    ).strip()
    reply = (
        os.getenv("PARTNER_MAIL_REPLY_TO") or os.getenv("MAIL_REPLY_TO") or user
    ).strip() or user
    return host, port, user, password, from_name, reply


def plain_to_fallback_html(plain: str) -> str:
    site = "https://quantumpayouts.ru"
    link = f'<a href="{site}" style="color:#0b57d0;text-decoration:underline;">'
    parts = []
    for line in plain.splitlines():
        if not line.strip():
            parts.append("<br>")
            continue
        e = escape(line)
        e = e.replace("Quantum Payouts", f"{link}Quantum Payouts</a>")
        e = e.replace(escape(site), f'{link}{escape(site.replace("https://", ""))}</a>')
        e = e.replace("quantumpayouts.ru", f"{link}quantumpayouts.ru</a>")
        parts.append(f"<p>{e}</p>")
    return (
        '<!DOCTYPE html><html lang="ru"><body style="font-family:Georgia,serif;'
        'line-height:1.55;color:#1a1a1a;max-width:640px;">'
        + "".join(parts)
        + "</body></html>"
    )


def send_email(*, to: str, subject: str, plain: str, html: str | None = None) -> str:
    host, port, user, password, from_name, reply = smtp_creds()
    assert_from_ok(user)
    if not host or not password:
        raise SystemExit("Missing SMTP host/password for rdv@ list-mailer.")

    mid = make_msgid(domain=user.split("@")[-1])
    msg = MIMEMultipart("alternative")
    msg["From"] = formataddr((from_name, user))
    msg["To"] = to
    msg["Subject"] = subject
    msg["Reply-To"] = reply
    msg["Message-ID"] = mid
    msg["List-Unsubscribe"] = f"<mailto:{user}?subject=unsubscribe>"
    msg["X-Campaign"] = "list-mailer"
    msg["X-Partner-Channel"] = "isolated-from-ava-outreach"
    body_html = html or plain_to_fallback_html(plain)
    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(body_html, "html", "utf-8"))

    timeout = float(
        os.getenv("PARTNER_MAIL_SMTP_TIMEOUT_SECONDS")
        or os.getenv("MAIL_SMTP_TIMEOUT_SECONDS")
        or "20"
    )
    with smtplib.SMTP_SSL(host, port, timeout=timeout) as s:
        s.login(user, password)
        s.send_message(msg)
    return mid.strip().strip("<>")
