"""SSE cabinet stream: Hermes run events, then the same final /chat payload."""

from __future__ import annotations

from typing import Any, Iterator

from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.services.hermes_nous.live_events import format_sse, map_hermes_event


def _office_context(db: Session, ctx: TenantContext) -> dict[str, Any]:
    try:
        from app.services.hermes_nous.onboarding import get_office_loop

        loop = get_office_loop(db, ctx) or {}
    except Exception:
        loop = {}
    setup = loop.get("setup") if isinstance(loop.get("setup"), dict) else {}
    return {
        "phase": loop.get("phase") or "welcome",
        "kb_ok": bool(loop.get("kb_ok")),
        "setup_next": loop.get("setup_next"),
        "setup_complete": bool(setup.get("setup_complete")),
        "progress": setup.get("progress"),
    }


def _public_run(nous: dict[str, Any]) -> dict[str, Any]:
    hidden = {"_started_at"}
    return {key: value for key, value in nous.items() if key not in hidden}


def iter_chat_stream(
    db: Session,
    ctx: TenantContext,
    body: Any,
    *,
    eligible: bool,
) -> Iterator[str]:
    if not eligible:
        yield format_sse("fallback", {"reason": "use_chat"})
        return

    from app.services.hermes_nous.bridge import (
        HermesBridgeError,
        _meter_hermes_turn,
        _poll_run_output,
        create_run,
        iter_hermes_sse,
        resolve_runtime,
    )
    from app.services.hermes_nous.tool_packs import pack_for_mode

    message = (getattr(body, "message", None) or "").strip()
    try:
        context = _office_context(db, ctx)
        pack_mode = "conduct" if context.get("setup_complete") or context.get("phase") in ("ready", "conduct") else "onboarding"
        session_id = None
        conversation_id = getattr(body, "conversation_id", None)
        if conversation_id:
            session_id = f"{ctx.tenant_slug}:{conversation_id}"
        started = create_run(
            db,
            ctx,
            message=message,
            session_id=session_id,
            tool_ids=pack_for_mode(pack_mode),
            mode=pack_mode,
            office_context=context,
            wait=False,
        )
    except HermesBridgeError:
        yield format_sse("fallback", {"reason": "bridge"})
        return

    run_id = str(started.get("run_id") or "")
    yield format_sse("started", {"run_id": run_id})
    yield format_sse("action", {"phase": "thinking"})

    observed: list[dict[str, Any]] = []
    try:
        runtime = resolve_runtime(db, ctx)
        for name, data in iter_hermes_sse(runtime, run_id):
            mapped = map_hermes_event(name, data)
            if not mapped:
                continue
            if mapped.get("phase") == "terminal":
                break
            if mapped.get("phase") == "tool" and mapped.get("tool"):
                observed.append(
                    {
                        "tool": mapped["tool"],
                        "ok": True,
                        "preview": mapped.get("preview") or "",
                    }
                )
            yield format_sse("action", {k: v for k, v in mapped.items() if v is not None})
    except HermesBridgeError:
        # Events endpoint missing or dropped. The final poll still finishes the turn.
        pass

    runtime = resolve_runtime(db, ctx)
    polled = _poll_run_output(runtime, run_id, timeout_s=75.0) if run_id else None
    final_body = polled if isinstance(polled, dict) else (started.get("hermes") if isinstance(started.get("hermes"), dict) else {})
    output = ""
    if isinstance(final_body, dict):
        output = str(final_body.get("output") or "")
    nous = _public_run(started)
    nous["output"] = output
    nous["hermes"] = final_body
    nous["status"] = str((final_body or {}).get("status") or "completed")
    if observed:
        nous["tool_calls"] = observed
    _meter_hermes_turn(
        db,
        ctx,
        final_body,
        started_at=float(started.get("_started_at") or 0.0),
        runtime=runtime,
    )

    from app.api.v1.operator import _finish_diy, _tool_calls_from_nous

    reply = output or "Hermes завершил ход."
    tool_calls = _tool_calls_from_nous(nous)
    try:
        from app.services.hermes_guide import prefer_pending_kb_draft_reply

        reply = prefer_pending_kb_draft_reply(db, ctx, str(reply or ""), tool_calls=tool_calls)
    except Exception:
        pass
    modality = body.modality if getattr(body, "modality", None) in ("text", "voice") else "text"
    payload = _finish_diy(
        db,
        ctx,
        body,
        modality=modality,
        engine="nous_hermes_agent",
        reply=str(reply or ""),
        tool_calls=tool_calls,
        hermes_run=nous,
    )
    yield format_sse("done", payload)
