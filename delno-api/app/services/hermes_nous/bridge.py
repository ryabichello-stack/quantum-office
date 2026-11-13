"""DELNO → Hermes API bridge (runs + OpenAI-compat fallback)."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.services.hermes_nous.provision import ensure_tenant_hermes_home, tenant_runtime_record
from app.services.hermes_nous.run_tokens import issue_run_token
from app.services.hermes_nous.tasks import add_step, record_run
from app.services.hermes_nous.tool_packs import pack_for_mode


class HermesBridgeError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None, body: Any = None):
        super().__init__(message)
        self.status = status
        self.body = body


def _http_json(
    method: str,
    url: str,
    *,
    api_key: str,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 120.0,
) -> tuple[int, Any]:
    data = None
    req_headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if headers:
        req_headers.update(headers)
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    # Never send tenant Hermes calls through corporate HTTP(S)_PROXY.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            body: Any = json.loads(raw) if raw.strip() else {}
            return int(resp.status), body
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            body = {"raw": raw}
        raise HermesBridgeError(f"hermes_http_{exc.code}", status=exc.code, body=body) from exc
    except urllib.error.URLError as exc:
        raise HermesBridgeError(f"hermes_unreachable: {exc.reason}") from exc


def resolve_runtime(db: Session, ctx: TenantContext) -> dict[str, Any]:
    record = tenant_runtime_record(db, ctx)
    if not record or not record.get("runtime_base_url"):
        record = ensure_tenant_hermes_home(db, ctx)
    base = (record or {}).get("runtime_base_url") or os.environ.get("HERMES_NOUS_RUNTIME_URL") or ""
    base = str(base).rstrip("/")
    if not base:
        raise HermesBridgeError(
            "hermes_runtime_not_configured",
            body={"hint": "Set HERMES_NOUS_RUNTIME_URL or provision runtime_base_url"},
        )
    key_env = str((record or {}).get("api_server_key_env") or "HERMES_API_SERVER_KEY")
    api_key = os.environ.get(key_env) or os.environ.get("HERMES_API_SERVER_KEY") or ""
    if not api_key:
        raise HermesBridgeError("hermes_api_key_missing", body={"env": key_env})
    return {"base_url": base, "api_key": api_key, "record": record}


def create_run(
    db: Session,
    ctx: TenantContext,
    *,
    message: str,
    session_id: str | None = None,
    tool_ids: list[str] | None = None,
    idempotency_key: str | None = None,
    task_id: UUID | None = None,
    mode: str | None = "onboarding",
    office_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Start a Hermes /v1/runs turn; mint scoped MCP token for this run."""
    runtime = resolve_runtime(db, ctx)
    run_id_hint = f"delno_{uuid4().hex[:12]}"
    tools = tool_ids if tool_ids else pack_for_mode(mode)
    issued = issue_run_token(
        db,
        ctx,
        run_id=run_id_hint,
        tool_ids=tools,
        knowledge_scopes=["default"],
    )
    delno_run = record_run(
        db,
        ctx,
        hermes_run_id=run_id_hint,
        task_id=task_id,
        status="running",
        summary=message[:500],
    )
    add_step(
        db,
        ctx,
        delno_run.id,
        kind="plan",
        safe_summary=f"Старт поручения (mode={mode})",
        status="completed",
    )
    _meter_run_start(db, ctx, delno_run_id=str(delno_run.id))
    headers = {"Idempotency-Key": idempotency_key or f"delno-{run_id_hint}"}
    # Pass run token via header Hermes can map into MCP env (DELNO injects at gateway).
    headers["X-Delno-Run-Token"] = issued.token
    tool_hint = ", ".join(tools[:24])
    pack = (mode or "onboarding").strip().lower()
    ctx_bits: list[str] = []
    if isinstance(office_context, dict):
        if office_context.get("kb_ok"):
            ctx_bits.append("KB step is DONE — do not ask to import/rebuild company knowledge.")
        sn = office_context.get("setup_next")
        if isinstance(sn, dict) and sn.get("title"):
            sub = sn.get("substep")
            micro = f" micro-step={sub}." if sub else ""
            if sub == "need_sip":
                micro += " Open credentials.open_form mango_sip (never ask password in chat)."
            elif sub == "need_did":
                micro += " phones.list → phones.provision; do not reopen SIP form."
            elif sub == "need_reg":
                micro += " Check hermes.health / registration; do not reopen SIP form."
            elif sn.get("id") == "telephony_script":
                micro += (
                    " Use telephony.script_get → draft/save script; "
                    "do not reopen SIP form or re-import KB."
                )
            elif sn.get("id") == "telegram":
                micro += " Open credentials.open_form telegram_bot (BotFather token; never in chat)."
            elif sn.get("id") == "max":
                micro += " Open credentials.open_form max_bot (access token; never in chat)."
            elif sn.get("id") == "files":
                micro += (
                    " Open credentials.open_form files_yadisk "
                    "(or files_mailru / files_gdrive / files_onedrive)."
                )
            ctx_bits.append(
                f"hermes_ops next required step: «{sn.get('title')}» "
                f"(id={sn.get('id')}).{micro} hint: {sn.get('hint') or '—'}. Lead with this."
            )
        phase = office_context.get("phase")
        if phase:
            ctx_bits.append(f"office_loop.phase={phase}")
    context_line = (" " + " ".join(ctx_bits)) if ctx_bits else ""
    if pack in ("onboarding", "welcome", "kb", "p1"):
        mission = (
            "Product loop (owner Hermes): follow hermes.setup_status facts, not guesses. "
            "ONLY treat checks.*.ok / tenant_usable / setup_complete as truth for THIS tenant. "
            "Platform upstream / Docker / detail.platform_upstream / service_reachable NEVER means "
            "the owner configured mail/calendar/files/conference/phone. "
            "If required_done is 0, say the office is empty and start with «О компании» — "
            "never claim connectors are activated, never invent demo DIDs like +79991234567. "
            "If KB is done, advance to connectors (credentials.open_form / phones / channels). "
            "Never invent website URLs, phone numbers, or passwords. Prefer hermes.setup_status, "
            "hermes.setup_mark, credentials.open_form, office.import_website only when KB is missing."
        )
    else:
        mission = (
            "Office is being conducted: plan → DELNO MCP tools → report. "
            "ONLY use MCP server delno_office. Do NOT use greptile_mcp, hosted connectors, "
            "portal.nousresearch.com, or manage_connections. "
            "Call tools by exact registered names with dots→underscores, e.g. "
            "mcp__delno_office__get_knowledge, mcp__delno_office__phones_list, "
            "mcp__delno_office__hermes_health, mcp__delno_office__billing_summary. "
            "If unsure, tool_search then call the mcp__delno_office__… result. "
            "Never bare names, never terminal. Never claim a granted tool is unavailable. "
            "Critical writes need confirmation policy."
        )
    payload: dict[str, Any] = {
        "input": message,
        "session_id": session_id or f"delno-{ctx.tenant_id}-{ctx.user_id or 'owner'}",
        "instructions": (
            f"You are the company Hermes agent for THIS tenant only. {mission}{context_line} "
            f"Logical grants (map to mcp__delno_office__*): {tool_hint}. "
            "Do not invent credentials. "
            "Act as a normal multi-step agent: (1) short numbered plan in Russian, "
            "(2) call tools for each step in order, (3) final report of what was done. "
            "Never collapse a multi-part request into a single canned reply. "
            "For websites/URLs use mcp__delno_office__web_research or "
            "mcp__delno_office__web_browse / web_fetch — NEVER a local Chromium/"
            "terminal browser (it is not available in this runtime)."
        ),
    }
    url = f"{runtime['base_url']}/v1/runs"
    try:
        status, body = _http_json(
            "POST",
            url,
            api_key=runtime["api_key"],
            payload=payload,
            headers=headers,
        )
    except HermesBridgeError as exc:
        # Fallback: OpenAI-compat chat completions when Runs API unavailable on pin
        if exc.status in (404, 405, 501) or "unreachable" in str(exc):
            return _fallback_chat(runtime, message=message, session_id=payload["session_id"], issued=issued)
        raise

    hermes_run_id = (body or {}).get("run_id") or issued.run_id
    # Interactive cabinet expects a completed turn — poll briefly for output.
    polled = _poll_run_output(runtime, hermes_run_id, timeout_s=75.0)
    final_body = polled or body or {}
    output = ""
    if isinstance(final_body, dict):
        output = str(final_body.get("output") or "")
        if not output:
            # some pins nest message content
            choices = final_body.get("choices") or []
            if choices:
                output = str(((choices[0] or {}).get("message") or {}).get("content") or "")
    return {
        "ok": True,
        "engine": "nous_hermes_agent",
        "mode": "runs",
        "pack_mode": mode,
        "http_status": status,
        "run_id": hermes_run_id,
        "delno_run_id": issued.run_id,
        "delno_agent_run_id": str(delno_run.id),
        "run_token_expires_at": issued.expires_at,
        "tool_ids": tools,
        "output": output,
        "hermes": final_body,
        "session_id": payload["session_id"],
    }


def _poll_run_output(runtime: dict[str, Any], run_id: str, *, timeout_s: float = 75.0) -> dict[str, Any] | None:
    """Poll GET /v1/runs/{id} until completed/failed or timeout."""
    deadline = time.time() + timeout_s
    last: dict[str, Any] | None = None
    while time.time() < deadline:
        try:
            _status, body = _http_json(
                "GET",
                f"{runtime['base_url']}/v1/runs/{run_id}",
                api_key=runtime["api_key"],
                timeout=20.0,
            )
        except HermesBridgeError:
            break
        if isinstance(body, dict):
            last = body
            st = str(body.get("status") or "").lower()
            if st in {"completed", "failed", "error", "cancelled", "canceled", "stopped"}:
                return body
            if body.get("output"):
                return body
        time.sleep(1.2)
    return last


def get_run(db: Session, ctx: TenantContext, run_id: str) -> dict[str, Any]:
    runtime = resolve_runtime(db, ctx)
    status, body = _http_json(
        "GET",
        f"{runtime['base_url']}/v1/runs/{run_id}",
        api_key=runtime["api_key"],
    )
    return {"ok": True, "http_status": status, "hermes": body}


def stop_run(db: Session, ctx: TenantContext, run_id: str) -> dict[str, Any]:
    runtime = resolve_runtime(db, ctx)
    status, body = _http_json(
        "POST",
        f"{runtime['base_url']}/v1/runs/{run_id}/stop",
        api_key=runtime["api_key"],
        payload={},
    )
    return {"ok": True, "http_status": status, "hermes": body}


def _fallback_chat(
    runtime: dict[str, Any],
    *,
    message: str,
    session_id: str,
    issued: Any,
) -> dict[str, Any]:
    status, body = _http_json(
        "POST",
        f"{runtime['base_url']}/v1/chat/completions",
        api_key=runtime["api_key"],
        payload={
            "model": "hermes-agent",
            "messages": [{"role": "user", "content": message}],
        },
        headers={
            "X-Hermes-Session-Id": session_id,
            "X-Delno-Run-Token": issued.token,
        },
    )
    choice = ((body or {}).get("choices") or [{}])[0]
    text = ((choice.get("message") or {}).get("content")) or ""
    return {
        "ok": True,
        "engine": "nous_hermes_agent",
        "mode": "chat_completions_fallback",
        "http_status": status,
        "run_id": issued.run_id,
        "delno_run_id": issued.run_id,
        "run_token_expires_at": issued.expires_at,
        "output": text,
        "hermes": body,
        "session_id": session_id,
    }


def _meter_run_start(db: Session, ctx: TenantContext, *, delno_run_id: str) -> None:
    """P5: best-effort usage breadcrumb (no secrets)."""
    try:
        from app.services.events import emit_event

        emit_event(
            db,
            tenant_id=ctx.tenant_id,
            event_type="hermes_nous.run_started",
            category="billing",
            source="hermes_nous.bridge",
            payload={"delno_agent_run_id": delno_run_id},
        )
        db.commit()
    except Exception:  # noqa: BLE001
        pass
