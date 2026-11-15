"""In-call /v1/telephony/calls/tool gateway."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.core.tenant import TenantContext
from app.models.call_session import CallSession  # noqa: F401
from app.models.conversation import Conversation  # noqa: F401
from app.models.phone_number import PhoneNumber  # noqa: F401
from app.models.platform_event import PlatformEvent  # noqa: F401
from app.models.tenant import Tenant
from app.services import phone_provision, telephony, telephony_script, voice_tools


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def _tenant(db, slug="quantum-labs") -> Tenant:
    t = db.query(Tenant).filter(Tenant.slug == slug).one_or_none()
    if t:
        return t
    t = Tenant(id=uuid.uuid4(), slug=slug, name="Quantum Labs", settings={}, is_active=True)
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def test_voice_tool_list_and_knowledge(db, monkeypatch):
    tenant = _tenant(db)
    ctx = TenantContext(tenant_id=tenant.id, tenant_slug=tenant.slug, role="tenant_owner")
    phone_provision.provision_phone(db, ctx, e164="+79699665899")
    telephony_script.save_telephony_script(
        db,
        ctx,
        script=(
            "## Приветствие\n"
            "Добрый день! Вы позвонили в Quantum Labs. Чем могу помочь?\n\n"
            "## Задачи\n"
            "- Отвечать из базы знаний\n"
            "- Писать на встречу\n"
        ),
        greeting="Добрый день! Вы позвонили в Quantum Labs. Чем могу помочь?",
        tools=["get_company_knowledge", "check_calendar", "hangup_call"],
        publish_knowledge=False,
    )
    started = telephony.start_inbound_call(
        db,
        did="+79699665899",
        from_number="+79001112233",
        external_id="ast-tool-1",
        trunk_id="delno-quantum-labs",
    )
    assert started["ok"] is True
    assert started["secretary"]["configured"] is True
    assert "get_company_knowledge" in started["secretary"]["tools"]

    listed = voice_tools.dispatch(
        db, call_id="ast-tool-1", action="list_enabled_tools", params={}
    )
    assert listed["ok"] is True
    assert listed["tenant_slug"] == "quantum-labs"
    ids = {t["id"] for t in listed["tools"]}
    assert "get_company_knowledge" in ids

    class _Fake:
        def run(self, db, ctx, **kwargs):
            from app.operator.tools.registry import ToolResult

            return ToolResult(ok=True, message="ok", data={"answer": "выплаты"})

    monkeypatch.setattr(
        "app.operator.tools.builtin.GetKnowledgeTool",
        lambda *a, **k: _Fake(),
    )
    know = voice_tools.dispatch(
        db,
        call_id="ast-tool-1",
        action="get_company_knowledge",
        params={"query": "что вы делаете"},
    )
    assert know["ok"] is True
    assert know["data"]["answer"] == "выплаты"
