"""Server-side run bindings authorize MCP without legacy company key."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.core.tenant import TenantContext
from app.models.hermes_runtime import HermesRunBinding
from app.models.tenant import Tenant
from app.api.v1.mcp import get_mcp_tenant_context
from app.services.hermes_nous.run_bindings import bind_run_token, lookup_binding
from app.services.hermes_nous.run_tokens import issue_run_token
from app.services.mcp_gateway import ensure_mcp_api_key


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_bind_and_lookup(db):
    t = Tenant(slug="bind-co", name="Bind", settings={})
    db.add(t)
    db.commit()
    db.refresh(t)
    exp = int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())
    row = bind_run_token(
        db,
        tenant_id=t.id,
        profile_id="tenant_bind-co__company_main",
        worker_id="tenant-a",
        run_id="delno_abc123",
        session_id="bind-co:conv1",
        actor_user_id=None,
        agent_id="company_main",
        raw_token="dnrt_test_token_value",
        tool_ids=["hermes.setup_status", "get_knowledge"],
        expires_at_unix=exp,
    )
    assert isinstance(row, HermesRunBinding)
    found = lookup_binding(db, run_id="delno_abc123")
    assert found is not None
    assert found.tenant_id == t.id
    assert "get_knowledge" in (found.tool_ids or [])
    assert lookup_binding(db, run_id="missing") is None


def test_run_id_requires_credential_from_bound_tenant(db):
    owner = Tenant(slug="owner-co", name="Owner", settings={})
    other = Tenant(slug="other-co", name="Other", settings={})
    db.add_all([owner, other])
    db.commit()
    owner_key = ensure_mcp_api_key(db, owner)
    other_key = ensure_mcp_api_key(db, other)
    issued = issue_run_token(db, TenantContext(
        tenant_id=owner.id, tenant_slug=owner.slug, user_id=None, role="system",
    ), run_id="delno_owner_run", tool_ids=["get_knowledge"])
    bind_run_token(
        db, tenant_id=owner.id, profile_id="tenant_owner-co__company_main",
        worker_id="pool", run_id="delno_owner_run", session_id="owner-co:conv1",
        actor_user_id=None, agent_id="company_main", raw_token=issued.token,
        tool_ids=["get_knowledge"],
        expires_at_unix=int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
    )

    def auth(key=None, profile=None):
        return get_mcp_tenant_context(
            db=db,
            credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials=key) if key else None,
            x_api_key=None, x_delno_mcp_key=None, x_delno_run_token=None,
            x_delno_run_id="delno_owner_run", x_delno_profile_id=profile,
        )

    with pytest.raises(HTTPException) as missing:
        auth()
    assert missing.value.status_code == 401
    with pytest.raises(HTTPException) as foreign:
        auth(other_key)
    assert foreign.value.status_code == 403
    with pytest.raises(HTTPException) as wrong_profile:
        auth(owner_key, "tenant_other-co__company_main")
    assert wrong_profile.value.status_code == 403
    permitted = auth(owner_key, "tenant_owner-co__company_main")
    assert permitted.tenant.tenant_id == owner.id
    assert permitted.run_token_tool_ids == ["get_knowledge"]
