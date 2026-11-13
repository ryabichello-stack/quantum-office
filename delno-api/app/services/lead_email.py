"""Best-effort owner notification after a lead transaction is committed."""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.lead import Lead

logger = logging.getLogger(__name__)
_PENDING = "delno_pending_lead_emails"


def queue_lead_email(db: Session, lead: Lead) -> None:
    # Save plain values: ORM objects may expire or detach on commit.
    db.info.setdefault(_PENDING, []).append(
        {
            "id": str(lead.id),
            "source": lead.source or "website",
            "name": lead.name or "",
            "phone": lead.phone or "",
            "email": lead.email or "",
            "company": lead.company or "",
            "website": lead.website or "",
        }
    )


def _send_lead_email(lead: dict[str, str]) -> None:
    settings = get_settings()
    if not (
        settings.lead_smtp_host
        and settings.lead_smtp_user
        and settings.lead_smtp_password
        and settings.lead_smtp_from
        and settings.lead_notify_to
    ):
        return

    message = EmailMessage()
    message["From"] = settings.lead_smtp_from
    message["To"] = settings.lead_notify_to
    message["Subject"] = "DELNO: новая заявка"
    lines = [
        "Новая заявка DELNO",
        "",
        f"Источник: {lead['source']}",
        f"Имя: {lead['name']}",
        f"Телефон: {lead['phone']}",
    ]
    for label, key in (("Почта", "email"), ("Компания", "company"), ("Сайт", "website")):
        if lead[key]:
            lines.append(f"{label}: {lead[key]}")
    lines.extend(("", f"ID заявки: {lead['id']}"))
    message.set_content("\n".join(lines))

    if settings.lead_smtp_port == 465:
        smtp = smtplib.SMTP_SSL(settings.lead_smtp_host, settings.lead_smtp_port, timeout=10)
    else:
        smtp = smtplib.SMTP(settings.lead_smtp_host, settings.lead_smtp_port, timeout=10)
    with smtp:
        if settings.lead_smtp_port != 465:
            smtp.starttls()
        smtp.login(settings.lead_smtp_user, settings.lead_smtp_password)
        smtp.send_message(message)


@event.listens_for(Session, "after_commit")
def _notify_after_commit(db: Session) -> None:
    for lead in db.info.pop(_PENDING, []):
        try:
            _send_lead_email(lead)
        except Exception:
            logger.exception("DELNO lead email delivery failed: lead_id=%s", lead["id"])


@event.listens_for(Session, "after_rollback")
def _discard_after_rollback(db: Session) -> None:
    db.info.pop(_PENDING, None)
