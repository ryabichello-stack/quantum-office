"""Stale agent_runs reconciler."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.models.agent_task import AgentRun
from app.models.tenant import Tenant
from app.services.hermes_nous.reconcile import reconcile_stale_runs


def test_reconcile_closes_orphan_running():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    t = Tenant(slug="rec-co", name="Rec", settings={})
    db.add(t)
    db.commit()
    db.refresh(t)
    old = datetime.now(timezone.utc) - timedelta(hours=2)
    run = AgentRun(
        id=uuid.uuid4(),
        tenant_id=t.id,
        hermes_run_id=None,
        status="running",
        started_at=old,
        result_summary="stuck",
    )
    db.add(run)
    db.commit()
    out = reconcile_stale_runs(db, older_than_minutes=30, limit=10)
    assert out["closed"] == 1
    db.refresh(run)
    assert run.status == "failed"
    assert run.error_code == "no_runtime_or_hermes_run_id"
    assert run.finished_at is not None
    db.close()
