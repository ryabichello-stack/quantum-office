"""Inbox thread view + operator reply from UI."""

from __future__ import annotations

import html
import os
import re
from typing import Any

from modules.replies import ReplyInboxStore
from outbox import OutboxStore
from sender import send_email, smtp_configured


def _default_outbox() -> OutboxStore:
    from core.paths import DATA_DIR

    return OutboxStore(DATA_DIR / "outbox.db")


def _re_subject(subject: str | None) -> str:
    s = (subject or "").strip() or "Re: outreach"
    if re.match(r"^(re|fwd?):\s", s, re.I):
        return s
    return f"Re: {s}"


def _plain_to_html(text: str) -> str:
    return f"<pre style=\"font-family:inherit;white-space:pre-wrap\">{html.escape(text)}</pre>"


def _our_email() -> str:
    return (os.getenv("MAIL_USERNAME", "") or "").strip().lower()


def build_inbox_thread(
    inbox_id: int,
    *,
    inbox: ReplyInboxStore | None = None,
    outbox: OutboxStore | None = None,
) -> dict[str, Any]:
    store = inbox or ReplyInboxStore()
    row = store.get(inbox_id)
    if not row:
        return {"ok": False, "error": "inbox_not_found"}

    peer = (row.get("from_email") or "").strip().lower()
    company_id = (row.get("company_id") or "").strip()
    outbox_id = row.get("outbox_id")
    messages: list[dict[str, Any]] = []

    if outbox_id:
        obox = outbox or _default_outbox()
        try:
            ob_row = obox.get_row(int(outbox_id))
        except (TypeError, ValueError):
            ob_row = None
        if ob_row:
            subject = ""
            try:
                from modules.tracking import TrackingStore

                events = TrackingStore().by_outbox_id(int(outbox_id))
                if events:
                    subject = events[0].subject or ""
            except Exception:  # noqa: BLE001
                subject = ""
            messages.append(
                {
                    "direction": "outbound",
                    "kind": "outreach",
                    "at": ob_row.sent_at or ob_row.updated_at or ob_row.created_at,
                    "from": _our_email(),
                    "to": ob_row.email,
                    "subject": subject or "Outreach",
                    "body": "Исходящее письмо outreach (тело — шаблон кампании на момент отправки).",
                    "message_id": ob_row.message_id or "",
                }
            )

    for item in store.list_by_contact(
        email=peer, company_id=company_id or None, limit=100
    ):
        messages.append(
            {
                "direction": "inbound",
                "kind": "reply",
                "at": item.get("created_at"),
                "from": item.get("from_email"),
                "to": _our_email(),
                "subject": item.get("subject") or "",
                "body": item.get("preview") or "",
                "message_id": item.get("message_id") or "",
                "classification": item.get("classification"),
                "inbox_id": item.get("id"),
                "processed": bool(item.get("processed")),
            }
        )

    for item in store.list_operator_replies(peer_email=peer, limit=50):
        messages.append(
            {
                "direction": "outbound",
                "kind": "operator",
                "at": item.get("created_at"),
                "from": _our_email(),
                "to": item.get("to_email"),
                "subject": item.get("subject") or "",
                "body": item.get("body") or "",
                "message_id": item.get("message_id") or "",
                "in_reply_to": item.get("in_reply_to") or "",
            }
        )

    messages.sort(key=lambda m: str(m.get("at") or ""))

    ref_ids: list[str] = []
    for m in messages:
        mid = (m.get("message_id") or "").strip().strip("<>")
        if mid:
            ref_ids.append(mid)

    enrichment: dict[str, Any] | None = None
    try:
        from modules.accounts import AccountStore

        enrichment = AccountStore().enrichment_context(
            email=peer or None,
            bitrix_company_id=company_id or None,
            classification=row.get("classification"),
            contact_name="",
            company_title="",
            create_if_missing=False,
        )
    except Exception:  # noqa: BLE001
        enrichment = None

    return {
        "ok": True,
        "inbox_id": inbox_id,
        "peer_email": peer,
        "company_id": company_id,
        "deal_id": row.get("deal_id"),
        "classification": row.get("classification"),
        "subject": row.get("subject"),
        "references": ref_ids,
        "messages": messages,
        "enrichment": enrichment,
    }


def send_inbox_reply(
    inbox_id: int,
    *,
    body: str,
    subject: str | None = None,
    mark_done: bool = True,
    inbox: ReplyInboxStore | None = None,
) -> dict[str, Any]:
    if not smtp_configured():
        return {"ok": False, "error": "smtp_not_configured"}

    text = (body or "").strip()
    if not text:
        return {"ok": False, "error": "body_required"}
    if len(text) > 20000:
        return {"ok": False, "error": "body_too_long"}

    store = inbox or ReplyInboxStore()
    row = store.get(inbox_id)
    if not row:
        return {"ok": False, "error": "inbox_not_found"}

    to_addr = (row.get("from_email") or "").strip().lower()
    if not to_addr:
        return {"ok": False, "error": "recipient_missing"}

    thread = build_inbox_thread(inbox_id, inbox=store)
    refs = thread.get("references") or []
    in_reply_to = (row.get("message_id") or "").strip().strip("<>")
    if in_reply_to and in_reply_to not in refs:
        refs = refs + [in_reply_to]
    references_hdr = " ".join(f"<{mid}>" for mid in refs if mid)

    subj = (subject or "").strip() or _re_subject(row.get("subject"))
    user = os.getenv("MAIL_USERNAME", "").strip()
    unsub = os.getenv("MAIL_REPLY_TO", user).strip() or user

    try:
        message_id = send_email(
            to=to_addr,
            subject=subj,
            plain=text,
            html=_plain_to_html(text),
            unsubscribe_mailto=unsub,
            in_reply_to=in_reply_to or None,
            references=references_hdr or None,
            include_list_unsubscribe=False,
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)[:500]}

    store.record_operator_reply(
        inbox_id=inbox_id,
        to_email=to_addr,
        subject=subj,
        body=text,
        message_id=message_id,
        in_reply_to=in_reply_to or None,
    )
    if mark_done:
        store.mark_processed(inbox_id)

    return {
        "ok": True,
        "message_id": message_id,
        "to": to_addr,
        "subject": subj,
        "marked_done": mark_done,
    }
