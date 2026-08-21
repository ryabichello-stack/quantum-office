"""SMTP SSL sender (Mail.ru / same settings as ava-mailer)."""

from __future__ import annotations

import logging
import mimetypes
import os
import random
import smtplib
import time
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, make_msgid
from pathlib import Path
from typing import Any

from bitrix_client import BitrixClient  # noqa: I001
from outbox import OutboxStore
from templates import DEFAULT_SIGNATURE, default_logo_url, render_cooperation


def _render_letter(
    *,
    contact_name: str,
    company: str,
    website: str,
    phone: str,
    unsubscribe_mailto: str,
    unsubscribe_url: str | None = None,
    plain_template: str | None = None,
    html_template: str | None = None,
    settings: Any = None,
    callback_url: str | None = None,
) -> tuple[str, str]:
    from templates import public_base_url

    sig = (_cfg(settings, "OUTREACH_SIGNATURE", "") or "").strip() or DEFAULT_SIGNATURE
    logo_url = (_cfg(settings, "OUTREACH_LOGO_URL", "") or "").strip() or default_logo_url(
        lambda k: _cfg(settings, k, "")
    )
    logo_on = _cfg_bool(settings, "OUTREACH_LOGO_ENABLED", True)
    contact_email = (
        (_cfg(settings, "OUTREACH_CONTACT_EMAIL", "") or "").strip()
        or unsubscribe_mailto
        or os.getenv("MAIL_USERNAME")
        or "office@quantumlabs.ru"
    )
    return render_cooperation(
        contact_name=contact_name,
        company_name=company,
        website=website,
        phone=phone,
        unsubscribe_mailto=unsubscribe_mailto,
        unsubscribe_url=unsubscribe_url,
        plain_template=plain_template,
        html_template=html_template,
        signature_template=sig,
        logo_url=logo_url,
        logo_enabled=logo_on,
        contact_email=contact_email,
        icon_base_url=public_base_url(lambda k: _cfg(settings, k, "")),
        callback_url=callback_url,
    )


def _tracking_company_slug(
    *,
    contact_name: str | None = None,
    email: str | None = None,
    company_title: str | None = None,
) -> str:
    from modules.tracking import plus_company_slug

    # Prefer human company/contact label; fall back to recipient domain.
    return plus_company_slug(company_title or contact_name or email or "")


def _callback_url_for_row(
    *,
    outbox_id: int,
    email: str,
    settings: Any = None,
) -> str | None:
    try:
        from callback_cta import (
            callback_url_for,
            cta_enabled,
            make_callback_token,
        )

        if not cta_enabled(settings):
            return None
        token = make_callback_token(outbox_id=int(outbox_id or 0), email=email or "campaign")
        return callback_url_for(token, settings)
    except Exception:  # noqa: BLE001
        logger.debug("callback url build failed", exc_info=True)
        return None

logger = logging.getLogger("ava-outreach.sender")

_ASSETS_DIR = Path(__file__).resolve().parent / "assets"
_DEFAULT_PRESENTATION = _ASSETS_DIR / "quantum_payouts_presentation_small.pdf"


from presentations import resolve_presentation


def _presentation_path(settings: Any = None, pack_path: str | None = None) -> Path | None:
    """Resolve PDF: custom upload → pack asset → settings path → shared default."""
    pack_id = (_cfg(settings, "OUTREACH_SEQUENCE_PACK", "") or "").strip()
    settings_path = (pack_path or _cfg(settings, "OUTREACH_PRESENTATION_PDF", "") or "").strip()
    if not pack_id and settings_path:
        stem = Path(settings_path).stem
        if stem and stem != "quantum_payouts_presentation_small":
            pack_id = stem
    return resolve_presentation(pack_id=pack_id or None, settings_path=settings_path or None)


def _should_attach_presentation(
    settings: Any,
    *,
    step_wants: bool = False,
    force: bool | None = None,
) -> bool:
    if force is False:
        return False
    if force is True:
        return True
    if step_wants:
        # still respect explicit off
        if _cfg(settings, "OUTREACH_ATTACH_PRESENTATION", "") in ("0", "false", "no", "off"):
            return False
        return True
    return _cfg_bool(settings, "OUTREACH_ATTACH_PRESENTATION", False)


def _attachments_for_send(
    settings: Any,
    *,
    step_wants: bool = False,
    pack_presentation: str | None = None,
    force: bool | None = None,
) -> list[Path]:
    if not _should_attach_presentation(settings, step_wants=step_wants, force=force):
        return []
    path = _presentation_path(settings, pack_presentation)
    return [path] if path else []


def _cfg(settings: Any, key: str, default: str = "") -> str:
    if settings is not None:
        val = settings.get(key, default)
        return default if val is None else str(val)
    return os.getenv(key, default)


def _cfg_bool(settings: Any, key: str, default: bool = False) -> bool:
    if settings is not None:
        return settings.get_bool(key, default)
    return os.getenv(key, "true" if default else "false").lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _cfg_int(settings: Any, key: str, default: int) -> int:
    if settings is not None:
        return settings.get_int(key, default)
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default


def smtp_configured() -> bool:
    return bool(
        os.getenv("MAIL_SMTP_HOST")
        and os.getenv("MAIL_USERNAME")
        and os.getenv("MAIL_PASSWORD")
    )


def send_email(
    *,
    to: str,
    subject: str,
    plain: str,
    html: str,
    unsubscribe_mailto: str,
    reply_to: str | None = None,
    outreach_id: str | None = None,
    message_id: str | None = None,
    unsubscribe_url: str | None = None,
    attachments: list[Path] | None = None,
) -> str:
    """Send one message. Returns Message-ID (without angle brackets).

    If message_id is provided (pre-claim), reuse it for SMTP idempotency.
    Optional PDF/file attachments use multipart/mixed wrapping alternative body.
    """
    host = os.getenv("MAIL_SMTP_HOST", "").strip()
    port = int(os.getenv("MAIL_SMTP_PORT", "465"))
    user = os.getenv("MAIL_USERNAME", "").strip()
    password = os.getenv("MAIL_PASSWORD", "")
    from_name = os.getenv("MAIL_FROM_NAME", "Quantum Labs").strip()
    default_reply = os.getenv("MAIL_REPLY_TO", user).strip() or user
    reply = (reply_to or default_reply).strip()
    timeout = float(os.getenv("MAIL_SMTP_TIMEOUT_SECONDS", "20"))
    domain = user.split("@")[-1] if "@" in user else "localhost"
    if message_id:
        mid_raw = message_id.strip()
        if not mid_raw.startswith("<"):
            mid_header = f"<{mid_raw}>"
        else:
            mid_header = mid_raw
    else:
        mid_header = make_msgid(domain=domain)

    files = [p for p in (attachments or []) if p and Path(p).is_file()]
    if files:
        msg: MIMEMultipart = MIMEMultipart("mixed")
        alt = MIMEMultipart("alternative")
        alt.attach(MIMEText(plain, "plain", "utf-8"))
        alt.attach(MIMEText(html, "html", "utf-8"))
        msg.attach(alt)
        for path in files:
            path = Path(path)
            ctype, _ = mimetypes.guess_type(str(path))
            maintype, subtype = (ctype or "application/pdf").split("/", 1)
            with path.open("rb") as fh:
                part = MIMEApplication(fh.read(), _subtype=subtype if maintype == "application" else "octet-stream")
            part.add_header(
                "Content-Disposition",
                "attachment",
                filename=path.name,
            )
            msg.attach(part)
    else:
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText(plain, "plain", "utf-8"))
        msg.attach(MIMEText(html, "html", "utf-8"))

    msg["From"] = formataddr((from_name, user))
    msg["To"] = to
    msg["Subject"] = subject
    msg["Reply-To"] = reply
    msg["Message-ID"] = mid_header
    unsub_parts = [f"<mailto:{unsubscribe_mailto}?subject=unsubscribe>"]
    if unsubscribe_url:
        unsub_parts.insert(0, f"<{unsubscribe_url}>")
    msg["List-Unsubscribe"] = ", ".join(unsub_parts)
    if unsubscribe_url:
        msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    # Stable From identity (anti-ban): never rotate From; tracking goes to Reply-To / Message-ID.
    if outreach_id:
        msg["X-Outreach-Id"] = outreach_id

    with smtplib.SMTP_SSL(host, port, timeout=timeout) as server:
        server.login(user, password)
        server.send_message(msg)

    return mid_header.strip().strip("<>")


def make_outbound_message_id() -> str:
    user = os.getenv("MAIL_USERNAME", "").strip()
    domain = user.split("@")[-1] if "@" in user else "localhost"
    return make_msgid(domain=domain).strip().strip("<>")


def _delay_between_sends(settings: Any = None) -> None:
    lo = _cfg_int(settings, "OUTREACH_DELAY_MIN_SECONDS", 60)
    hi = _cfg_int(settings, "OUTREACH_DELAY_MAX_SECONDS", 180)
    if hi < lo:
        hi = lo
    seconds = random.randint(lo, hi) if hi > 0 else 0
    if seconds > 0:
        logger.info("delay %ss before next send", seconds)
        time.sleep(seconds)


def _record_bitrix_after_send(
    bitrix: BitrixClient,
    *,
    company_id: str,
    company_title: str,
    to_email: str,
    subject: str,
    plain: str,
    html: str,
    message_id: str | None = None,
    settings: Any = None,
) -> dict[str, Any]:
    """Record outreach send in Bitrix without creating a deal by default.

    Deal creation after SMTP floods the funnel. Default: timeline comment on
    the company (+ optional deal only if BITRIX_CREATE_DEAL=true legacy).
    """
    del html  # kept in signature for callers; timeline uses plain
    assigned = _cfg_int(settings, "BITRIX_ASSIGNED_BY_ID", 1)
    stage = (_cfg(settings, "BITRIX_DEAL_STAGE_ID", "NEW") or "NEW").strip() or "NEW"
    # Default FALSE — qualification/reply/telephony create deals, not SMTP
    create_deal = _cfg_bool(settings, "BITRIX_CREATE_DEAL", False)
    timeline = _cfg_bool(settings, "BITRIX_TIMELINE_COMMENT", True)
    out: dict[str, Any] = {}
    if not company_id:
        raise ValueError("company_id required for Bitrix note")

    note = (
        f"✉️ Outreach SMTP: письмо отправлено → {to_email}\n"
        f"Тема: {subject}\n"
        f"Message-ID: {message_id or '—'}\n"
        f"Статус: SENT (сделка не создана — ждём ответ/квалификацию)\n\n"
        f"--- Копия ---\n{plain[:3500]}"
    )

    if create_deal:
        deal_title = f"Outreach: {subject} — {company_title}"
        comments = (
            f"Автосоздание после отправки outreach-письма (legacy BITRIX_CREATE_DEAL).\n"
            f"Кому: {to_email}\n"
            f"Тема: {subject}\n"
            f"Message-ID: {message_id or '—'}\n"
            f"Ответственный: офис (ASSIGNED_BY_ID={assigned})\n\n"
            f"--- Копия письма ---\n{plain}"
        )
        deal_id = bitrix.create_deal(
            title=deal_title,
            company_id=company_id,
            assigned_by_id=assigned,
            stage_id=stage,
            comments=comments,
        )
        out["deal_id"] = deal_id
        logger.info("bitrix deal created id=%s company=%s", deal_id, company_id)
        if timeline:
            try:
                bitrix.add_timeline_comment(deal_id, note, entity_type="deal")
            except Exception as exc:  # noqa: BLE001
                logger.warning("timeline comment failed for deal %s: %s", deal_id, exc)
                out["timeline_error"] = str(exc)[:500]
        return out

    if timeline:
        try:
            bitrix.add_timeline_comment(company_id, note, entity_type="company")
            out["company_timeline"] = True
            logger.info("bitrix company timeline ok company=%s", company_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("company timeline failed for %s: %s", company_id, exc)
            out["timeline_error"] = str(exc)[:500]
    return out


def _ensure_verified(
    email: str,
    *,
    deliverability: Any,
) -> tuple[bool, str]:
    try:
        from modules.verification import VerificationModule

        mod = VerificationModule()
        suppressed = None
        if deliverability is not None:
            suppressed = deliverability.is_suppressed(email)
        hard = False
        if suppressed and "hard_bounce" in str(suppressed):
            hard = True
        result = mod.verify(
            email,
            suppressed_reason=suppressed,
            previous_hard_bounce=hard,
        )
        if not result.allow_send:
            return False, f"verify:{result.status}:{result.detail}"
        return True, result.status
    except Exception as exc:  # noqa: BLE001
        logger.warning("verification skipped (allow): %s", exc)
        return True, "verify_error_allow"


def send_batch(
    store: OutboxStore,
    *,
    limit: int,
    dry_run: bool = False,
    bitrix: BitrixClient | None = None,
    only_email: str | None = None,
    settings: Any = None,
    tracking: Any = None,
    deliverability: Any = None,
) -> dict[str, Any]:
    enabled = _cfg_bool(settings, "OUTREACH_ENABLED", False)
    run_state = (_cfg(settings, "OUTREACH_RUN_STATE", "stopped") or "stopped").lower()
    # Prefer explicit run state; fall back to legacy OUTREACH_ENABLED
    if run_state in ("stopped", "paused", "playing"):
        enabled = run_state == "playing"
    daily_limit = _cfg_int(settings, "OUTREACH_DAILY_LIMIT", 15)
    subject = _cfg(settings, "OUTREACH_SUBJECT", "Сотрудничество — Quantum Labs")
    company = _cfg(settings, "OUTREACH_COMPANY_NAME", "Quantum Labs")
    website = _cfg(settings, "OUTREACH_WEBSITE", "https://quantumlabs.ru")
    phone = _cfg(settings, "OUTREACH_CONTACT_PHONE", "")
    mailbox = os.getenv("MAIL_USERNAME") or "office@quantumlabs.ru"
    unsub = (
        _cfg(settings, "OUTREACH_UNSUBSCRIBE_MAILTO", "")
        or mailbox
        or "office@quantumlabs.ru"
    )
    plain_tpl = _cfg(settings, "OUTREACH_TEMPLATE_PLAIN", "")
    html_tpl = _cfg(settings, "OUTREACH_TEMPLATE_HTML", "")
    plus_reply = _cfg_bool(settings, "TRACKING_PLUS_REPLY_TO", False)

    # Lazy import modules so CLI works even if package layout shifts
    if tracking is None:
        try:
            from modules.tracking import TrackingStore

            tracking = TrackingStore()
        except Exception:  # noqa: BLE001
            tracking = None
    if deliverability is None:
        try:
            from modules.deliverability import DeliverabilityStore

            deliverability = DeliverabilityStore()
        except Exception:  # noqa: BLE001
            deliverability = None

    if not dry_run and not enabled:
        return {
            "ok": False,
            "error": f"run_state={run_state} — press Play to send (or use send-one / dry-run)",
            "run_state": run_state,
            "processed": 0,
        }
    if not dry_run and not smtp_configured():
        return {"ok": False, "error": "SMTP not configured (MAIL_*)", "processed": 0}

    sent_today = store.sent_today_count()
    effective_limit = daily_limit
    if deliverability is not None and not dry_run:
        effective_limit = deliverability.effective_daily_limit(settings, daily_limit)

    remaining = max(0, effective_limit - sent_today) if not dry_run else limit
    if not dry_run and remaining <= 0:
        return {
            "ok": False,
            "error": f"daily limit reached (effective={effective_limit}, configured={daily_limit})",
            "sent_today": sent_today,
            "effective_daily_limit": effective_limit,
            "processed": 0,
        }

    # Fetch extra pending so domain/suppression skips can refill within batch
    fetch_n = min(limit * 3, remaining * 3 if not dry_run else limit * 3, 100)
    fetch_n = max(fetch_n, limit)
    candidates = store.list_pending(fetch_n, only_email=only_email)
    if only_email and not candidates:
        return {
            "ok": False,
            "error": f"no pending outbox row for email={only_email}",
            "processed": 0,
        }

    results: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    followups: list[dict[str, Any]] = []
    processed_sends = 0

    for row in candidates:
        if processed_sends >= limit:
            break
        if not dry_run and processed_sends >= remaining:
            break

        if deliverability is not None and not dry_run:
            already = False
            if row.company_id:
                with store.connect() as conn:
                    other = conn.execute(
                        """
                        SELECT id FROM outbox
                        WHERE company_id = ?
                          AND status IN ('sent', 'sending', 'replied')
                          AND id != ?
                        LIMIT 1
                        """,
                        (row.company_id, row.id),
                    ).fetchone()
                already = other is not None
            # Contact policy (AVA ↔ email)
            if row.company_id and not dry_run:
                try:
                    from modules.policy import ContactPolicyStore

                    pol = ContactPolicyStore()
                    ok_p, why = pol.allow_email(row.company_id)
                    if not ok_p:
                        skipped.append(
                            {"id": row.id, "email": row.email, "reason": f"policy:{why}"}
                        )
                        store.set_status(row.id, "skipped", error=f"policy:{why}")
                        continue
                except Exception as exc:  # noqa: BLE001
                    logger.debug("policy check skipped: %s", exc)
            decision = deliverability.decide(
                email=row.email,
                settings=settings,
                sent_today=sent_today + processed_sends,
                configured_daily_limit=daily_limit,
                company_id=row.company_id or None,
                company_already_contacted=already,
            )
            if not decision.allow:
                skipped.append(
                    {
                        "id": row.id,
                        "email": row.email,
                        "reason": decision.reason,
                    }
                )
                if decision.reason.startswith("suppressed:") or decision.reason.startswith(
                    "company_"
                ):
                    store.set_status(row.id, "skipped", error=decision.reason)
                continue
            effective_limit = decision.effective_daily_limit

        if not dry_run:
            ok_v, v_detail = _ensure_verified(row.email, deliverability=deliverability)
            if not ok_v:
                skipped.append({"id": row.id, "email": row.email, "reason": v_detail})
                store.set_status(row.id, "skipped", error=v_detail)
                continue

        # Tracking headers (optional plus Reply-To)
        reply_to = None
        plus_tag = None
        unsub_addr = unsub
        unsub_url = None
        unsub_token = None
        if tracking is not None:
            from modules.tracking import (
                build_tracking_headers,
                make_unsubscribe_token,
                unsubscribe_url_for,
            )

            hdrs = build_tracking_headers(
                outbox_id=row.id,
                mailbox=mailbox,
                enable_plus_reply_to=plus_reply,
                company_slug=_tracking_company_slug(
                    contact_name=row.contact_name,
                    email=row.email,
                    company_title=company,
                ),
            )
            plus_tag = hdrs.get("plus_tag")
            reply_to = hdrs.get("reply_to")
            if hdrs.get("unsubscribe_mailto"):
                unsub_addr = hdrs["unsubscribe_mailto"]
            unsub_token = make_unsubscribe_token(outbox_id=row.id, email=row.email)
            unsub_url = unsubscribe_url_for(unsub_token, settings)

        cb_url = _callback_url_for_row(outbox_id=row.id, email=row.email, settings=settings)
        plain, html = _render_letter(
            contact_name=row.contact_name,
            company=company,
            website=website,
            phone=phone,
            unsubscribe_mailto=unsub_addr,
            unsubscribe_url=unsub_url,
            plain_template=plain_tpl or None,
            html_template=html_tpl or None,
            settings=settings,
            callback_url=cb_url,
        )
        open_token = None
        if tracking is not None and not dry_run:
            try:
                from modules.tracking import inject_open_pixel, new_open_token, open_tracking_enabled

                if open_tracking_enabled(settings):
                    open_token = new_open_token()
                    html = inject_open_pixel(html, open_token, settings)
            except Exception as exc:  # noqa: BLE001
                logger.warning("open pixel inject failed: %s", exc)
                open_token = None
        item: dict[str, Any] = {
            "id": row.id,
            "email": row.email,
            "company_id": row.company_id,
            "contact_id": row.contact_id,
            "contact_name": row.contact_name,
            "plus_tag": plus_tag,
            "reply_to": reply_to,
        }
        try:
            if dry_run:
                item["status"] = "dry_run"
                item["subject"] = subject
                item["preview_plain"] = plain[:500]
                attach = _attachments_for_send(settings, step_wants=False)
                if attach:
                    item["would_attach"] = [p.name for p in attach]
                logger.info("dry-run would send to %s (%s)", row.email, row.contact_name)
                results.append(item)
                processed_sends += 1
            else:
                pre_mid = make_outbound_message_id()
                if not store.claim_for_send(row.id, message_id=pre_mid):
                    skipped.append(
                        {
                            "id": row.id,
                            "email": row.email,
                            "reason": "claim_failed_not_pending",
                        }
                    )
                    continue
                try:
                    attach = _attachments_for_send(settings, step_wants=False)
                    message_id = send_email(
                        to=row.email,
                        subject=subject,
                        plain=plain,
                        html=html,
                        unsubscribe_mailto=unsub_addr,
                        reply_to=reply_to,
                        outreach_id=str(row.id),
                        message_id=pre_mid,
                        unsubscribe_url=unsub_url,
                        attachments=attach,
                    )
                    if attach:
                        item["attached"] = [p.name for p in attach]
                except Exception:
                    store.release_claim(row.id, error="smtp_failed")
                    raise
                item["message_id"] = message_id
                if tracking is not None:
                    try:
                        tracking.record(
                            outbox_id=row.id,
                            email=row.email,
                            message_id=message_id,
                            reply_to=reply_to,
                            plus_tag=plus_tag,
                            subject=subject,
                            open_token=open_token,
                            unsub_token=unsub_token,
                        )
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("tracking record failed: %s", exc)

                if deliverability is not None:
                    try:
                        deliverability.bump_domain(deliverability.domain_of(row.email))
                        if row.company_id:
                            deliverability.bump_company(row.company_id)
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("domain/company bump failed: %s", exc)

                bitrix_meta: dict[str, Any] = {}
                if bitrix and row.company_id:
                    try:
                        bitrix_meta = _record_bitrix_after_send(
                            bitrix,
                            company_id=row.company_id,
                            company_title=row.contact_name or row.email,
                            to_email=row.email,
                            subject=subject,
                            plain=plain,
                            html=html,
                            message_id=message_id,
                            settings=settings,
                        )
                        item.update(bitrix_meta)
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("bitrix after-send failed: %s", exc)
                        item["bitrix_error"] = str(exc)[:500]
                elif bitrix and not row.company_id:
                    logger.warning(
                        "skip Bitrix note: outbox row %s has empty company_id", row.id
                    )
                    item["bitrix_error"] = "empty company_id"

                store.mark(
                    row.id,
                    "sent",
                    deal_id=bitrix_meta.get("deal_id"),
                    message_id=message_id,
                )
                item["status"] = "sent"
                # Sequence enroll + step 1 complete
                try:
                    if _cfg_bool(settings, "SEQUENCES_ENABLED", True):
                        from modules.sequences import SequenceStore
                        from modules.policy import ContactPolicyStore

                        pack_id = (_cfg(settings, "OUTREACH_SEQUENCE_PACK", "") or "").strip()
                        seq = SequenceStore()
                        lead = seq.enroll(
                            email=row.email,
                            company_id=row.company_id or "",
                            contact_name=row.contact_name or "",
                            subject_base=subject,
                            outbox_id=row.id,
                            pack_id=pack_id,
                        )
                        if lead.get("id"):
                            seq.mark_step_sent(
                                int(lead["id"]),
                                step=1,
                                outbox_id=row.id,
                                subject_base=subject,
                            )
                            item["sequence_step"] = 1
                            if pack_id:
                                item["sequence_pack"] = pack_id
                        if row.company_id:
                            ContactPolicyStore().note_email_sent(
                                row.company_id, email=row.email
                            )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("sequence enroll failed: %s", exc)
                logger.info("sent to %s mid=%s", row.email, message_id)
                results.append(item)
                processed_sends += 1
                if processed_sends < limit and processed_sends < remaining:
                    _delay_between_sends(settings)
        except Exception as exc:  # noqa: BLE001
            store.mark(row.id, "failed", error=str(exc)[:500])
            item["status"] = "failed"
            item["error"] = str(exc)[:500]
            results.append(item)
            logger.exception("send failed for %s", row.email)

    # Follow-up steps (2+) for due sequence leads
    if not dry_run and _cfg_bool(settings, "SEQUENCES_ENABLED", True) and processed_sends < limit:
        try:
            followups = _send_due_sequence_steps(
                store,
                limit=max(0, min(limit - processed_sends, remaining - processed_sends)),
                settings=settings,
                bitrix=bitrix,
                tracking=tracking,
                deliverability=deliverability,
                subject_default=subject,
                company=company,
                mailbox=mailbox,
                unsub=unsub,
            )
            for fu in followups:
                if fu.get("status") == "sent":
                    processed_sends += 1
                    results.append(fu)
                elif fu.get("status") == "skipped":
                    skipped.append(fu)
                else:
                    results.append(fu)
        except Exception:  # noqa: BLE001
            logger.exception("sequence follow-ups failed")

    return {
        "ok": True,
        "dry_run": dry_run,
        "processed": len([r for r in results if r.get("status") != "failed"]),
        "failed": len([r for r in results if r.get("status") == "failed"]),
        "skipped": skipped,
        "followups": len([f for f in followups if f.get("status") == "sent"]),
        "sent_today": store.sent_today_count(),
        "daily_limit": daily_limit,
        "effective_daily_limit": effective_limit,
        "plus_reply_to_enabled": plus_reply,
        "only_email": only_email,
        "results": results,
    }


def _plain_to_html(plain: str) -> str:
    from html import escape

    body = escape(plain).replace("\n", "<br>\n")
    return f"<!DOCTYPE html><html><body style='font-family:Georgia,serif'>{body}</body></html>"


def _send_due_sequence_steps(
    store: OutboxStore,
    *,
    limit: int,
    settings: Any,
    bitrix: BitrixClient | None,
    tracking: Any,
    deliverability: Any,
    subject_default: str,
    company: str,
    mailbox: str,
    unsub: str,
) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    from modules.policy import ContactPolicyStore
    from modules.sequences import SequenceStore
    from modules.tracking import (
        build_tracking_headers,
        inject_open_pixel,
        make_unsubscribe_token,
        new_open_token,
        open_tracking_enabled,
        unsubscribe_url_for,
    )

    seq = SequenceStore()
    pol = ContactPolicyStore()
    due = seq.list_due(limit=limit * 2)
    out: list[dict[str, Any]] = []
    sent_n = 0
    plus_reply = _cfg_bool(settings, "TRACKING_PLUS_REPLY_TO", False)

    for lead in due:
        if sent_n >= limit:
            break
        step_def = seq.next_step_def(lead)
        if not step_def:
            continue
        email = str(lead["email"])
        company_id = str(lead.get("company_id") or "")
        if company_id:
            ok_p, why = pol.allow_email(company_id)
            if not ok_p:
                seq.stop(email=email, reason=f"policy:{why}")
                out.append({"email": email, "status": "skipped", "reason": f"policy:{why}"})
                continue
        if deliverability is not None:
            reason = deliverability.is_suppressed(email)
            if reason:
                seq.stop(email=email, reason=f"suppressed:{reason}")
                out.append({"email": email, "status": "skipped", "reason": f"suppressed:{reason}"})
                continue
            paused, pause_reason = deliverability.is_paused()
            if paused:
                out.append(
                    {"email": email, "status": "skipped", "reason": f"mailbox_paused:{pause_reason}"}
                )
                break

        name = str(lead.get("contact_name") or "коллега")
        base_subj = str(lead.get("subject_base") or subject_default)
        website = _cfg(settings, "OUTREACH_WEBSITE", "https://quantumlabs.ru")
        phone = _cfg(settings, "OUTREACH_CONTACT_PHONE", "")
        pack_id = str(lead.get("pack_id") or "")
        subj_tpl = step_def.get("subject") or base_subj
        subject = (
            str(subj_tpl)
            .replace("{subject}", base_subj)
            .replace("{name}", name)
            .replace("{company}", company)
        )
        plain_tpl = step_def.get("plain") or (
            "Добрый день, {name}!\n\nПодскажите, успели посмотреть моё письмо?\n\n"
            "С уважением,\n{company}\n"
        )
        html_tpl = step_def.get("html")

        outbox_id = int(lead["last_outbox_id"] or 0) or None
        row = store.find_by_email(email)
        if row:
            outbox_id = row.id

        reply_to = None
        plus_tag = None
        unsub_addr = unsub
        unsub_url = None
        unsub_token = None
        open_token = None
        if tracking is not None and outbox_id:
            hdrs = build_tracking_headers(
                outbox_id=outbox_id,
                mailbox=mailbox,
                enable_plus_reply_to=plus_reply,
                company_slug=_tracking_company_slug(
                    contact_name=name,
                    email=email,
                    company_title=company,
                ),
            )
            plus_tag = hdrs.get("plus_tag")
            reply_to = hdrs.get("reply_to")
            if hdrs.get("unsubscribe_mailto"):
                unsub_addr = hdrs["unsubscribe_mailto"]
            unsub_token = make_unsubscribe_token(outbox_id=outbox_id, email=email)
            unsub_url = unsubscribe_url_for(unsub_token, settings)

        cb_url = _callback_url_for_row(
            outbox_id=int(outbox_id or 0),
            email=email,
            settings=settings,
        )
        plain, html = _render_letter(
            contact_name=name,
            company=company,
            website=website,
            phone=phone,
            unsubscribe_mailto=unsub_addr,
            unsubscribe_url=unsub_url,
            plain_template=str(plain_tpl),
            html_template=str(html_tpl) if html_tpl else None,
            settings=settings,
            callback_url=cb_url,
        )
        if tracking is not None and outbox_id and open_tracking_enabled(settings):
            open_token = new_open_token()
            html = inject_open_pixel(html, open_token, settings)

        item: dict[str, Any] = {
            "email": email,
            "company_id": company_id,
            "sequence_lead_id": lead["id"],
            "sequence_step": int(step_def["step"]),
            "sequence_pack": pack_id or None,
            "followup": True,
        }
        try:
            pre_mid = make_outbound_message_id()
            attach = _attachments_for_send(
                settings,
                step_wants=bool(step_def.get("attach_presentation")),
            )
            message_id = send_email(
                to=email,
                subject=subject,
                plain=plain,
                html=html,
                unsubscribe_mailto=unsub_addr,
                reply_to=reply_to,
                outreach_id=f"seq-{lead['id']}-{step_def['step']}",
                message_id=pre_mid,
                unsubscribe_url=unsub_url,
                attachments=attach,
            )
            item["message_id"] = message_id
            if tracking is not None and outbox_id:
                tracking.record(
                    outbox_id=outbox_id,
                    email=email,
                    message_id=message_id,
                    reply_to=reply_to,
                    plus_tag=plus_tag,
                    subject=subject,
                    open_token=open_token,
                    unsub_token=unsub_token,
                )
            if deliverability is not None:
                deliverability.bump_domain(deliverability.domain_of(email))
                if company_id:
                    deliverability.bump_company(company_id)
            if bitrix and company_id:
                try:
                    _record_bitrix_after_send(
                        bitrix,
                        company_id=company_id,
                        company_title=name,
                        to_email=email,
                        subject=subject,
                        plain=plain,
                        html=html,
                        message_id=message_id,
                        settings=settings,
                    )
                except Exception as exc:  # noqa: BLE001
                    item["bitrix_error"] = str(exc)[:300]
            updated = seq.mark_step_sent(
                int(lead["id"]),
                step=int(step_def["step"]),
                outbox_id=outbox_id,
                subject_base=base_subj,
            )
            if company_id:
                pol.note_email_sent(company_id, email=email)
                if updated and updated.get("status") == "completed":
                    days = _cfg_int(settings, "COMPANY_CONTACT_COOLDOWN_DAYS", 14)
                    pol.set_second_contact_cooldown(company_id, days=days)
            item["status"] = "sent"
            sent_n += 1
            out.append(item)
            logger.info(
                "sequence step %s sent to %s mid=%s",
                step_def["step"],
                email,
                message_id,
            )
            if sent_n < limit:
                _delay_between_sends(settings)
        except Exception as exc:  # noqa: BLE001
            item["status"] = "failed"
            item["error"] = str(exc)[:500]
            out.append(item)
            logger.exception("sequence follow-up failed for %s", email)
    return out


def send_one(
    store: OutboxStore,
    *,
    to: str,
    contact_name: str | None = None,
    dry_run: bool = False,
    settings: Any = None,
    tracking: Any = None,
    deliverability: Any = None,
    create_bitrix_deal: bool = False,
    bitrix: BitrixClient | None = None,
    attach_presentation: bool | None = None,
) -> dict[str, Any]:
    """Send a single letter to an explicit address (test / one-shot).

    Does NOT require OUTREACH_ENABLED — gated by ONESHOT_DAILY_LIMIT instead.
    Does not consume the mass-send queue unless the email already exists there.
    """
    to_email = (to or "").strip().lower()
    if not to_email or "@" not in to_email:
        return {"ok": False, "error": "valid to email required", "processed": 0}

    if tracking is None:
        try:
            from modules.tracking import TrackingStore

            tracking = TrackingStore()
        except Exception:  # noqa: BLE001
            tracking = None
    if deliverability is None:
        try:
            from modules.deliverability import DeliverabilityStore

            deliverability = DeliverabilityStore()
        except Exception:  # noqa: BLE001
            deliverability = None

    oneshot_limit = _cfg_int(settings, "ONESHOT_DAILY_LIMIT", 5)
    if deliverability is not None and not dry_run:
        used = deliverability.oneshot_today()
        if used >= oneshot_limit:
            return {
                "ok": False,
                "error": f"oneshot daily limit reached ({oneshot_limit})",
                "oneshot_today": used,
                "processed": 0,
            }
        reason = deliverability.is_suppressed(to_email)
        if reason:
            return {
                "ok": False,
                "error": f"suppressed:{reason}",
                "processed": 0,
            }

    if not dry_run and not smtp_configured():
        return {"ok": False, "error": "SMTP not configured (MAIL_*)", "processed": 0}

    subject = _cfg(settings, "OUTREACH_SUBJECT", "Сотрудничество — Quantum Labs")
    company = _cfg(settings, "OUTREACH_COMPANY_NAME", "Quantum Labs")
    website = _cfg(settings, "OUTREACH_WEBSITE", "https://quantumlabs.ru")
    phone = _cfg(settings, "OUTREACH_CONTACT_PHONE", "")
    mailbox = os.getenv("MAIL_USERNAME") or "office@quantumlabs.ru"
    unsub = (
        _cfg(settings, "OUTREACH_UNSUBSCRIBE_MAILTO", "")
        or mailbox
        or "office@quantumlabs.ru"
    )
    plain_tpl = _cfg(settings, "OUTREACH_TEMPLATE_PLAIN", "")
    html_tpl = _cfg(settings, "OUTREACH_TEMPLATE_HTML", "")
    plus_reply = _cfg_bool(settings, "TRACKING_PLUS_REPLY_TO", False)
    name = (contact_name or "").strip() or "коллега"

    row = store.ensure_manual_recipient(email=to_email, contact_name=name)

    reply_to = None
    plus_tag = None
    unsub_addr = unsub
    if tracking is not None:
        from modules.tracking import build_tracking_headers

        hdrs = build_tracking_headers(
            outbox_id=row.id,
            mailbox=mailbox,
            enable_plus_reply_to=plus_reply,
            company_slug=_tracking_company_slug(
                contact_name=name,
                email=to_email,
                company_title=company,
            ),
        )
        plus_tag = hdrs.get("plus_tag")
        reply_to = hdrs.get("reply_to")
        if hdrs.get("unsubscribe_mailto"):
            unsub_addr = hdrs["unsubscribe_mailto"]

    cb_url = _callback_url_for_row(outbox_id=row.id, email=to_email, settings=settings)
    plain, html = _render_letter(
        contact_name=name,
        company=company,
        website=website,
        phone=phone,
        unsubscribe_mailto=unsub_addr,
        plain_template=plain_tpl or None,
        html_template=html_tpl or None,
        settings=settings,
        callback_url=cb_url,
    )
    attach = _attachments_for_send(settings, step_wants=False, force=attach_presentation)
    open_token = None
    if tracking is not None and not dry_run:
        try:
            from modules.tracking import inject_open_pixel, new_open_token, open_tracking_enabled

            if open_tracking_enabled(settings):
                open_token = new_open_token()
                html = inject_open_pixel(html, open_token, settings)
        except Exception as exc:  # noqa: BLE001
            logger.warning("open pixel inject failed: %s", exc)
            open_token = None

    item: dict[str, Any] = {
        "id": row.id,
        "email": to_email,
        "contact_name": name,
        "plus_tag": plus_tag,
        "reply_to": reply_to,
        "oneshot": True,
        "subject": subject,
        "attached": [p.name for p in attach] if attach else [],
    }

    if dry_run:
        item["status"] = "dry_run"
        item["preview_plain"] = plain[:500]
        return {
            "ok": True,
            "dry_run": True,
            "processed": 1,
            "oneshot_today": deliverability.oneshot_today() if deliverability else 0,
            "oneshot_daily_limit": oneshot_limit,
            "attached": item["attached"],
            "results": [item],
        }

    try:
        message_id = send_email(
            to=to_email,
            subject=subject,
            plain=plain,
            html=html,
            unsubscribe_mailto=unsub_addr,
            reply_to=reply_to,
            outreach_id=f"oneshot-{row.id}",
            attachments=attach,
        )
        item["message_id"] = message_id
        if tracking is not None:
            tracking.record(
                outbox_id=row.id,
                email=to_email,
                message_id=message_id,
                reply_to=reply_to,
                plus_tag=plus_tag,
                subject=subject,
                open_token=open_token,
            )
        if deliverability is not None:
            deliverability.bump_domain(deliverability.domain_of(to_email))
            item["oneshot_today"] = deliverability.bump_oneshot()

        deal_meta: dict[str, Any] = {}
        if create_bitrix_deal and bitrix and row.company_id:
            try:
                deal_meta = _record_bitrix_after_send(
                    bitrix,
                    company_id=row.company_id,
                    company_title=row.contact_name or to_email,
                    to_email=to_email,
                    subject=subject,
                    plain=plain,
                    html=html,
                    settings=settings,
                )
                item.update(deal_meta)
            except Exception as exc:  # noqa: BLE001
                item["bitrix_error"] = str(exc)[:500]

        store.mark(row.id, "sent", deal_id=deal_meta.get("deal_id"))
        item["status"] = "sent"
        logger.info("oneshot sent to %s mid=%s attach=%s", to_email, message_id, item["attached"])
        return {
            "ok": True,
            "dry_run": False,
            "processed": 1,
            "oneshot_today": item.get("oneshot_today"),
            "oneshot_daily_limit": oneshot_limit,
            "attached": item["attached"],
            "results": [item],
        }
    except Exception as exc:  # noqa: BLE001
        store.mark(row.id, "failed", error=str(exc)[:500])
        item["status"] = "failed"
        item["error"] = str(exc)[:500]
        logger.exception("oneshot failed for %s", to_email)
        return {"ok": False, "error": str(exc)[:500], "processed": 0, "results": [item]}
