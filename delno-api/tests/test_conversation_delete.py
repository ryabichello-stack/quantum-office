import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.core.tenant import TenantContext
from app.models.conversation import Conversation, Message
from app.models.tenant import Tenant
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.operator import router as operator_router
from app.core.db import get_db
from app.core.auth import get_tenant_context_auth


def _db():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_delete_conversation_removes_messages():
    db = _db()
    tenant = Tenant(slug="del", name="Del", settings={}, is_active=True)
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    conv = Conversation(tenant_id=tenant.id, channel="hermes")
    db.add(conv)
    db.flush()
    db.add(Message(tenant_id=tenant.id, conversation_id=conv.id, role="user", body="hi"))
    db.commit()

    app = FastAPI()
    app.include_router(operator_router, prefix="/v1")

    def _override_db():
        yield db

    def _override_ctx():
        return TenantContext(tenant_id=tenant.id, tenant_slug=tenant.slug, role="tenant_owner")

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_tenant_context_auth] = _override_ctx
    client = TestClient(app)
    res = client.delete(f"/v1/operator/conversations/{conv.id}")
    assert res.status_code == 200
    assert res.json()["ok"] is True
    assert db.query(Conversation).count() == 0
    assert db.query(Message).count() == 0
