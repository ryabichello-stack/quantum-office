"""Delivery channels: email (SMTP) and Telegram Bot API."""

from __future__ import annotations

import json
import logging
import os
import smtplib
import urllib.error
import urllib.parse
import urllib.request
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Tuple

from models import FetchedFile

logger = logging.getLogger(__name__)

SMTP_HOST = os.getenv("MAIL_SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("MAIL_SMTP_PORT", "465") or "465")
SMTP_USER = os.getenv("MAIL_USERNAME", "").strip()
SMTP_PASS = os.getenv("MAIL_PASSWORD", "").strip()
SMTP_TIMEOUT = float(os.getenv("MAIL_SMTP_TIMEOUT_SECONDS", "10") or "10")
MAIL_FROM_NAME = os.getenv("MAIL_FROM_NAME", "Quantum Labs").strip() or "Quantum Labs"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_API = os.getenv("TELEGRAM_API_BASE", "https://api.telegram.org").rstrip("/")


def email_configured() -> bool:
    return bool(SMTP_HOST and SMTP_USER and SMTP_PASS)


def telegram_configured() -> bool:
    return bool(TELEGRAM_BOT_TOKEN)


def send_email(to: str, file: FetchedFile, *, subject: str = "", caption: str = "") -> Tuple[bool, str]:
    if not email_configured():
        return False, "smtp_not_configured"
    to = (to or "").strip()
    if not to or "@" not in to:
        return False, "invalid_email"

    msg = MIMEMultipart()
    msg["From"] = f"{MAIL_FROM_NAME} <{SMTP_USER}>"
    msg["To"] = to
    msg["Subject"] = subject or f"Файл: {file.filename}"
    body = caption or f"Во вложении: {file.filename}"
    msg.attach(MIMEText(body, "plain", "utf-8"))

    part = MIMEApplication(file.content)
    part.add_header("Content-Disposition", "attachment", filename=file.filename)
    msg.attach(part)

    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT) as server:
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        return True, ""
    except Exception as exc:
        logger.exception("email send failed")
        return False, str(exc)


def send_telegram(
    chat_id: str,
    file: FetchedFile,
    *,
    caption: str = "",
) -> Tuple[bool, str]:
    if not telegram_configured():
        return False, "telegram_not_configured"
    chat_id = (chat_id or "").strip()
    if not chat_id:
        return False, "invalid_chat_id"

    # Telegram Bot API multipart/form-data via stdlib is awkward; use curl-like boundary.
    boundary = "----avafilesboundary7MA4YWxkTrZu0gW"
    url = f"{TELEGRAM_API}/bot{TELEGRAM_BOT_TOKEN}/sendDocument"

    def _field(name: str, value: str) -> bytes:
        return (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{value}\r\n"
        ).encode("utf-8")

    body = b"".join(
        [
            _field("chat_id", chat_id),
            _field("caption", (caption or file.filename)[:1024]),
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="document"; filename="{file.filename}"\r\n'
                f"Content-Type: {file.content_type}\r\n\r\n"
            ).encode("utf-8"),
            file.content,
            f"\r\n--{boundary}--\r\n".encode("utf-8"),
        ]
    )
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
        if not data.get("ok"):
            return False, str(data.get("description") or data)
        return True, ""
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")[:400]
        return False, f"telegram_http_{exc.code}: {err}"
    except Exception as exc:
        logger.exception("telegram send failed")
        return False, str(exc)


def deliver(via: str, to: str, file: FetchedFile, *, caption: str = "", subject: str = "") -> Tuple[bool, str]:
    via = (via or "").strip().lower()
    if via in ("email", "mail", "smtp"):
        return send_email(to, file, subject=subject, caption=caption)
    if via in ("telegram", "tg"):
        return send_telegram(to, file, caption=caption)
    return False, f"unknown_via:{via}"


def delivery_status() -> dict:
    return {
        "email_configured": email_configured(),
        "telegram_configured": telegram_configured(),
    }
