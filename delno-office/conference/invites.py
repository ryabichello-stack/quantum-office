"""SMTP invite emails for conferences."""

from __future__ import annotations

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)

SMTP_HOST = os.getenv("MAIL_SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("MAIL_SMTP_PORT", "465") or "465")
SMTP_USER = os.getenv("MAIL_USERNAME", "").strip()
SMTP_PASS = os.getenv("MAIL_PASSWORD", "").strip()
SMTP_TIMEOUT_SECONDS = float(os.getenv("MAIL_SMTP_TIMEOUT_SECONDS", "6") or "6")
MAIL_FROM_NAME = os.getenv("MAIL_FROM_NAME", "Quantum Labs").strip() or "Quantum Labs"
REPLY_TO = os.getenv("CONFERENCE_REPLY_TO", SMTP_USER).strip()


def smtp_configured() -> bool:
    return bool(SMTP_HOST and SMTP_USER and SMTP_PASS)


def _send_one(to: str, subject: str, body: str) -> Tuple[bool, str]:
    if not smtp_configured():
        return False, "smtp_not_configured"
    msg = MIMEMultipart()
    msg["From"] = f"{MAIL_FROM_NAME} <{SMTP_USER}>" if MAIL_FROM_NAME else SMTP_USER
    msg["To"] = to
    msg["Subject"] = subject
    if REPLY_TO:
        msg["Reply-To"] = REPLY_TO
    msg.attach(MIMEText(body, "plain", "utf-8"))
    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT_SECONDS) as server:
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        return True, ""
    except Exception as exc:
        logger.exception("[INVITE EMAIL] failed to=%s", to)
        return False, str(exc)


def build_invite_body(
    *,
    title: str,
    join_url: str,
    when_text: str = "",
    host_note: str = "",
    invitee_name: str = "",
) -> str:
    greeting = f"Здравствуйте, {invitee_name}!" if invitee_name else "Здравствуйте!"
    lines = [
        greeting,
        "",
        f"Вас приглашают на видеовстречу: {title or 'встреча Quantum Labs'}.",
    ]
    if when_text:
        lines.append(f"Когда: {when_text}")
    lines.extend(
        [
            "",
            "Ссылка на Яндекс Телемост:",
            join_url,
            "",
        ]
    )
    if host_note:
        lines.extend(["Комментарий:", host_note, ""])
    lines.extend(
        [
            "Если ссылка не открывается — скопируйте её в браузер.",
            "",
            "— Quantum Labs",
        ]
    )
    return "\n".join(lines)


def send_invites(
    *,
    invitees: Iterable[str],
    title: str,
    join_url: str,
    when_text: str = "",
    host_note: str = "",
) -> List[dict]:
    subject = f"Приглашение: {title or 'видеовстреча Quantum Labs'}"
    results: List[dict] = []
    for raw in invitees:
        email = (raw or "").strip()
        if not email or "@" not in email:
            results.append({"email": email, "sent": False, "error": "invalid_email"})
            continue
        body = build_invite_body(
            title=title,
            join_url=join_url,
            when_text=when_text,
            host_note=host_note,
        )
        ok, err = _send_one(email, subject, body)
        results.append({"email": email, "sent": ok, "error": err})
    return results
