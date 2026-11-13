"""DELNO → Hermes API bridge (runs + OpenAI-compat fallback)."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.services.hermes_nous.placement import PlacementError, resolve_placement
from app.services.hermes_nous.run_bindings import bind_run_token
from app.services.hermes_nous.run_tokens import issue_run_token
from app.services.hermes_nous.tasks import add_step, record_run
from app.services.hermes_nous.tool_packs import pack_for_mode


class HermesBridgeError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None, body: Any = None):
        super().__init__(message)
        self.status = status
        self.body = body


def _office_facts_block(office_context: dict[str, Any] | None) -> str:
    """Ground Hermes in THIS tenant's hermes_ops facts (Hermes still speaks — no DIY reply)."""
    if not isinstance(office_context, dict):
        return ""
    progress = office_context.get("progress") if isinstance(office_context.get("progress"), dict) else {}
    sn = office_context.get("setup_next") if isinstance(office_context.get("setup_next"), dict) else {}
    checks = office_context.get("checks_summary") if isinstance(office_context.get("checks_summary"), dict) else {}
    lines = [
        "[FACTS hermes_ops — только этот кабинет; не выдумывай «уже готово»]",
        f"setup_complete={bool(office_context.get('setup_complete'))}",
        f"phase={office_context.get('phase') or '—'}",
        f"kb_ok={bool(office_context.get('kb_ok'))}",
    ]
    if progress:
        lines.append(
            f"required_done={progress.get('required_done')}/{progress.get('required_total')}"
        )
    if checks:
        bits = [f"{k}={'ok' if v else 'нет'}" for k, v in checks.items()]
        lines.append("checks: " + ", ".join(bits))
    if sn.get("title"):
        lines.append(
            f"next_step=«{sn.get('title')}» id={sn.get('id')} hint={sn.get('hint') or '—'}"
        )
    if int(progress.get("required_done") or 0) == 0:
        lines.append(
            "Кабинет ПУСТОЙ: знания/телефония/секретарь/почта/календарь/ВКС — НЕ готовы."
        )
    return "\n".join(lines)


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
    """Resolve THIS tenant's profile→worker. Never fall back to env default / worker A."""
    try:
        return resolve_placement(db, ctx)
    except PlacementError as exc:
        raise HermesBridgeError(exc.code, status=exc.status, body=exc.detail) from exc


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
    record = runtime.get("record") if isinstance(runtime.get("record"), dict) else {}
    profile_id = str(record.get("profile_id") or f"tenant_{ctx.tenant_slug}__company_main")
    worker_id = str(record.get("worker_id") or record.get("slot_id") or "") or None
    # Namespace session to tenant+profile — never share across companies.
    if session_id:
        sid = str(session_id)
        if not sid.startswith(f"{ctx.tenant_slug}:"):
            sid = f"{ctx.tenant_slug}:{sid}"
        session_id = sid
    run_id_hint = f"delno_{uuid4().hex[:12]}"
    tools = tool_ids if tool_ids else pack_for_mode(mode)
    issued = issue_run_token(
        db,
        ctx,
        run_id=run_id_hint,
        tool_ids=tools,
        knowledge_scopes=["default"],
        agent_id=str(record.get("agent_id") or "company_main"),
    )
    bind_run_token(
        db,
        tenant_id=ctx.tenant_id,
        profile_id=profile_id,
        worker_id=worker_id,
        run_id=run_id_hint,
        session_id=session_id,
        actor_user_id=ctx.user_id,
        agent_id=str(record.get("agent_id") or "company_main"),
        raw_token=issued.token,
        tool_ids=list(issued.tool_ids),
        expires_at_unix=int(issued.expires_at),
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
    # Preferred: Hermes MCP client forwards this into MCP Authorization.
    # Fallback: MCP proxy resolves binding by X-Delno-Run-Id (see /v1/mcp).
    headers["X-Delno-Run-Token"] = issued.token
    headers["X-Delno-Run-Id"] = run_id_hint
    headers["X-Delno-Profile-Id"] = profile_id
    if worker_id:
        headers["X-Delno-Worker-Id"] = worker_id
    tool_hint = ", ".join(tools[:24])
    pack = (mode or "onboarding").strip().lower()
    ctx_bits: list[str] = []
    if isinstance(office_context, dict):
        progress = office_context.get("progress") if isinstance(office_context.get("progress"), dict) else {}
        req_done = progress.get("required_done")
        req_total = progress.get("required_total")
        if req_done is not None and req_total is not None:
            ctx_bits.append(
                f"FACT progress required_done={req_done}/{req_total} for THIS tenant only."
            )
            if int(req_done or 0) == 0:
                ctx_bits.append(
                    "FACT: cabinet is EMPTY — KB/phone/script/mail/calendar/conference are NOT done. "
                    "Never say «уже готова/готовы». Start at «О компании»."
                )
        if office_context.get("kb_ok"):
            ctx_bits.append("KB step is DONE — do not ask to import/rebuild company knowledge.")
        else:
            ctx_bits.append(
                "FACT: KB is NOT ready for this tenant — do not claim knowledge/telephony are done."
            )
        sn = office_context.get("setup_next")
        if isinstance(sn, dict) and sn.get("title"):
            sub = sn.get("substep")
            micro = f" micro-step={sub}." if sub else ""
            if sub == "need_sip":
                micro += (
                    " MUST call credentials.open_form mango_sip now "
                    "(never ask password in chat; never only describe the form)."
                )
            elif sub == "need_did":
                micro += (
                    " phones.list → phones.provision; after DID succeeds in same turn "
                    "open credentials.open_form mango_sip if SIP not Registered yet."
                )
            elif sub == "need_reg":
                micro += (
                    " hermes.health: if Registered → next setup step; "
                    "if Rejected/not Registered → MUST credentials.open_form mango_sip again "
                    "(fix password; do not only say «проверьте пароль»)."
                )
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
            "When owner sends a company URL, social link, free-text, or attachment "
            "(image of КП/presentation/price list, or PDF/DOCX) — or asks to enrich KB: "
            "commercial director flow — office.build_kb_draft (attachments arrive as extracted "
            "free_text via DIY vision/file path) → SHOW the full commercial profile in the reply → ask "
            "«Добавить в базу знаний?» and WAIT. Do NOT call hermes.setup_mark, "
            "upload_knowledge_snippet, or jump to phone/SIP in the same turn. "
            "Only after owner says yes: office.confirm_kb_draft, then hermes.setup_status and "
            "propose the next connector with a question. Critical writes need owner consent first. "
            "If KB already has data: get_knowledge first, then enrich via browser and rewrite stronger. "
            "Never invent website URLs, phone numbers, or passwords."
        )
    else:
        mission = (
            "Office is being conducted: plan → DELNO MCP tools → report. "
            "ONLY use MCP server delno_office. Do NOT use greptile_mcp, hosted connectors, "
            "portal.nousresearch.com, or manage_connections. "
            "If owner asks to enrich KB / deepen company description: act as commercial director — "
            "get_knowledge → browser research → strong commercial profile in the reply → confirm. "
            "Call tools by exact registered names with dots→underscores, e.g. "
            "mcp__delno_office__get_knowledge, mcp__delno_office__office_build_kb_draft, "
            "mcp__delno_office__web_research, mcp__delno_office__phones_list. "
            "If unsure, tool_search then call the mcp__delno_office__… result. "
            "Never bare names, never terminal. Never claim a granted tool is unavailable. "
            "Critical writes need confirmation policy."
        )
    facts_block = _office_facts_block(office_context if isinstance(office_context, dict) else None)
    hermes_input = message
    if facts_block:
        hermes_input = (
            f"{facts_block}\n\n"
            "Ответь владельцу сам, своими словами как Гермес, строго по FACTS выше "
            "(и/или после вызова mcp__delno_office__hermes_setup_status). "
            "Не подставляй демо/чужой кабинет.\n\n"
            f"Сообщение владельца:\n{message}"
        )
    payload: dict[str, Any] = {
        "input": hermes_input,
        # Isolate sessions per tenant+conversation so demo memory cannot leak.
        "session_id": session_id
        or f"delno-{ctx.tenant_slug or ctx.tenant_id}-{ctx.user_id or 'owner'}",
        "instructions": (
            f"You are the company Hermes agent for THIS tenant only "
            f"(slug={ctx.tenant_slug}, profile={profile_id}). {mission}{context_line} "
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
