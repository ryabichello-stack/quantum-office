"""Gate 2: a previous Owner conversation remains private and retrievable."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.hermes_nous import router as hermes_router
from app.core.auth import get_tenant_context_auth
from app.core.db import Base
from app.core.db import get_db
from app.core.tenant import TenantContext
from app.models.feature_flag import FeatureFlag
from app.models.tenant import Tenant
from app.models.user import User
from app.services.hermes_nous.owner_memory import recent_owner_context, remember_owner_turn


def test_completed_owner_turn_recalled_only_by_same_company_and_user(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'owner-memory.sqlite'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    with sessions() as db:
        a = Tenant(slug="company-a", name="Company A", settings={}, is_active=True)
        b = Tenant(slug="company-b", name="Company B", settings={}, is_active=True)
        db.add_all([a, b])
        db.flush()
        owner = User(tenant_id=a.id, email="owner-a@example.test", role="tenant_owner")
        colleague = User(tenant_id=a.id, email="colleague-a@example.test", role="tenant_admin")
        other = User(tenant_id=b.id, email="owner-b@example.test", role="tenant_owner")
        db.add_all([owner, colleague, other])
        db.commit()
        contexts = [
            TenantContext(tenant_id=a.id, tenant_slug=a.slug, user_id=owner.id, role=owner.role),
            TenantContext(tenant_id=a.id, tenant_slug=a.slug, user_id=colleague.id, role=colleague.role),
            TenantContext(tenant_id=b.id, tenant_slug=b.slug, user_id=other.id, role=other.role),
        ]
        assert remember_owner_turn(
            db, contexts[0], session_id="company-a:chat-yesterday", run_id="delno-run-1",
            request_text="Вчера согласовали цену. token: very-secret",
            response_text="Да, договорились о 5000 ₽. Bearer hidden-secret",
        )
        assert not remember_owner_turn(
            db, contexts[0], session_id="company-a:chat-yesterday", run_id="delno-run-1",
            request_text="Повтор", response_text="Повтор",
        )
        assert not remember_owner_turn(
            db, contexts[0], session_id="company-b:foreign", run_id="delno-run-2",
            request_text="Чужой", response_text="Чужой",
        )
        recalled = recent_owner_context(db, contexts[0])
        assert "5000" in recalled and "chat-yesterday" not in recalled
        assert "very-secret" not in recalled and "hidden-secret" not in recalled
        assert recent_owner_context(db, contexts[1]) == ""
        assert recent_owner_context(db, contexts[2]) == ""
    engine.dispose()


def test_next_owner_dialogue_receives_previous_turn_after_new_session(monkeypatch):
    monkeypatch.setenv("DELNO_OWNER_MEMORY_ENABLED", "1")
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    with sessions() as db:
        tenant = Tenant(slug="memory-owner", name="Memory Owner", settings={}, is_active=True)
        db.add(tenant)
        db.flush()
        owner = User(tenant_id=tenant.id, email="owner-memory@example.test", role="tenant_owner")
        db.add_all([owner, FeatureFlag(tenant_id=tenant.id, flag_key="hermes_nous_runtime", enabled=True),
                    FeatureFlag(tenant_id=tenant.id, flag_key="hermes_owner_memory", enabled=True)])
        db.commit()
        ctx = TenantContext(tenant_id=tenant.id, tenant_slug=tenant.slug, user_id=owner.id, role=owner.role)

        app = FastAPI()
        app.include_router(hermes_router, prefix="/v1")
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_tenant_context_auth] = lambda: ctx
        client = TestClient(app)
        outputs = [
            {"ok": True, "engine": "nous_hermes_agent", "output": "Договорились о 5000 ₽", "delno_run_id": "delno-1", "hermes": {"status": "completed"}},
            {"ok": True, "engine": "nous_hermes_agent", "output": "Вчера договорились о 5000 ₽", "delno_run_id": "delno-2", "hermes": {"status": "completed"}},
        ]
        with patch("app.api.v1.hermes_nous.create_run", side_effect=outputs) as create:
            first = client.post("/v1/hermes-nous/runs", json={"message": "Цена 5000 ₽", "conversation_id": "yesterday", "mode": "conduct"})
            second = client.post("/v1/hermes-nous/runs", json={"message": "О чём говорили вчера?", "conversation_id": "today", "mode": "conduct"})
        assert first.status_code == second.status_code == 200
        assert create.call_args_list[0].kwargs["owner_history"] == ""
        assert "5000" in create.call_args_list[1].kwargs["owner_history"]
        assert create.call_args_list[1].kwargs["session_id"] == "memory-owner:today"
        listed = client.get("/v1/hermes-nous/memory/turns")
        assert listed.status_code == 200 and len(listed.json()["items"]) == 2
        cleared = client.delete("/v1/hermes-nous/memory/turns")
        assert cleared.status_code == 200 and cleared.json()["deleted"] == 2
        assert client.get("/v1/hermes-nous/memory/turns").json()["items"] == []
    engine.dispose()
