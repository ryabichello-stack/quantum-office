"""IMAP mail ingest — inbound + outbound (Sent). Supports multiple mailboxes."""

from __future__ import annotations

import email
import email.header
import email.utils
import hashlib
import imaplib
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from dotenv import load_dotenv

load_dotenv()

from brain_platform.db.repository import BrainRepository
from brain_platform.ingest.extract_text import (
    extract_text_from_bytes,
    looks_like_connection_data,
)

logger = logging.getLogger("brain.ingest.mail")

_ANGLE_RE = re.compile(r"<([^>]+)>")
_SKIP_ATTACHMENT_NAMES = {
    "smime.p7s",
    "smime.p7m",
    "signature.asc",
    "winmail.dat",
}


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


def attachments_root() -> Path:
    raw = (_env("BRAIN_ATTACHMENTS_DIR") or "").strip()
    if raw:
        return Path(raw)
    data = (_env("BRAIN_DATA_DIR") or "").strip()
    if data:
        return Path(data) / "mail-attachments"
    return Path(__file__).resolve().parents[2] / "data" / "mail-attachments"


def _safe_filename(name: str) -> str:
    base = (name or "attachment").strip().replace("\x00", "")
    base = re.sub(r"[\\/]+", "_", base)
    base = re.sub(r"[^\w.\- ()а-яА-ЯёЁ]+", "_", base, flags=re.U).strip("._ ")
    return (base or "attachment")[:180]


def _iter_attachments(
    msg: email.message.Message,
) -> Iterator[tuple[str, str, bytes]]:
    """Yield (filename, content_type, payload_bytes) for attachment-like parts."""
    if not msg.is_multipart():
        return
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        disp = str(part.get("Content-Disposition") or "")
        filename = part.get_filename()
        if filename:
            filename = _decode_header(filename)
        ctype = part.get_content_type() or "application/octet-stream"
        is_attach = "attachment" in disp.lower() or bool(filename)
        # Also catch inline docs that are not body text/html
        if not is_attach:
            if ctype in ("text/plain", "text/html"):
                continue
            if not filename:
                continue
        if not filename:
            ext = {
                "application/pdf": ".pdf",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
            }.get(ctype, "")
            filename = f"attachment{ext}"
        if filename.lower() in _SKIP_ATTACHMENT_NAMES:
            continue
        payload = part.get_payload(decode=True) or b""
        if not payload:
            continue
        # Skip tiny inline images
        if ctype.startswith("image/") and len(payload) < 40_000 and "attachment" not in disp.lower():
            continue
        yield filename, ctype, payload


def _process_message_attachments(
    repo: BrainRepository,
    *,
    tenant_id: str,
    email_id: str,
    message_id: str,
    subject: str,
    body_text: str,
    msg: email.message.Message,
) -> dict[str, Any]:
    """Save + index attachments; promote connection settings for office-assistant."""
    root = attachments_root()
    mid_key = hashlib.sha1(message_id.encode("utf-8")).hexdigest()[:16]
    dest_dir = root / mid_key
    dest_dir.mkdir(parents=True, exist_ok=True)

    attachment_ids: list[str] = []
    indexed = 0
    promoted = 0
    encrypted = 0
    errors: list[str] = []
    connection_blobs: list[str] = []

    # Body itself may already contain bank connection settings.
    if looks_like_connection_data(body_text):
        connection_blobs.append(f"## Из тела письма\n\n{body_text[:12000]}")

    for filename, ctype, payload in _iter_attachments(msg):
        safe = _safe_filename(filename)
        path = dest_dir / safe
        # Avoid collisions
        if path.exists() and path.read_bytes() != payload:
            stem, suf = path.stem, path.suffix
            path = dest_dir / f"{stem}-{hashlib.sha1(payload).hexdigest()[:8]}{suf}"
        try:
            path.write_bytes(payload)
        except OSError as exc:
            errors.append(f"write:{safe}:{exc}")
            continue

        extracted = extract_text_from_bytes(payload, filename=safe, content_type=ctype)
        text = str(extracted.get("text") or "")
        if extracted.get("encrypted"):
            encrypted += 1
            text = f"(encrypted attachment: {safe}; cannot extract without password)"
        content_hash = hashlib.sha256(payload).hexdigest()
        is_conn = looks_like_connection_data(text)
        visibility = "company" if is_conn else "restricted"
        try:
            result = repo.upsert_file_asset(
                tenant_id=tenant_id,
                path=str(path.resolve()),
                filename=safe,
                content_hash=content_hash,
                source="mail_attachment",
                text_excerpt=text[:20000],
                visibility=visibility,
                acl={
                    "allow_users": [],
                    "allow_groups": ["group:management", "group:sales", "group:ops"],
                    "allow_services": [
                        "service:cursor-admin",
                        "service:text-secretary",
                        *(["service:voice-office"] if is_conn else []),
                    ],
                    "deny_users": [],
                    "deny_groups": [],
                },
            )
            fid = result.get("id")
            if fid:
                attachment_ids.append(fid)
            if not result.get("unchanged") and not result.get("skipped_duplicate_content"):
                indexed += 1
            if is_conn and text.strip():
                connection_blobs.append(f"## Вложение: {safe}\n\n{text[:12000]}")
        except Exception as exc:  # noqa: BLE001
            logger.warning("attachment index failed %s: %s", safe, exc)
            errors.append(f"index:{safe}:{exc}")

    if attachment_ids:
        try:
            repo.set_email_attachment_ids(email_id, attachment_ids)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"link:{exc}")

    if connection_blobs:
        title_hint = re.sub(r"^(re|fw|fwd|aw|sv|re\[\d+\]):\s*", "", subject or "", flags=re.I)
        title_hint = re.sub(r"\s+", " ", title_hint).strip()[:120] or "Данные для подключения"
        title = f"Данные для подключения: {title_hint}"
        try:
            repo.promote_connection_settings_doc(
                tenant_id=tenant_id,
                title=title,
                body="\n\n".join(connection_blobs)[:18000],
                source=f"mail-attachment:{message_id}",
                subject_hint=subject,
            )
            promoted += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("promote connection doc failed: %s", exc)
            errors.append(f"promote:{exc}")

    return {
        "attachments": len(attachment_ids),
        "indexed": indexed,
        "promoted": promoted,
        "encrypted": encrypted,
        "errors": errors[:10],
    }


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
    attachments_total = 0
    attachments_indexed = 0
    attachments_promoted = 0

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
                    email_id = str(result.get("id") or "")
                    if email_id:
                        att = _process_message_attachments(
                            repo,
                            tenant_id=tenant_id,
                            email_id=email_id,
                            message_id=mid,
                            subject=subject,
                            body_text=body,
                            msg=msg,
                        )
                        attachments_total += int(att.get("attachments") or 0)
                        attachments_indexed += int(att.get("indexed") or 0)
                        attachments_promoted += int(att.get("promoted") or 0)
                        if att.get("errors"):
                            errors.extend(
                                f"{account.username}:{mid}:{e}" for e in att["errors"]
                            )
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
        "attachments": attachments_total,
        "attachments_indexed": attachments_indexed,
        "attachments_promoted": attachments_promoted,
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
    attachments = 0
    attachments_indexed = 0
    attachments_promoted = 0
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
            attachments += int(one.get("attachments") or 0)
            attachments_indexed += int(one.get("attachments_indexed") or 0)
            attachments_promoted += int(one.get("attachments_promoted") or 0)
            errors.extend(one.get("errors") or [])
        except Exception as exc:  # noqa: BLE001
            logger.exception("imap account failed: %s", account.username)
            err = {"ok": False, "account": account.username, "error": str(exc)}
            per_account.append(err)
            errors.append(f"{account.username}:{exc}")

    repo.set_ingest_state(
        f"mail:{direction}:last",
        f"accounts={len(accounts)};created={created};skipped={skipped};"
        f"att={attachments};att_idx={attachments_indexed};promoted={attachments_promoted}",
    )
    return {
        "ok": all(a.get("ok") for a in per_account) if per_account else False,
        "created": created,
        "skipped": skipped,
        "attachments": attachments,
        "attachments_indexed": attachments_indexed,
        "attachments_promoted": attachments_promoted,
        "accounts": [a.username for a in accounts],
        "per_account": per_account,
        "errors": errors[:40],
    }
