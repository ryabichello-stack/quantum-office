"""Save outbound outreach mail into a dedicated IMAP folder (not system Sent).

Mail.ru / most providers do not put SMTP-only sends into «Отправленные».
After a successful SMTP send we APPEND the same RFC822 into a mailbox folder
such as «рассылка Outreach» so the operator can open and forward copies from webmail.
"""

from __future__ import annotations

import imaplib
import logging
import os
import time
from email.message import Message
from email.utils import formatdate
from typing import Any

logger = logging.getLogger("ava-outreach.imap_sent")

DEFAULT_FOLDER = "рассылка Outreach"


def _env_true(name: str, default: str = "true") -> bool:
    return (os.getenv(name, default) or default).strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def imap_save_sent_enabled() -> bool:
    """Default on when IMAP credentials exist; set IMAP_SAVE_SENT=false to disable."""
    if not _env_true("IMAP_SAVE_SENT", "true"):
        return False
    user = (os.getenv("MAIL_USERNAME") or "").strip()
    password = os.getenv("MAIL_PASSWORD") or ""
    return bool(user and password)


def sent_folder_name() -> str:
    return (os.getenv("IMAP_SENT_FOLDER") or DEFAULT_FOLDER).strip() or DEFAULT_FOLDER


def encode_imap_utf7(s: str) -> str:
    """RFC 3501 modified UTF-7 for mailbox names (Cyrillic etc.)."""
    out: list[str] = []
    buf: list[str] = []

    def flush() -> None:
        if not buf:
            return
        raw = "".join(buf).encode("utf-16-be")
        import base64

        b64 = base64.b64encode(raw).decode("ascii").rstrip("=").replace("/", ",")
        out.append("&" + b64 + "-")
        buf.clear()

    for ch in s:
        o = ord(ch)
        if 0x20 <= o <= 0x7E:
            flush()
            if ch == "&":
                out.append("&-")
            else:
                out.append(ch)
        else:
            buf.append(ch)
    flush()
    return "".join(out)


def quote_mailbox(name: str) -> str:
    """Quote IMAP mailbox atom (required when name has spaces)."""
    if name.startswith('"') and name.endswith('"'):
        return name
    return '"' + name.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _folder_candidates(name: str) -> list[str]:
    """Try UTF-7 and raw forms — Mail.ru accepts both depending on server build."""
    enc = encode_imap_utf7(name)
    seen: list[str] = []
    for cand in (enc, name):
        if cand and cand not in seen:
            seen.append(cand)
    return seen


def ensure_mailbox_folder(imap: imaplib.IMAP4, folder: str) -> str:
    """CREATE folder if missing; return the name form that SELECT works with."""
    last_err = ""
    for cand in _folder_candidates(folder):
        quoted = quote_mailbox(cand)
        typ, _ = imap.select(quoted, readonly=True)
        if typ == "OK":
            try:
                imap.close()
            except Exception:  # noqa: BLE001
                pass
            return cand
        typ, data = imap.create(quoted)
        if typ == "OK":
            return cand
        detail = b" ".join(x for x in (data or []) if isinstance(x, (bytes, bytearray))).decode(
            "utf-8", errors="replace"
        )
        # already exists under another encoding
        if "exists" in detail.lower() or "already" in detail.lower():
            typ2, _ = imap.select(quoted, readonly=True)
            if typ2 == "OK":
                try:
                    imap.close()
                except Exception:  # noqa: BLE001
                    pass
                return cand
        last_err = f"{typ} {detail}".strip()
    raise RuntimeError(f"cannot create/select IMAP folder {folder!r}: {last_err}")


def _message_bytes(msg: Message) -> bytes:
    """Serialize for APPEND; ensure Date so clients sort correctly."""
    if not msg.get("Date"):
        try:
            msg["Date"] = formatdate(localtime=True)
        except Exception:  # noqa: BLE001
            pass
    raw = msg.as_bytes()
    # CRLF line endings are safer for IMAP APPEND
    return raw.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")


def append_sent_copy(msg: Message, *, folder: str | None = None) -> dict[str, Any]:
    """APPEND ``msg`` into the outreach sent folder. Never raises to callers of SMTP.

    Returns ``{ok, folder, error?}``. Failures are logged — SMTP already succeeded.
    """
    if not imap_save_sent_enabled():
        return {"ok": False, "skipped": True, "reason": "disabled"}

    host = (os.getenv("IMAP_HOST") or "imap.mail.ru").strip()
    port = int(os.getenv("IMAP_PORT") or "993")
    user = (os.getenv("MAIL_USERNAME") or "").strip()
    password = os.getenv("MAIL_PASSWORD") or ""
    folder_name = (folder or sent_folder_name()).strip()
    timeout = float(os.getenv("IMAP_TIMEOUT_SECONDS") or "20")

    imap: imaplib.IMAP4_SSL | None = None
    try:
        imap = imaplib.IMAP4_SSL(host, port, timeout=timeout)
        imap.login(user, password)
        resolved = ensure_mailbox_folder(imap, folder_name)
        payload = _message_bytes(msg)
        # \Seen — operator archive, not a new unread pile
        typ, data = imap.append(
            quote_mailbox(resolved),
            "(\\Seen)",
            imaplib.Time2Internaldate(time.time()),
            payload,
        )
        if typ != "OK":
            detail = b" ".join(x for x in (data or []) if isinstance(x, (bytes, bytearray))).decode(
                "utf-8", errors="replace"
            )
            raise RuntimeError(f"APPEND failed: {typ} {detail}".strip())
        logger.info("saved sent copy to IMAP folder %r (%s bytes)", folder_name, len(payload))
        return {"ok": True, "folder": folder_name, "imap_name": resolved, "bytes": len(payload)}
    except Exception as exc:  # noqa: BLE001
        logger.warning("IMAP save-sent failed (SMTP already ok): %s", exc)
        return {"ok": False, "folder": folder_name, "error": str(exc)}
    finally:
        if imap is not None:
            try:
                imap.logout()
            except Exception:  # noqa: BLE001
                pass
