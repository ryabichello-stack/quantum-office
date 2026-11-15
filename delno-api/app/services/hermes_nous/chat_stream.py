"""SSE cabinet stream: live Hermes run events, then the exact POST /chat payload.

The turn itself runs through ``operator_chat`` in a worker thread, so every
onboarding fast-path (vault form, channel chooser, KB draft, pending MCP UI such
as ``credentials.open_form``) behaves exactly like /chat. While it runs we watch
for the Hermes run this tenant just started and proxy its tool events.
"""

from __future__ import annotations

import queue
import threading
import time
from typing import Any, Iterator

from app.core.tenant import TenantContext
from app.services.hermes_nous.live_events import format_sse, map_hermes_event

_RUN_WAIT_S = 240.0
_POLL_S = 0.4


def _recent_run_ids(db, ctx: TenantContext) -> set[str]:
    from app.models.agent_task import AgentRun

    rows = (
        db.query(AgentRun.id)
        .filter(AgentRun.tenant_id == ctx.tenant_id)
        .order_by(AgentRun.created_at.desc())
        .limit(40)
        .all()
    )
    return {str(r[0]) for r in rows}


def _find_new_remote_run(db, ctx: TenantContext, known: set[str]) -> str | None:
    """Hermes run id of a run this tenant started after the stream began. Never another tenant."""
    from app.models.agent_task import AgentRun

    db.expire_all()
    rows = (
        db.query(AgentRun)
        .filter(AgentRun.tenant_id == ctx.tenant_id)
        .order_by(AgentRun.created_at.desc())
        .limit(10)
        .all()
    )
    for row in rows:
        if str(row.id) in known:
            continue
        remote = (row.checkpoint or {}).get("remote_run_id")
        if remote:
            return str(remote)
    return None


def _drain(events: "queue.Queue[tuple[str, dict[str, Any]] | None]") -> Iterator[str]:
    """Yield queued in-process tool actions without blocking."""
    while True:
        try:
            item = events.get_nowait()
        except queue.Empty:
            return
        if item is None:
            continue
        name, mapped = item
        if mapped.get("phase") == "terminal":
            continue
        yield format_sse(name, {k: v for k, v in mapped.items() if v is not None})


def iter_chat_stream(ctx: TenantContext, body: Any) -> Iterator[str]:
    from fastapi import HTTPException

    from app.api.v1.operator import operator_chat
    from app.core.db import SessionLocal

    watch_db = SessionLocal()
    try:
        known = _recent_run_ids(watch_db, ctx)
    except Exception:
        known = set()

    box: dict[str, Any] = {}
    done = threading.Event()
    events: "queue.Queue[tuple[str, dict[str, Any]] | None]" = queue.Queue()

    def _worker() -> None:
        from app.services.hermes_nous.progress import progress_sink

        db = SessionLocal()
        try:
            # Fast paths call tools in this thread: forward each one as a live action.
            with progress_sink(lambda ev: events.put(("action", ev))):
                box["payload"] = operator_chat(body, db, ctx)
        except HTTPException as exc:
            box["http_error"] = exc
        except Exception as exc:  # noqa: BLE001 — surfaced as fallback, /chat will report
            box["error"] = exc
        finally:
            db.close()
            done.set()

    threading.Thread(target=_worker, name="delno-chat-stream", daemon=True).start()
    yield format_sse("action", {"phase": "thinking"})

    run_id: str | None = None
    deadline = time.monotonic() + _RUN_WAIT_S
    try:
        while not done.is_set() and run_id is None and time.monotonic() < deadline:
            yield from _drain(events)
            try:
                run_id = _find_new_remote_run(watch_db, ctx, known)
            except Exception:
                run_id = None
            if run_id is None:
                done.wait(_POLL_S)
    finally:
        watch_db.close()

    if run_id and not done.is_set():
        from app.services.hermes_nous.bridge import HermesBridgeError, iter_hermes_sse, resolve_runtime

        def _reader() -> None:
            rdb = SessionLocal()
            try:
                runtime = resolve_runtime(rdb, ctx)
                rdb.close()
                for name, data in iter_hermes_sse(runtime, run_id):
                    mapped = map_hermes_event(name, data)
                    if mapped:
                        events.put(("action", mapped))
                        if mapped.get("phase") == "terminal":
                            break
            except (HermesBridgeError, Exception):  # noqa: BLE001 — the final payload still arrives
                pass
            finally:
                try:
                    rdb.close()
                except Exception:
                    pass
                events.put(None)

        yield format_sse("started", {"run_id": run_id})
        threading.Thread(target=_reader, name="delno-chat-events", daemon=True).start()
        reader_open = True
        while reader_open or not done.is_set():
            if done.is_set() and not reader_open:
                break
            try:
                item = events.get(timeout=0.5)
            except queue.Empty:
                if done.is_set():
                    # Turn finished; drain whatever is already queued, then stop.
                    reader_open = False
                continue
            if item is None:
                reader_open = False
                continue
            name, mapped = item
            if mapped.get("phase") == "terminal":
                continue
            yield format_sse(name, {k: v for k, v in mapped.items() if v is not None})

    while not done.wait(_POLL_S):
        yield from _drain(events)
    yield from _drain(events)
    if "payload" in box:
        yield format_sse("done", box["payload"])
        return
    # Nothing was answered: let the cabinet retry through POST /chat.
    yield format_sse("fallback", {"reason": "error"})
