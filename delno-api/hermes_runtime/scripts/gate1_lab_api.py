"""Isolated SQLite MCP test service for the Gate 1 Hermes pool lab.

Run on an internal Docker network only. Seeds disposable tenants and writes
their *test-only* run credentials to /data/identities.json for the smoke test.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.v1.mcp import router as mcp_router
from app.core.db import Base, get_db
from app.core.tenant import TenantContext
from app.models.tenant import Tenant
from app.models.user import User
from app.models.agent_task import AgentRun, AgentTask
from app.models.platform_event import PlatformEvent
from app.operator.tools import register_builtin_tools
from app.services.hermes_nous.run_bindings import bind_run_token
from app.services.hermes_nous.run_tokens import issue_run_token
from app.services.mcp_gateway import ensure_mcp_api_key


data_dir = Path("/data")
data_dir.mkdir(parents=True, exist_ok=True)
engine = create_engine(f"sqlite:///{data_dir / 'gate1.sqlite'}", connect_args={"check_same_thread": False})
Base.metadata.create_all(engine)
sessions = sessionmaker(bind=engine, expire_on_commit=False)
register_builtin_tools()
app = FastAPI()
app.include_router(mcp_router, prefix="/v1")


def db_dependency():
    with sessions() as db:
        yield db


app.dependency_overrides[get_db] = db_dependency

identity_file = data_dir / "identities.json"
if not identity_file.exists():
    identities = []
    with sessions() as db:
        for i in range(2):
            slug = f"gate-{i}"
            tenant = Tenant(slug=slug, name=f"Gate company {i}", settings={}, is_active=True)
            db.add(tenant)
            db.flush()
            user = User(tenant_id=tenant.id, email=f"gate-{i}@example.test", role="tenant_owner")
            db.add(user)
            db.commit()
            db.refresh(tenant)
            db.refresh(user)
            key = ensure_mcp_api_key(db, tenant)
            ctx = TenantContext(tenant_id=tenant.id, tenant_slug=slug, user_id=user.id, role=user.role)
            profile_id = f"tenant_gate-{i}__company_main"
            for kind in ("owner", "background"):
                scoped_ctx = ctx if kind == "owner" else TenantContext(
                    tenant_id=tenant.id, tenant_slug=slug, user_id=None, role="system")
                run_id = f"gate1_{kind}_run_{i}"
                token = issue_run_token(db, scoped_ctx, run_id=run_id,
                                        tool_ids=["get_tenant_summary", "send_mail_draft"])
                task_id = None
                if kind == "background":
                    task = AgentTask(tenant_id=tenant.id, owner_user_id=None,
                                     goal="Summarize company", trigger_kind="schedule")
                    db.add(task)
                    db.flush()
                    task_id = task.id
                db.add(AgentRun(tenant_id=tenant.id, task_id=task_id,
                                hermes_run_id=run_id, status="running"))
                db.commit()
                bind_run_token(
                    db, tenant_id=tenant.id, profile_id=profile_id, worker_id="pool",
                    run_id=run_id, session_id=f"{slug}:{kind}:test",
                    actor_user_id=scoped_ctx.user_id, agent_id="company_main",
                    raw_token=token.token, tool_ids=token.tool_ids,
                    expires_at_unix=token.expires_at,
                )
                identities.append({"tenant_id": str(tenant.id), "tenant_slug": slug,
                                   "profile": profile_id,
                                   "run_id": run_id, "token": token.token,
                                   "legacy_key": key, "kind": kind,
                                   "grants": token.tool_ids})
    identity_file.write_text(json.dumps(identities), encoding="utf-8")
    identity_file.chmod(0o600)


@app.get("/lab/evidence")
def evidence():
    with sessions() as db:
        rows = db.query(PlatformEvent).filter(PlatformEvent.event_type == "mcp.tool_called").all()
        return [{"tenant_id": str(row.tenant_id), "tool": row.payload.get("tool"),
                 "auth_via": row.payload.get("auth_via"),
                 "run_id": row.payload.get("run_id")} for row in rows]
