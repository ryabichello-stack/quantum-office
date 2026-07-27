"""IMAP mail ingest — inbound + outbound (Sent). Supports multiple mailboxes."""

from __future__ import annotations

import email
import email.header
import email.utils
import imaplib
import logging
import os
import re
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv

load_dotenv()

from brain_platform.db.repository import BrainRepository

logger = logging.getLogger("brain.ingest.mail")

_ANGLE_RE = re.compile(r"<([^>]+)>")


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


@dataclass(frozen=True)
class MailAccount:
    username: str
    password: str
    host: str = "imap.mail.ru"
    port: int = 993
    label: str = ""

    @property
    def id(self) -> str:
        return (self.label or self.username).strip().lower()


def configured_mail_accounts() -> list[MailAccount]:
    """Primary MAIL_* plus optional MAIL2_* … MAIL9_* accounts."""
    accounts: list[MailAccount] = []
    primary_user = _env("MAIL_USERNAME")
    primary_pass = os.getenv("MAIL_PASSWORD") or ""
    if primary_user and primary_pass:
        accounts.append(
            MailAccount(
                username=primary_user,
                password=primary_pass,
                host=_env("IMAP_HOST") or "imap.mail.ru",
                port=int(_env("IMAP_PORT") or "993"),
                label=_env("MAIL_LABEL") or primary_user,
            )
        )

    for i in range(2, 10):
        user = _env(f"MAIL{i}_USERNAME")
        password = os.getenv(f"MAIL{i}_PASSWORD") or ""
        if not user or not password:
            continue
        accounts.append(
            MailAccount(
                username=user,
                password=password,
                host=_env(f"MAIL{i}_IMAP_HOST") or _env("IMAP_HOST") or "imap.mail.ru",
                port=int(_env(f"MAIL{i}_IMAP_PORT") or _env("IMAP_PORT") or "993"),
                label=_env(f"MAIL{i}_LABEL") or user,
            )
        )
    return accounts


def imap_configured() -> bool:
    return bool(configured_mail_accounts())


def imap_account_usernames() -> list[str]:
    return [a.username for a in configured_mail_accounts()]


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


def _named_addrs(raw: str | None) -> list[tuple[str, str]]:
    """Return (display_name, email) pairs with cleaned addresses."""
    if not raw:
        return []
    out: list[tuple[str, str]] = []
    for name, addr in email.utils.getaddresses([raw]):
        a = (addr or "").strip().lower()
        if not a or "@" not in a:
            continue
        m = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", a)
        if not m:
            continue
        a = m.group(0).lower()
        display = _decode_header(name).strip().strip('"').strip("'")
        out.append((display, a))
    return out


def _addrs(raw: str | None) -> list[str]:
    return [addr for _, addr in _named_addrs(raw)]


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


def _open_imap(account: MailAccount) -> imaplib.IMAP4_SSL:
    client = imaplib.IMAP4_SSL(account.host, account.port)
    client.login(account.username, account.password)
    return client


def _folder_candidates(direction: str) -> list[str]:
    if direction == "inbound":
        raw = _env("BRAIN_IMAP_INBOX") or _env("IMAP_MAILBOX") or "INBOX"
        return [f.strip() for f in raw.split(",") if f.strip()]
    raw = _env("BRAIN_IMAP_SENT") or "Sent,Sent Items,Отправленные,&BB4EQgQ,INBOX.Sent"
    return [f.strip() for f in raw.split(",") if f.strip()]


def _select_folder(client: imaplib.IMAP4_SSL, folder: str) -> bool:
    """Select mailbox; ignore names that cannot be sent as IMAP arguments."""
    try:
        folder.encode("ascii")
    except UnicodeEncodeError:
        return False
    for candidate in (folder, f'"{folder}"'):
        try:
            typ, _ = client.select(candidate, readonly=True)
            if typ == "OK":
                return True
        except (UnicodeEncodeError, imaplib.IMAP4.error):
            continue
    return False


def _list_mailboxes(client: imaplib.IMAP4_SSL) -> list[str]:
    typ, data = client.list()
    if typ != "OK" or not data:
        return []
    names: list[str] = []
    for raw in data:
        if not raw:
            continue
        line = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
        m = re.search(r'"([^"]*)"\s*$', line)
        if m:
            names.append(m.group(1))
            continue
        parts = line.split()
        if parts:
            names.append(parts[-1].strip('"'))
    return names


def _ingest_one_account(
    repo: BrainRepository,
    account: MailAccount,
    *,
    tenant_id: str,
    direction: str,
    limit: int,
) -> dict[str, Any]:
    directions = ["inbound", "outbound"] if direction == "both" else [direction]
    client = _open_imap(account)
    created = 0
    skipped = 0
    errors: list[str] = []
    local_user = account.username.lower()

    try:
        available = _list_mailboxes(client)
        logger.info("imap %s mailboxes: %s", account.username, available[:30])

        for d in directions:
            folders = _folder_candidates(d)
            if d == "outbound":
                for name in available:
                    low = name.lower()
                    if (
                        "sent" in low
                        or name.startswith("&BB4EQgQ")
                        or "отправлен" in low
                    ):
                        folders.append(name)
            if d == "inbound":
                folders = ["INBOX", *folders]

            seen: set[str] = set()
            uniq_folders: list[str] = []
            for f in folders:
                if f not in seen:
                    seen.add(f)
                    uniq_folders.append(f)

            selected = None
            for folder in uniq_folders:
                if _select_folder(client, folder):
                    selected = folder
                    break
            if not selected:
                errors.append(f"no_folder_for_{d}:{uniq_folders[:8]}")
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
                from_named = _named_addrs(msg.get("From"))
                to_named = _named_addrs(msg.get("To"))
                cc_named = _named_addrs(msg.get("Cc"))
                from_email = from_named[0][1] if from_named else ""
                from_name = from_named[0][0] if from_named else ""
                to_emails = [a for _, a in to_named]
                cc_emails = [a for _, a in cc_named]
                participant_names = {
                    a: n for n, a in [*from_named, *to_named, *cc_named] if n and a
                }
                body = _plain_body(msg)
                date_tuple = (
                    email.utils.parsedate_to_datetime(msg.get("Date"))
                    if msg.get("Date")
                    else None
                )
                sent_at = date_tuple.isoformat() if date_tuple else None
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
                        from_name=from_name or None,
                        to_emails=to_emails or [local_user],
                        cc_emails=cc_emails,
                        participant_names=participant_names,
                        body_text=body,
                        sent_at=sent_at,
                    )
                    if result.get("created"):
                        created += 1
                    else:
                        skipped += 1
                except Exception as exc:  # noqa: BLE001
                    logger.exception("ingest mail failed account=%s", account.username)
                    errors.append(f"{account.username}:{mid}:{exc}")
    finally:
        try:
            client.logout()
        except Exception:  # noqa: BLE001
            pass

    return {
        "ok": True,
        "account": account.username,
        "created": created,
        "skipped": skipped,
        "errors": errors[:20],
    }


def ingest_mailbox(
    repo: BrainRepository,
    *,
    tenant_id: str,
    direction: str = "both",
    limit: int = 200,
) -> dict[str, Any]:
    """Fetch recent messages from all configured mailboxes and upsert into brain store."""
    accounts = configured_mail_accounts()
    if not accounts:
        return {"ok": False, "error": "imap_not_configured", "created": 0}

    created = 0
    skipped = 0
    errors: list[str] = []
    per_account: list[dict[str, Any]] = []

    for account in accounts:
        try:
            one = _ingest_one_account(
                repo,
                account,
                tenant_id=tenant_id,
                direction=direction,
                limit=limit,
            )
            per_account.append(one)
            created += int(one.get("created") or 0)
            skipped += int(one.get("skipped") or 0)
            errors.extend(one.get("errors") or [])
        except Exception as exc:  # noqa: BLE001
            logger.exception("imap account failed: %s", account.username)
            err = {"ok": False, "account": account.username, "error": str(exc)}
            per_account.append(err)
            errors.append(f"{account.username}:{exc}")

    repo.set_ingest_state(
        f"mail:{direction}:last",
        f"accounts={len(accounts)};created={created};skipped={skipped}",
    )
    return {
        "ok": all(a.get("ok") for a in per_account) if per_account else False,
        "created": created,
        "skipped": skipped,
        "accounts": [a.username for a in accounts],
        "per_account": per_account,
        "errors": errors[:40],
    }
