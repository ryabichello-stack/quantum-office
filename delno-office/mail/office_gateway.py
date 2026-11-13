"""
Lightweight mail gateway for DELNO tools-first.

Does NOT replace legacy ava-mailer main.py (see PROTECTED_README.txt).
Provides:
  GET  /health
  POST /api/mail/send   — dry-run staging until SMTP_* configured
"""

from __future__ import annotations

import logging
import os
import smtplib
from email.mime.text import MIMEText
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("delno-mail")

WEBHOOK_TOKEN = os.getenv("WEBHOOK_TOKEN", "").strip()
SERVICE_NAME = "delno-mail"
SMTP_HOST = os.getenv("MAIL_SMTP_HOST", "").strip() or os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("MAIL_SMTP_PORT", os.getenv("SMTP_PORT", "465")) or "465")
SMTP_USER = os.getenv("MAIL_USERNAME", "").strip() or os.getenv("SMTP_USER", "").strip()
SMTP_PASSWORD = os.getenv("MAIL_PASSWORD", "").strip() or os.getenv("SMTP_PASSWORD", "").strip()
MAIL_FROM = os.getenv("MAIL_FROM", "").strip() or SMTP_USER
MAIL_FROM_NAME = os.getenv("MAIL_FROM_NAME", "DELNO").strip() or "DELNO"
FORCE_DRY_RUN = os.getenv("MAIL_FORCE_DRY_RUN", "").lower() in ("1", "true", "yes", "on")

app = FastAPI(title="DELNO Mail Gateway", version="0.1.0")


def _check_token(x_webhook_token: Optional[str] = None) -> None:
    # Fail closed: an empty token must not open the API.
    if not WEBHOOK_TOKEN or (x_webhook_token or "").strip() != WEBHOOK_TOKEN:
        raise HTTPException(status_code=401, detail="unauthorized")


def smtp_configured() -> bool:
    return bool(SMTP_HOST and SMTP_USER and SMTP_PASSWORD and MAIL_FROM)


class MailSendRequest(BaseModel):
    to: str = Field(..., min_length=3, max_length=320)
    subject: str = Field(..., min_length=1, max_length=500)
    body: str = Field(..., min_length=1, max_length=50000)
    tenant_slug: str = Field(default="", max_length=120)
    dry_run: bool = False


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": SERVICE_NAME,
        "smtp_configured": smtp_configured(),
        "force_dry_run": FORCE_DRY_RUN,
        "creds_policy": "tools_first",
        "capabilities": ["send"],
    }


@app.post("/api/mail/send")
def mail_send(
    req: MailSendRequest,
    x_webhook_token: Optional[str] = Header(None),
):
    _check_token(x_webhook_token)
    to = req.to.strip()
    subject = req.subject.strip()
    body = req.body.strip()
    dry = bool(req.dry_run or FORCE_DRY_RUN or not smtp_configured())

    if dry:
        logger.info(
            "[MAIL STUB] to=%s subject=%r tenant=%s",
            to,
            subject[:80],
            req.tenant_slug,
        )
        return {
            "ok": True,
            "queued": False,
            "sent": False,
            "stub": True,
            "dry_run": True,
            "to": to,
            "subject": subject[:200],
            "body_preview": body[:240],
            "tenant_slug": req.tenant_slug,
            "message": "Draft staged locally; SMTP not wired (tools-first)",
        }

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = f"{MAIL_FROM_NAME} <{MAIL_FROM}>"
    msg["To"] = to
    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30) as smtp:
            smtp.login(SMTP_USER, SMTP_PASSWORD)
            smtp.sendmail(MAIL_FROM, [to], msg.as_string())
    except Exception as exc:
        logger.exception("[MAIL SEND ERROR] %s", exc)
        return {
            "ok": False,
            "queued": False,
            "sent": False,
            "error": "smtp_error",
            "message": str(exc)[:300],
        }

    return {
        "ok": True,
        "queued": True,
        "sent": True,
        "stub": False,
        "to": to,
        "subject": subject[:200],
        "tenant_slug": req.tenant_slug,
        "message": f"Sent to {to}",
    }
