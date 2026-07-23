"""IMAP mail ingest — inbound + outbound (Sent)."""

from __future__ import annotations

import email
import email.header
import email.utils
import imaplib
import logging
import os
import re
from typing import Any

from brain_platform.db.repository import BrainRepository

logger = logging.getLogger("brain.ingest.mail")

_ANGLE_RE = re.compile(r"<([^>]+)>")


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def imap_configured() -> bool:
    return bool(_env("MAIL_USERNAME") and os.getenv("MAIL_PASSWORD") and (_env("IMAP_HOST") or "imap.mail.ru"))


def _decode_header(value: str | None) -> str:
    if not value:
        return ""
    parts = email.header.decode_header(value)
    out: list[str] = []
    for chunk, enc in parts:
        if isinstance(chunk, bytes):
            out.append(chunk.decode(enc or "utf-8", errors="replace"))
        else:
            out.append(chunk or "")
    return "".join(out)


def _addrs(raw: str | None) -> list[str]:
    if not raw:
        return []
    out = []
    for name, addr in email.utils.getaddresses([raw]):
        a = (addr or "").strip().lower()
        if a:
            out.append(a)
    return out


def _message_id(msg: email.message.Message) -> str | None:
    mid = (msg.get("Message-ID") or msg.get("Message-Id") or "").strip()
    if not mid:
        return None
    m = _ANGLE_RE.search(mid)
    return (m.group(1) if m else mid).strip().lower()


def _plain_body(msg: email.message.Message, limit: int = 50000) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "")
            if ctype == "text/plain" and "attachment" not in disp.lower():
                payload = part.get_payload(decode=True) or b""
                charset = part.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")[:limit]
        # fallback html stripped lightly
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True) or b""
                charset = part.get_content_charset() or "utf-8"
                html = payload.decode(charset, errors="replace")
                return re.sub(r"<[^>]+>", " ", html)[:limit]
        return ""
    payload = msg.get_payload(decode=True) or b""
    charset = msg.get_content_charset() or "utf-8"
    return payload.decode(charset, errors="replace")[:limit]


def _open_imap() -> imaplib.IMAP4_SSL:
    host = _env("IMAP_HOST") or "imap.mail.ru"
    port = int(_env("IMAP_PORT") or "993")
    user = _env("MAIL_USERNAME")
    password = os.getenv("MAIL_PASSWORD") or ""
    client = imaplib.IMAP4_SSL(host, port)
    client.login(user, password)
    return client


def _folder_candidates(direction: str) -> list[str]:
    if direction == "inbound":
        raw = _env("BRAIN_IMAP_INBOX") or _env("IMAP_MAILBOX") or "INBOX"
        return [f.strip() for f in raw.split(",") if f.strip()]
    raw = _env("BRAIN_IMAP_SENT") or "Sent,Sent Items,Отправленные,&BB4EQgQ,INBOX.Sent"
    return [f.strip() for f in raw.split(",") if f.strip()]


def ingest_mailbox(
    repo: BrainRepository,
    *,
    tenant_id: str,
    direction: str = "both",
    limit: int = 200,
) -> dict[str, Any]:
    """Fetch recent messages and upsert into brain store."""
    if not imap_configured():
        return {"ok": False, "error": "imap_not_configured", "created": 0}

    directions = ["inbound", "outbound"] if direction == "both" else [direction]
    client = _open_imap()
    created = 0
    skipped = 0
    errors: list[str] = []

    try:
        for d in directions:
            folders = _folder_candidates(d)
            selected = None
            for folder in folders:
                typ, _ = client.select(f'"{folder}"', readonly=True)
                if typ == "OK":
                    selected = folder
                    break
            if not selected:
                errors.append(f"no_folder_for_{d}:{folders}")
                continue

            typ, data = client.search(None, "ALL")
            if typ != "OK" or not data or not data[0]:
                continue
            ids = data[0].split()
            ids = ids[-limit:]
            for num in ids:
                typ, msg_data = client.fetch(num, "(RFC822)")
                if typ != "OK" or not msg_data or not msg_data[0]:
                    continue
                raw = msg_data[0][1]
                msg = email.message_from_bytes(raw)
                mid = _message_id(msg)
                if not mid:
                    skipped += 1
                    continue
                subject = _decode_header(msg.get("Subject"))
                from_email = (_addrs(msg.get("From")) or [""])[0]
                to_emails = _addrs(msg.get("To"))
                cc_emails = _addrs(msg.get("Cc"))
                body = _plain_body(msg)
                date_tuple = email.utils.parsedate_to_datetime(msg.get("Date")) if msg.get("Date") else None
                sent_at = date_tuple.isoformat() if date_tuple else None
                # infer direction if folder ambiguous
                local_user = _env("MAIL_USERNAME").lower()
                dir_final = d
                if d == "outbound" or (from_email and from_email == local_user):
                    dir_final = "outbound"
                elif d == "inbound":
                    dir_final = "inbound"

                try:
                    result = repo.upsert_email_message(
                        tenant_id=tenant_id,
                        message_id=mid,
                        direction=dir_final,
                        subject=subject,
                        from_email=from_email or "unknown@unknown",
                        to_emails=to_emails or [local_user],
                        cc_emails=cc_emails,
                        body_text=body,
                        sent_at=sent_at,
                    )
                    if result.get("created"):
                        created += 1
                    else:
                        skipped += 1
                except Exception as exc:  # noqa: BLE001
                    logger.exception("ingest mail failed")
                    errors.append(f"{mid}:{exc}")
    finally:
        try:
            client.logout()
        except Exception:  # noqa: BLE001
            pass

    repo.set_ingest_state(f"mail:{direction}:last", f"created={created};skipped={skipped}")
    return {
        "ok": True,
        "created": created,
        "skipped": skipped,
        "errors": errors[:20],
    }
