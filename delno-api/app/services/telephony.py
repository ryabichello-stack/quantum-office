"""Office OS telephony — CallSession / CallJob + Frontline bridge."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.principals import PRINCIPAL_VOICE_PUBLIC
from app.core.tenant import TenantContext
from app.models.call_job import CallJob
from app.models.call_session import CallSession
from app.models.conversation import Conversation, Message
from app.models.phone_number import PhoneNumber
from app.models.tenant import Tenant
from app.services.channel_router import resolve_by_phone_e164
from app.services.events import emit_event

_E164_RE = re.compile(r"^\+?[1-9]\d{7,14}$")


def normalize_e164(raw: str) -> str:
    s = (raw or "").strip().replace(" ", "").replace("-", "")
    if s.startswith("00"):
        s = "+" + s[2:]
    if s.isdigit() and s.startswith("8") and len(s) == 11:
        s = "+7" + s[1:]
    if s.isdigit() and s.startswith("7") and len(s) == 11:
        s = "+" + s
    if not s.startswith("+") and s.isdigit():
        s = "+" + s
    return s


def _valid_e164(e164: str) -> bool:
    return bool(_E164_RE.match(e164))


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def session_to_dict(row: CallSession) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "tenant_id": str(row.tenant_id),
        "conversation_id": str(row.conversation_id) if row.conversation_id else None,
        "call_job_id": str(row.call_job_id) if row.call_job_id else None,
        "direction": row.direction,
        "status": row.status,
        "from_e164": row.from_e164,
        "to_e164": row.to_e164,
        "did_e164": row.did_e164,
        "external_id": row.external_id,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "ended_at": row.ended_at.isoformat() if row.ended_at else None,
        "duration_sec": row.duration_sec,
        "outcome": row.outcome,
        "transcript": row.transcript,
        "summary": row.summary,
        "meta": row.meta or {},
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def job_to_dict(row: CallJob) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "tenant_id": str(row.tenant_id),
        "lead_id": str(row.lead_id) if row.lead_id else None,
        "to_e164": row.to_e164,
        "from_did": row.from_did,
        "script": row.script,
        "status": row.status,
        "priority": row.priority,
        "attempts": row.attempts,
        "max_attempts": row.max_attempts,
        "created_by": row.created_by,
        "result_session_id": str(row.result_session_id) if row.result_session_id else None,
        "error": row.error,
        "meta": row.meta or {},
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "scheduled_at": row.scheduled_at.isoformat() if row.scheduled_at else None,
    }


def start_inbound_call(
    db: Session,
    *,
    did: str,
    from_number: str,
    external_id: str | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    did_n = normalize_e164(did)
    from_n = normalize_e164(from_number)
    if not _valid_e164(did_n):
        return {"ok": False, "error": "invalid_did"}

    ctx_chan = resolve_by_phone_e164(db, did_n)
    if not ctx_chan:
        # try without plus variants
        alt = did_n[1:] if did_n.startswith("+") else did_n
        ctx_chan = resolve_by_phone_e164(db, did_n) or resolve_by_phone_e164(db, "+" + alt)
    if not ctx_chan:
        emit_event(
            db,
            event_type="call.inbound.unrouted",
            category="operational",
            source="telephony",
            payload={"did": did_n, "from": from_n, "external_id": external_id},
        )
        return {"ok": False, "error": "did_not_provisioned", "did": did_n}

    if external_id:
        existing = (
            db.query(CallSession)
            .filter(
                CallSession.tenant_id == ctx_chan.tenant_id,
                CallSession.external_id == external_id,
            )
            .one_or_none()
        )
        if existing:
            return {"ok": True, "resumed": True, "session": session_to_dict(existing)}

    conv = Conversation(
        tenant_id=ctx_chan.tenant_id,
        channel="phone",
        status="open",
        contact_ref=from_n,
        meta={"direction": "inbound", "did": did_n, "principal_id": PRINCIPAL_VOICE_PUBLIC},
    )
    db.add(conv)
    db.flush()

    session = CallSession(
        tenant_id=ctx_chan.tenant_id,
        conversation_id=conv.id,
        direction="inbound",
        status="active",
        from_e164=from_n,
        to_e164=did_n,
        did_e164=did_n,
        external_id=external_id,
        started_at=_utc_now(),
        meta=meta or {},
    )
    db.add(session)
    db.flush()

    emit_event(
        db,
        event_type="call.inbound.started",
        category="domain",
        tenant_id=ctx_chan.tenant_id,
        source="telephony",
        payload={
            "session_id": str(session.id),
            "conversation_id": str(conv.id),
            "from": from_n,
            "did": did_n,
            "external_id": external_id,
        },
    )
    db.commit()
    return {
        "ok": True,
        "tenant_slug": ctx_chan.tenant_slug,
        "tenant_id": str(ctx_chan.tenant_id),
        "session": session_to_dict(session),
        "conversation_id": str(conv.id),
        "principal_id": PRINCIPAL_VOICE_PUBLIC,
    }


def _maybe_generate_summary(transcript: str) -> str | None:
    """Best-effort LLM summary for hangup when worker did not supply one."""
    text = (transcript or "").strip()
    if len(text) < 40:
        return text or None
    try:
        from app.services.model_provider import get_model_provider

        provider = get_model_provider()
        out = provider.chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Суммируй телефонный разговор для владельца офиса на русском. "
                        "2–4 предложения: кто звонил, о чём, итог/следующий шаг. Без воды."
                    ),
                },
                {"role": "user", "content": text[:12000]},
            ],
            max_tokens=280,
        )
        if not out.get("ok"):
            return None
        data = out.get("data") or {}
        choice = (data.get("choices") or [{}])[0]
        content = ((choice.get("message") or {}).get("content") or "").strip()
        return content[:2000] or None
    except Exception:  # noqa: BLE001
        return None


def end_call(
    db: Session,
    *,
    session_id: uuid.UUID,
    transcript: str | None = None,
    summary: str | None = None,
    outcome: str | None = None,
    duration_sec: int | None = None,
    recording_url: str | None = None,
    meta: dict[str, Any] | None = None,
    generate_summary: bool = False,
) -> dict[str, Any]:
    session = db.query(CallSession).filter(CallSession.id == session_id).one_or_none()
    if not session:
        return {"ok": False, "error": "not_found"}

    session.status = "ended"
    session.ended_at = _utc_now()
    if transcript is not None:
        session.transcript = transcript
    if summary is not None:
        session.summary = summary
    if outcome is not None:
        session.outcome = outcome
    if duration_sec is not None:
        session.duration_sec = duration_sec
    elif session.started_at and session.ended_at:
        start = session.started_at
        end = session.ended_at
        if start.tzinfo is None and end.tzinfo is not None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None and start.tzinfo is not None:
            end = end.replace(tzinfo=timezone.utc)
        session.duration_sec = int((end - start).total_seconds())

    sess_meta = dict(session.meta or {})
    if meta:
        sess_meta.update(meta)
    if recording_url:
        sess_meta["recording_url"] = recording_url
    session.meta = sess_meta

    if generate_summary and not (session.summary or "").strip() and (session.transcript or "").strip():
        generated = _maybe_generate_summary(session.transcript or "")
        if generated:
            session.summary = generated

    brain_result: dict[str, Any] | None = None
    if session.conversation_id and (session.summary or session.transcript):
        body = session.summary or (session.transcript or "")[:2000]
        db.add(
            Message(
                tenant_id=session.tenant_id,
                conversation_id=session.conversation_id,
                role="system",
                body=body,
                meta={
                    "kind": "call_summary",
                    "session_id": str(session.id),
                    "outcome": session.outcome,
                    "has_transcript": bool(session.transcript),
                },
            )
        )
        conv = db.query(Conversation).filter(Conversation.id == session.conversation_id).one_or_none()
        if conv:
            # Keep open so inbox shows as new / needs review (live memory)
            conv.status = "open"
            cmeta = dict(conv.meta or {})
            visitor = session.from_e164 if session.direction == "inbound" else session.to_e164
            cmeta.update(
                {
                    "direction": session.direction,
                    "did": session.did_e164,
                    "session_id": str(session.id),
                    "visitor_phone": visitor or cmeta.get("visitor_phone") or conv.contact_ref,
                    "summary": session.summary,
                    "last_message_preview": (session.summary or body)[:240],
                    "call_status": "completed" if (session.outcome or "") != "failed" else "failed",
                    "recording_url": sess_meta.get("recording_url"),
                    "recording_duration_sec": session.duration_sec,
                    "needs_review": True,
                    "principal_id": PRINCIPAL_VOICE_PUBLIC,
                }
            )
            conv.meta = cmeta
            conv.updated_at = _utc_now()

        from app.services.telephony_brain_sync import sync_call_session_to_brain

        brain_result = sync_call_session_to_brain(db, session)

    if session.call_job_id:
        job = db.query(CallJob).filter(CallJob.id == session.call_job_id).one_or_none()
        if job:
            job.status = "done" if (session.outcome or "") != "failed" else "failed"
            job.result_session_id = session.id

    event_type = "call.inbound.ended" if session.direction == "inbound" else "call.outbound.ended"
    emit_event(
        db,
        event_type=event_type,
        category="domain",
        tenant_id=session.tenant_id,
        source="telephony",
        payload={
            "session_id": str(session.id),
            "conversation_id": str(session.conversation_id) if session.conversation_id else None,
            "outcome": session.outcome,
            "duration_sec": session.duration_sec,
            "has_transcript": bool(session.transcript),
            "has_summary": bool(session.summary),
            "brain_ok": bool(brain_result and brain_result.get("ok")),
        },
    )
    if session.transcript:
        emit_event(
            db,
            event_type="call.transcript.ready",
            category="domain",
            tenant_id=session.tenant_id,
            source="telephony",
            payload={"session_id": str(session.id)},
        )
    if session.summary:
        emit_event(
            db,
            event_type="call.summary.ready",
            category="domain",
            tenant_id=session.tenant_id,
            source="telephony",
            payload={"session_id": str(session.id), "summary": session.summary[:500]},
        )
    db.commit()
    out: dict[str, Any] = {"ok": True, "session": session_to_dict(session)}
    if brain_result is not None:
        out["brain"] = brain_result
    return out


def frontline_turn(
    db: Session,
    *,
    session_id: uuid.UUID,
    text: str,
) -> dict[str, Any]:
    """Post-STT turn during an active call → Frontline Operator."""
    session = db.query(CallSession).filter(CallSession.id == session_id).one_or_none()
    if not session:
        return {"ok": False, "error": "not_found"}
    if session.status not in ("active", "ringing", "in_progress"):
        return {"ok": False, "error": "call_not_active", "status": session.status}

    tenant = db.query(Tenant).filter(Tenant.id == session.tenant_id).one()
    ctx = TenantContext(
        tenant_id=tenant.id,
        tenant_slug=tenant.slug,
        user_id=None,
        role=PRINCIPAL_VOICE_PUBLIC,
    )

    prompt = text.strip()
    if session.call_job_id:
        job = db.query(CallJob).filter(CallJob.id == session.call_job_id).one_or_none()
        if job and job.script and session.meta.get("script_injected") is not True:
            prompt = (
                f"[Исходящий сценарий от Hermes]\n{job.script}\n\n"
                f"[Реплика собеседника]\n{text.strip()}"
            )
            meta = dict(session.meta or {})
            meta["script_injected"] = True
            session.meta = meta
            session.status = "in_progress"

    # Lazy import avoids circular dependency: agent → tools.calls → telephony → agent
    from app.operator.agent import run_operator_turn

    out = run_operator_turn(
        db,
        ctx,
        message=prompt,
        channel="phone",
        conversation_id=session.conversation_id,
        input_modality="voice",
        record_user_message=True,
        commit=True,
    )
    return {
        "ok": True,
        "session_id": str(session.id),
        "reply": out.get("reply") or out.get("message") or "",
        "operator": out,
    }


def create_outbound_job(
    db: Session,
    ctx: TenantContext,
    *,
    to_e164: str,
    script: str,
    lead_id: uuid.UUID | None = None,
    created_by: str = "hermes",
    from_did: str | None = None,
) -> dict[str, Any]:
    to_n = normalize_e164(to_e164)
    if not _valid_e164(to_n):
        return {"ok": False, "error": "invalid_to_e164"}

    did = from_did
    if not did:
        phone = (
            db.query(PhoneNumber)
            .filter(
                PhoneNumber.tenant_id == ctx.tenant_id,
                PhoneNumber.status == "active",
            )
            .order_by(PhoneNumber.created_at.asc())
            .first()
        )
        did = phone.e164 if phone else None

    job = CallJob(
        tenant_id=ctx.tenant_id,
        lead_id=lead_id,
        to_e164=to_n,
        from_did=did,
        script=(script or "").strip(),
        status="queued",
        created_by=created_by,
    )
    db.add(job)
    db.flush()
    emit_event(
        db,
        event_type="call.outbound.queued",
        category="domain",
        tenant_id=ctx.tenant_id,
        source="hermes",
        payload={"job_id": str(job.id), "to": to_n, "from_did": did, "created_by": created_by},
    )
    db.commit()
    return {"ok": True, "job": job_to_dict(job)}


def list_sessions(db: Session, ctx: TenantContext, *, limit: int = 30) -> list[dict[str, Any]]:
    rows = (
        db.query(CallSession)
        .filter(CallSession.tenant_id == ctx.tenant_id)
        .order_by(CallSession.created_at.desc())
        .limit(min(limit, 100))
        .all()
    )
    return [session_to_dict(r) for r in rows]


def get_session(db: Session, ctx: TenantContext, session_id: uuid.UUID) -> dict[str, Any] | None:
    row = (
        db.query(CallSession)
        .filter(CallSession.id == session_id, CallSession.tenant_id == ctx.tenant_id)
        .one_or_none()
    )
    return session_to_dict(row) if row else None


def list_jobs(db: Session, ctx: TenantContext, *, status: str | None = None, limit: int = 30) -> list[dict[str, Any]]:
    q = db.query(CallJob).filter(CallJob.tenant_id == ctx.tenant_id)
    if status:
        q = q.filter(CallJob.status == status)
    rows = q.order_by(CallJob.created_at.desc()).limit(min(limit, 100)).all()
    return [job_to_dict(r) for r in rows]


def claim_next_job(db: Session) -> dict[str, Any] | None:
    """Dialer worker: claim oldest queued job globally (tenant isolated in row)."""
    q = (
        db.query(CallJob)
        .filter(CallJob.status == "queued")
        .order_by(CallJob.priority.asc(), CallJob.created_at.asc())
    )
    try:
        job = q.with_for_update(skip_locked=True).first()
    except Exception:  # noqa: BLE001 — sqlite / dialects without SKIP LOCKED
        job = q.first()
    if not job:
        return None
    job.status = "dialing"
    job.attempts = int(job.attempts or 0) + 1
    db.flush()

    tenant = db.query(Tenant).filter(Tenant.id == job.tenant_id).one()
    conv = Conversation(
        tenant_id=job.tenant_id,
        channel="phone",
        status="open",
        contact_ref=job.to_e164,
        meta={"direction": "outbound", "job_id": str(job.id)},
    )
    db.add(conv)
    db.flush()
    session = CallSession(
        tenant_id=job.tenant_id,
        conversation_id=conv.id,
        call_job_id=job.id,
        direction="outbound",
        status="ringing",
        from_e164=job.from_did,
        to_e164=job.to_e164,
        did_e164=job.from_did,
        started_at=_utc_now(),
        meta={"script": job.script},
    )
    db.add(session)
    db.flush()
    job.status = "in_progress"
    emit_event(
        db,
        event_type="call.outbound.started",
        category="domain",
        tenant_id=job.tenant_id,
        source="telephony.dialer",
        payload={"job_id": str(job.id), "session_id": str(session.id), "to": job.to_e164},
    )
    db.commit()
    return {
        "job": job_to_dict(job),
        "session": session_to_dict(session),
        "tenant_slug": tenant.slug,
        "conversation_id": str(conv.id),
    }
