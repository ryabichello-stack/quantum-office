"""Server-side run bindings authorize MCP without legacy company key."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.models.hermes_runtime import HermesRunBinding
from app.models.tenant import Tenant
from app.services.hermes_nous.run_bindings import bind_run_token, lookup_binding


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
