"""IMAP watcher: detect replies to outreach on office@ inbox."""

from __future__ import annotations

import email
import email.header
import email.utils
import imaplib
import logging
import os
import re
import smtplib
import threading
import time
from email.mime.text import MIMEText
from email.utils import formataddr, make_msgid
from typing import Any

from bitrix_client import BitrixClient, normalize_email
from outbox import OutboxStore

logger = logging.getLogger("ava-outreach.replies")

_ANGLE_RE = re.compile(r"<([^>]+)>")
_BOUNCE_FROM_RE = re.compile(
    r"(mailer-daemon|postmaster|mail-daemon|noreply-dsn|bounce)@",
    re.IGNORECASE,
)


def _env_true(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).lower() in ("1", "true", "yes", "on")


def _looks_like_bounce(msg: email.message.Message, from_email: str | None) -> bool:
    if from_email and _BOUNCE_FROM_RE.search(from_email):
        return True
    ctype = (msg.get_content_type() or "").lower()
    if ctype in {"multipart/report", "message/delivery-status"}:
        return True
    auto = (msg.get("Auto-Submitted") or "").lower()
    if auto and auto != "no":
        subj = (_decode_header(msg.get("Subject")) or "").lower()
        if any(
            k in subj
            for k in (
                "undeliverable",
                "delivery status",
                "delivery failure",
                "mail delivery failed",
                "returned mail",
                "failure notice",
                "не доставлено",
                "недоставлен",
            )
        ):
            return True
    if msg.get("X-Failed-Recipients"):
        return True
    return False


def _bounce_reason(msg: email.message.Message) -> str:
    subj = _decode_header(msg.get("Subject")) or ""
    preview = _plain_preview(msg, limit=400)
    failed = (msg.get("X-Failed-Recipients") or "").strip()
    parts = [p for p in (subj, failed, preview) if p]
    return " | ".join(parts)[:500]


def imap_configured() -> bool:
    user = (os.getenv("MAIL_USERNAME") or "").strip()
    password = os.getenv("MAIL_PASSWORD") or ""
    host = (os.getenv("IMAP_HOST") or "").strip() or "imap.mail.ru"
    return bool(user and password and host)


def _decode_header(value: str | None) -> str:
    if not value:
        return ""
    parts = email.header.decode_header(value)
    out: list[str] = []
    for chunk, enc in parts:
        if isinstance(chunk, bytes):
            out.append(chunk.decode(enc or "utf-8", errors="replace"))
        else:
            out.append(chunk)
    return "".join(out)


def _extract_address(raw: str | None) -> str | None:
    if not raw:
        return None
    _name, addr = email.utils.parseaddr(raw)
    return normalize_email(addr)


def _message_id(msg: email.message.Message) -> str | None:
    mid = (msg.get("Message-ID") or msg.get("Message-Id") or "").strip()
    if not mid:
        return None
    m = _ANGLE_RE.search(mid)
    return (m.group(1) if m else mid).strip().lower()


def _plain_preview(msg: email.message.Message, limit: int = 1200) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "")
            if ctype == "text/plain" and "attachment" not in disp.lower():
                payload = part.get_payload(decode=True) or b""
                charset = part.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")[:limit]
        return ""
    if msg.get_content_type() == "text/plain":
        payload = msg.get_payload(decode=True) or b""
        charset = msg.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace")[:limit]
    return ""


def _send_notify(*, subject: str, body: str) -> None:
    host = os.getenv("MAIL_SMTP_HOST", "").strip()
    port = int(os.getenv("MAIL_SMTP_PORT", "465"))
    user = os.getenv("MAIL_USERNAME", "").strip()
    password = os.getenv("MAIL_PASSWORD", "")
    to_addr = (
        os.getenv("REPLY_NOTIFY_EMAIL")
        or os.getenv("MAIL_REPLY_TO")
        or user
    ).strip()
    if not (host and user and password and to_addr):
        raise RuntimeError("SMTP not configured for reply notify")

    msg = MIMEText(body, "plain", "utf-8")
    msg["From"] = formataddr((os.getenv("MAIL_FROM_NAME", "Quantum Labs Outreach"), user))
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg["Message-ID"] = make_msgid(domain=user.split("@")[-1] if "@" in user else "localhost")
    with smtplib.SMTP_SSL(host, port, timeout=20) as server:
        server.login(user, password)
        server.send_message(msg)


def check_replies(
    store: OutboxStore,
    bitrix: BitrixClient | None = None,
    *,
    limit: int = 40,
) -> dict[str, Any]:
    """Poll IMAP INBOX for new mail from addresses we previously emailed."""
    if not imap_configured():
        return {"ok": False, "error": "IMAP not configured (MAIL_USERNAME/PASSWORD)", "matched": 0}

    host = (os.getenv("IMAP_HOST") or "imap.mail.ru").strip()
    port = int(os.getenv("IMAP_PORT", "993"))
    user = os.getenv("MAIL_USERNAME", "").strip()
    password = os.getenv("MAIL_PASSWORD", "")
    mailbox = (os.getenv("IMAP_MAILBOX") or "INBOX").strip()
    our = normalize_email(user) or user.lower()
    notify = _env_true("REPLY_NOTIFY_ENABLED", "true")
    write_bitrix = _env_true("REPLY_BITRIX_EVENT", "true")

    matched = 0
    scanned = 0
    skipped_seen = 0
    results: list[dict[str, Any]] = []

    imap = imaplib.IMAP4_SSL(host, port)
    try:
        imap.login(user, password)
        typ, _ = imap.select(mailbox, readonly=True)
        if typ != "OK":
            return {"ok": False, "error": f"cannot select mailbox {mailbox}", "matched": 0}

        # Recent messages only — UNSEEN first, fallback ALL limited by SEARCH ALL + fetch last N
        typ, data = imap.search(None, "UNSEEN")
        ids: list[bytes] = []
        if typ == "OK" and data and data[0]:
            ids = data[0].split()
        if not ids:
            typ, data = imap.search(None, "ALL")
            if typ == "OK" and data and data[0]:
                ids = data[0].split()[-limit:]
        else:
            ids = ids[-limit:]

        for num in ids:
            typ, fetched = imap.fetch(num, "(RFC822)")
            if typ != "OK" or not fetched or not fetched[0]:
                continue
            raw = fetched[0][1]
            if not isinstance(raw, (bytes, bytearray)):
                continue
            scanned += 1
            msg = email.message_from_bytes(raw)
            mid = _message_id(msg)
            if not mid:
                # synthesize stable id from UID + date
                mid = f"uid-{num.decode()}-{(msg.get('Date') or '').strip()}".lower()
            if store.inbound_seen(mid):
                skipped_seen += 1
                continue

            from_email = _extract_address(msg.get("From"))
            if not from_email or from_email == our:
                # Bounce / DSN often From mailer-daemon — try Message-ID chain first
                if _looks_like_bounce(msg, from_email):
                    try:
                        from modules.tracking import TrackingStore

                        tstore = TrackingStore()
                        ev = None
                        for hdr in ("In-Reply-To", "References"):
                            raw_hdr = msg.get(hdr) or ""
                            for token in raw_hdr.replace(",", " ").split():
                                token = token.strip().strip("<>")
                                if not token:
                                    continue
                                ev = tstore.by_message_id(token)
                                if ev:
                                    break
                            if ev:
                                break
                        if ev:
                            reason = _bounce_reason(msg)
                            try:
                                from modules.deliverability import DeliverabilityStore
                                from modules.sequences import SequenceStore

                                dstore = DeliverabilityStore()
                                classified = dstore.handle_bounce(
                                    email=ev.email, raw_reason=reason
                                )
                                tstore.record_bounce(
                                    ev.id,
                                    reason=f"{classified.category}:{classified.reason}|{reason}"[
                                        :500
                                    ],
                                )
                                store.mark_bounced(
                                    ev.outbox_id,
                                    reason=f"{classified.category}:{classified.reason}",
                                )
                                if classified.category in ("hard", "unknown", "policy", "auth"):
                                    SequenceStore().stop(
                                        email=ev.email, reason=f"bounce:{classified.category}"
                                    )
                            except Exception:  # noqa: BLE001
                                tstore.record_bounce(ev.id, reason=reason)
                                store.mark_bounced(ev.outbox_id, reason=reason)
                                try:
                                    from modules.deliverability import DeliverabilityStore

                                    DeliverabilityStore().add_suppression(
                                        ev.email, reason="bounce", source="imap-dsn"
                                    )
                                except Exception:  # noqa: BLE001
                                    pass
                            store.record_inbound(
                                message_id=mid,
                                from_email=from_email or "mailer-daemon",
                                subject=_decode_header(msg.get("Subject")),
                                outbox_id=ev.outbox_id,
                                deal_id=None,
                                notified=False,
                            )
                            matched += 1
                            results.append(
                                {
                                    "message_id": mid,
                                    "from": from_email or "mailer-daemon",
                                    "subject": _decode_header(msg.get("Subject")),
                                    "outbox_id": ev.outbox_id,
                                    "bounce": True,
                                    "bounce_reason": reason,
                                }
                            )
                            logger.info(
                                "outreach bounce matched outbox=%s email=%s",
                                ev.outbox_id,
                                ev.email,
                            )
                            continue
                    except Exception:  # noqa: BLE001
                        logger.debug("bounce resolve skipped", exc_info=True)
                store.record_inbound(
                    message_id=mid,
                    from_email=from_email or "",
                    subject=_decode_header(msg.get("Subject")),
                    outbox_id=None,
                    deal_id=None,
                    notified=False,
                )
                continue

            # Bounce from a non-daemon address still possible
            if _looks_like_bounce(msg, from_email):
                try:
                    from modules.tracking import TrackingStore

                    tstore = TrackingStore()
                    ev = None
                    for hdr in ("In-Reply-To", "References"):
                        raw_hdr = msg.get(hdr) or ""
                        for token in raw_hdr.replace(",", " ").split():
                            token = token.strip().strip("<>")
                            if not token:
                                continue
                            ev = tstore.by_message_id(token)
                            if ev:
                                break
                        if ev:
                            break
                    if ev:
                        reason = _bounce_reason(msg)
                        try:
                            from modules.deliverability import DeliverabilityStore

                            classified = DeliverabilityStore().handle_bounce(
                                email=ev.email, raw_reason=reason
                            )
                            tstore.record_bounce(
                                ev.id,
                                reason=f"{classified.category}:{classified.reason}|{reason}"[
                                    :500
                                ],
                            )
                            store.mark_bounced(
                                ev.outbox_id,
                                reason=f"{classified.category}:{classified.reason}",
                            )
                        except Exception:  # noqa: BLE001
                            tstore.record_bounce(ev.id, reason=reason)
                            store.mark_bounced(ev.outbox_id, reason=reason)
                        store.record_inbound(
                            message_id=mid,
                            from_email=from_email,
                            subject=_decode_header(msg.get("Subject")),
                            outbox_id=ev.outbox_id,
                            deal_id=None,
                            notified=False,
                        )
                        matched += 1
                        results.append(
                            {
                                "message_id": mid,
                                "from": from_email,
                                "outbox_id": ev.outbox_id,
                                "bounce": True,
                            }
                        )
                        continue
                except Exception:  # noqa: BLE001
                    logger.debug("bounce resolve skipped", exc_info=True)

            row = store.find_outreach_by_email(from_email)
            # Chain matching: In-Reply-To / References → send_events.message_id
            # Plus: Delivered-To / To / Cc with office+au.<id>.<sig>@
            if row is None:
                try:
                    from modules.tracking import TrackingStore, parse_plus_address

                    tstore = TrackingStore()
                    for hdr in ("In-Reply-To", "References"):
                        raw_hdr = msg.get(hdr) or ""
                        for token in raw_hdr.replace(",", " ").split():
                            token = token.strip().strip("<>")
                            if not token:
                                continue
                            ev = tstore.by_message_id(token)
                            if ev:
                                row = store.get_row(ev.outbox_id)
                                break
                        if row:
                            break
                    if row is None:
                        for hdr in ("Delivered-To", "To", "Cc", "X-Original-To"):
                            raw_hdr = msg.get(hdr) or ""
                            for part in raw_hdr.split(","):
                                addr = _extract_address(part) or part.strip()
                                parsed = parse_plus_address(addr)
                                if parsed and parsed.get("valid_sig"):
                                    row = store.get_row(int(parsed["outbox_id"]))
                                    if row:
                                        break
                            if row:
                                break
                except Exception:  # noqa: BLE001
                    logger.debug("tracking resolve skipped", exc_info=True)

            if row is None:
                store.record_inbound(
                    message_id=mid,
                    from_email=from_email,
                    subject=_decode_header(msg.get("Subject")),
                    outbox_id=None,
                    deal_id=None,
                    notified=False,
                )
                continue

            # Handle unsubscribe via plus kind
            try:
                from modules.tracking import parse_plus_address
                from modules.deliverability import DeliverabilityStore

                for hdr in ("Delivered-To", "To"):
                    raw_hdr = msg.get(hdr) or ""
                    for part in raw_hdr.split(","):
                        addr = _extract_address(part) or part.strip()
                        parsed = parse_plus_address(addr)
                        if parsed and parsed.get("kind") == "unsub" and parsed.get("valid_sig"):
                            DeliverabilityStore().add_suppression(
                                from_email, reason="unsubscribe", source="plus-unsub"
                            )
                            store.set_status(row.id, "skipped", error="unsubscribe")
            except Exception:  # noqa: BLE001
                pass

            subject = _decode_header(msg.get("Subject")) or "(без темы)"
            preview = _plain_preview(msg)
            from modules.replies.classify import classify_reply

            classified = classify_reply(subject=subject, body=preview, msg=msg)
            item: dict[str, Any] = {
                "message_id": mid,
                "from": from_email,
                "subject": subject,
                "outbox_id": row.id,
                "deal_id": row.deal_id,
                "company_id": row.company_id,
                "company_title": row.contact_name,
                "classification": classified.classification,
                "classification_confidence": classified.confidence,
            }

            # Stop sequence / policy on actionable classes
            try:
                from modules.sequences import SequenceStore
                from modules.policy import ContactPolicyStore

                if classified.should_stop_sequence:
                    SequenceStore().stop(
                        email=row.email or from_email,
                        company_id=row.company_id or None,
                        reason=classified.classification,
                    )
                if classified.classification == "unsubscribe":
                    ContactPolicyStore().note_unsubscribe(row.company_id or "")
                    try:
                        from modules.deliverability import DeliverabilityStore

                        DeliverabilityStore().add_suppression(
                            from_email, reason="unsubscribe", source="reply-classify"
                        )
                    except Exception:  # noqa: BLE001
                        pass
                elif classified.classification in (
                    "positive_interest",
                    "human_unclassified",
                    "forwarded",
                    "negative",
                ):
                    if row.company_id:
                        ContactPolicyStore().note_reply(row.company_id)
            except Exception:  # noqa: BLE001
                logger.debug("sequence/policy on reply failed", exc_info=True)

            if write_bitrix and bitrix:
                deal_id = row.deal_id
                humanish = classified.classification in (
                    "positive_interest",
                    "human_unclassified",
                    "forwarded",
                    "negative",
                    "unsubscribe",
                )
                try:
                    if humanish and not deal_id and row.company_id:
                        # Qualification signal: human reply → create deal once
                        deal_id = str(
                            bitrix.create_deal(
                                title=f"Ответ на outreach: {row.contact_name or from_email}",
                                company_id=row.company_id,
                                assigned_by_id=int(
                                    os.getenv("BITRIX_ASSIGNED_BY_ID", "1") or "1"
                                ),
                                stage_id=(
                                    os.getenv("BITRIX_DEAL_STAGE_ID", "NEW") or "NEW"
                                ).strip()
                                or "NEW",
                                comments=(
                                    f"Автосоздание после ответа на outreach.\n"
                                    f"Класс: {classified.classification}\n"
                                    f"От: {from_email}\nТема: {subject}\n\n{preview[:1500]}"
                                ),
                                source_id="EMAIL",
                            )
                        )
                        store.mark(row.id, "replied", deal_id=deal_id)
                        item["deal_id"] = deal_id
                        item["deal_created"] = True
                    if deal_id and humanish:
                        bitrix.add_timeline_comment(
                            deal_id,
                            (
                                f"📩 Ответ на outreach с {from_email}\n"
                                f"Класс: {classified.classification} "
                                f"({classified.confidence:.2f})\n"
                                f"Тема: {subject}\n\n"
                                f"--- Превью ---\n{preview[:2000]}"
                            ),
                            entity_type="deal",
                        )
                        item["bitrix"] = "timeline_ok"
                    elif row.company_id and humanish:
                        bitrix.add_timeline_comment(
                            row.company_id,
                            (
                                f"📩 Ответ на outreach с {from_email}\n"
                                f"Класс: {classified.classification}\n"
                                f"Тема: {subject}\n\n"
                                f"--- Превью ---\n{preview[:2000]}"
                            ),
                            entity_type="company",
                        )
                        item["bitrix"] = "company_timeline_ok"
                    if classified.should_create_task and humanish:
                        tid = bitrix.create_task(
                            title=f"Outreach ответ: {from_email}",
                            description=(
                                f"Классификация: {classified.classification}\n"
                                f"От: {from_email}\nТема: {subject}\n\n{preview[:2000]}"
                            ),
                            responsible_id=int(
                                os.getenv("BITRIX_ASSIGNED_BY_ID", "1") or "1"
                            ),
                            priority="2"
                            if classified.classification == "positive_interest"
                            else "1",
                            crm_company_id=row.company_id or None,
                            crm_deal_id=deal_id,
                        )
                        if tid:
                            item["bitrix_task_id"] = tid
                except Exception as exc:  # noqa: BLE001
                    logger.warning("bitrix reply timeline failed: %s", exc)
                    item["bitrix_error"] = str(exc)[:300]

            # Reply inbox
            try:
                from modules.replies import ReplyInboxStore

                inbox_row = ReplyInboxStore().add(
                    message_id=mid,
                    from_email=from_email,
                    subject=subject,
                    preview=preview,
                    classified=classified,
                    outbox_id=row.id,
                    company_id=row.company_id,
                    deal_id=item.get("deal_id") or row.deal_id,
                )
                if inbox_row and item.get("bitrix_task_id"):
                    ReplyInboxStore().mark_processed(
                        int(inbox_row["id"]),
                        bitrix_task_id=str(item["bitrix_task_id"]),
                    )
                item["inbox_id"] = (inbox_row or {}).get("id")
            except Exception:  # noqa: BLE001
                logger.debug("reply inbox failed", exc_info=True)

            notified_ok = False
            if notify and classified.should_notify:
                try:
                    _send_notify(
                        subject=f"[Outreach] {classified.classification}: {from_email}",
                        body=(
                            f"Получен ответ на outreach-письмо.\n\n"
                            f"Класс: {classified.classification} ({classified.confidence:.2f})\n"
                            f"От: {from_email}\n"
                            f"Компания: {row.contact_name} (company_id={row.company_id})\n"
                            f"Сделка Bitrix: {item.get('deal_id') or row.deal_id or '—'}\n"
                            f"Тема: {subject}\n\n"
                            f"--- Превью ---\n{preview}\n"
                        ),
                    )
                    notified_ok = True
                    item["notified"] = True
                except Exception as exc:  # noqa: BLE001
                    logger.warning("reply notify email failed: %s", exc)
                    item["notify_error"] = str(exc)[:300]

            if classified.classification not in ("automatic", "out_of_office", "bounce"):
                store.mark_replied(row.id)
            try:
                from modules.tracking import TrackingStore

                tstore = TrackingStore()
                for hdr in ("In-Reply-To", "References"):
                    raw_hdr = msg.get(hdr) or ""
                    for token in raw_hdr.replace(",", " ").split():
                        token = token.strip().strip("<>")
                        if not token:
                            continue
                        ev = tstore.by_message_id(token)
                        if ev:
                            tstore.mark_replied(ev.id)
                            break
                    else:
                        continue
                    break
                else:
                    for ev in tstore.by_outbox_id(row.id):
                        tstore.mark_replied(ev.id)
                        break
            except Exception:  # noqa: BLE001
                logger.debug("tracking mark_replied skipped", exc_info=True)
            store.record_inbound(
                message_id=mid,
                from_email=from_email,
                subject=subject,
                outbox_id=row.id,
                deal_id=row.deal_id,
                notified=notified_ok,
            )
            matched += 1
            results.append(item)
            logger.info("outreach reply matched from=%s deal=%s", from_email, row.deal_id)
    finally:
        try:
            imap.logout()
        except Exception:  # noqa: BLE001
            pass

    return {
        "ok": True,
        "scanned": scanned,
        "matched": matched,
        "skipped_seen": skipped_seen,
        "results": results,
    }


class ReplyWatchThread(threading.Thread):
    """Daemon poller started from FastAPI lifespan."""

    def __init__(self, store: OutboxStore, webhook_url: str) -> None:
        super().__init__(daemon=True, name="ava-outreach-reply-watch")
        self.store = store
        self.webhook_url = webhook_url
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        interval = int(os.getenv("REPLY_WATCH_INTERVAL_SECONDS", "120"))
        logger.info("reply watch started interval=%ss", interval)
        while not self._stop.is_set():
            if _env_true("REPLY_WATCH_ENABLED", "true") and imap_configured():
                bitrix = BitrixClient(self.webhook_url) if self.webhook_url else None
                try:
                    report = check_replies(self.store, bitrix)
                    if report.get("matched"):
                        logger.info("reply watch matched=%s", report.get("matched"))
                except Exception:  # noqa: BLE001
                    logger.exception("reply watch cycle failed")
                finally:
                    if bitrix:
                        bitrix.close()
            self._stop.wait(interval)
        logger.info("reply watch stopped")
