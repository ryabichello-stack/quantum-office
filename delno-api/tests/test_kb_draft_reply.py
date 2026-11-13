"""KB draft must reach the owner — not die behind max_tokens=900 / empty get_knowledge."""

from __future__ import annotations

import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.operator import _wants_kb_agent_work, _wants_show_kb_findings
from app.core.db import Base
from app.core.tenant import TenantContext
from app.models.tenant import Tenant
from app.models.user import User  # noqa: F401
from app.operator.agent import _kb_draft_user_reply, _prefer_kb_draft_in_reply, _tool_result_for_llm
from app.operator.tools.builtin import GetKnowledgeTool
from app.operator.tools.registry import ToolResult
from app.services.hermes_nous.onboarding import save_kb_draft


def test_show_findings_routes_to_kb_agent():
    assert _wants_show_kb_findings("покажи что нашелнаний")
    assert _wants_kb_agent_work("покажи что нашёл")
    assert _wants_kb_agent_work("покажи черновик")


def test_prefer_kb_draft_replaces_thin_summary():
    draft = "Собрал черновик\n\n## 1. Кто мы\nQuantum Payouts\n" + ("услуги " * 200)
    tools = [
        {
            "tool": "office.build_kb_draft",
            "ok": True,
            "message": draft[:500],
            "full_message": draft,
        }
    ]
    out = _prefer_kb_draft_in_reply("Собрал черновик, подтвердите.", tools)
    assert "## 1. Кто мы" in out
    assert "Quantum Payouts" in out
    assert _kb_draft_user_reply(tools) == draft.strip()


def test_tool_result_keeps_long_kb_body():
    body = "# Профиль\n\n## Услуги\n" + ("x" * 5000)
    result = ToolResult(
        ok=True,
        message="Собрал коммерческий черновик\n\n" + body,
        data={"kb_draft": {"status": "draft"}, "body": body, "chars": len(body), "title": "T"},
    )
    raw = _tool_result_for_llm(result)
    assert "kb_draft" in raw
    assert len(raw) > 4000


def test_get_knowledge_returns_office_loop_draft_when_kb_empty():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    tenant = Tenant(
        id=uuid.uuid4(),
        slug="kb-draft-show",
        name="QL",
        settings={},
        is_active=True,
    )
    db.add(tenant)
    db.commit()
    ctx = TenantContext(tenant_id=tenant.id, tenant_slug=tenant.slug, role="tenant_owner")

    body = "# Quantum\n\n## Услуги\nВыплаты на карты\n" * 20
    save_kb_draft(db, ctx, title="QL draft", body=body, source_url="https://quantumpayouts.ru")

    class EmptyAdapter:
        def search(self, *_a, **_k):
            return {"ok": True, "matches": [], "text": "", "chars": 0}

    tool = GetKnowledgeTool(adapter=EmptyAdapter())  # type: ignore[arg-type]
    result = tool.run(db, ctx, query="quantumpayouts.ru")
    assert result.ok
    assert result.data.get("kb_draft") is True
    assert "Выплаты на карты" in (result.message or "")
    assert len(result.data.get("body") or "") > 100
    db.close()
