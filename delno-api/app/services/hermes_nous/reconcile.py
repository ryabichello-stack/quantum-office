"""Reconcile stuck DELNO agent_runs against Hermes upstream status.

Codex Stage 4: no infinite ``running`` without an active upstream run.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.agent_task import AgentRun
from app.models.hermes_runtime import HermesProfile, HermesWorker


def _http_json(method: str, url: str, *, api_key: str, timeout: float = 15.0) -> tuple[int, Any]:
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        },
        method=method,
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            body: Any = json.loads(raw) if raw.strip() else {}
            return int(resp.status), body
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw) if raw.strip() else {"raw": raw}
        except json.JSONDecodeError:
            body = {"raw": raw}
        return int(exc.code), body
    except urllib.error.URLError as exc:
        return 0, {"error": "unreachable", "reason": str(exc.reason)}


def _runtime_for_tenant(db: Session, tenant_id: UUID) -> dict[str, str] | None:
    profile = (
        db.query(HermesProfile)
        .filter(HermesProfile.tenant_id == tenant_id, HermesProfile.agent_id == "company_main")
        .one_or_none()
    )
    if not profile or not profile.worker_id:
        return None
    worker = db.query(HermesWorker).filter(HermesWorker.worker_id == profile.worker_id).one_or_none()
    if not worker:
        return None
    key = os.environ.get(worker.api_server_key_env or "") or ""
    if not key:
        return None
    return {"base_url": worker.base_url.rstrip("/"), "api_key": key, "profile_id": profile.profile_id}


def reconcile_stale_runs(
    db: Session,
    *,
    older_than_minutes: int = 30,
    limit: int = 50,
    tenant_id: UUID | None = None,
) -> dict[str, Any]:
    """Mark long-running DELNO runs as failed/completed based on upstream or age."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=max(1, older_than_minutes))
    q = db.query(AgentRun).filter(AgentRun.status == "running", AgentRun.started_at.isnot(None))
    if tenant_id is not None:
        q = q.filter(AgentRun.tenant_id == tenant_id)
    q = q.filter(AgentRun.started_at < cutoff).order_by(AgentRun.started_at.asc()).limit(limit)
    runs = q.all()
    closed = 0
    checked = 0
    details: list[dict[str, Any]] = []
    for run in runs:
        checked += 1
        runtime = _runtime_for_tenant(db, run.tenant_id)
        new_status = "failed"
        error_code = "stale_running_reconciled"
        summary = run.result_summary
        if runtime and run.hermes_run_id:
            status_code, body = _http_json(
                "GET",
                f"{runtime['base_url']}/v1/runs/{run.hermes_run_id}",
                api_key=runtime["api_key"],
            )
            if status_code == 200 and isinstance(body, dict):
                up = str(body.get("status") or body.get("state") or "").lower()
                if up in ("completed", "succeeded", "success", "done"):
                    new_status = "completed"
                    error_code = None
                    summary = summary or str(body.get("output") or "")[:2000]
                elif up in ("running", "in_progress", "queued"):
                    # Still live upstream — leave alone
                    details.append(
                        {
                            "delno_run_id": str(run.id),
                            "hermes_run_id": run.hermes_run_id,
                            "action": "keep_running",
                            "upstream": up,
                        }
                    )
                    continue
                elif up in ("failed", "error", "cancelled", "canceled", "stopped"):
                    new_status = "failed" if up != "cancelled" and up != "canceled" and up != "stopped" else "cancelled"
                    error_code = f"upstream_{up}"
            elif status_code in (404, 410):
                new_status = "failed"
                error_code = "upstream_run_missing"
            else:
                new_status = "failed"
                error_code = "upstream_unreachable_or_stale"
        else:
            error_code = "no_runtime_or_hermes_run_id"

        run.status = new_status
        run.error_code = error_code
        if summary:
            run.result_summary = summary[:2000]
        run.finished_at = datetime.now(timezone.utc)
        cp = dict(run.checkpoint or {})
        cp["reconciled_at"] = datetime.now(timezone.utc).isoformat()
        cp["reconcile_error"] = error_code
        run.checkpoint = cp
        db.add(run)
        closed += 1
        details.append(
            {
                "delno_run_id": str(run.id),
                "hermes_run_id": run.hermes_run_id,
                "action": new_status,
                "error_code": error_code,
            }
        )
    if closed:
        db.commit()
    return {"ok": True, "checked": checked, "closed": closed, "items": details}
