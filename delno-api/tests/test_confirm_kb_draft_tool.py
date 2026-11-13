"""«положи в кб» must commit draft and close KB step — not loop upload confirms."""

from __future__ import annotations

import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.operator import _wants_confirm_kb_draft
from app.core.db import Base
from app.core.tenant import TenantContext
from app.models.tenant import Tenant
from app.models.user import User  # noqa: F401
from app.operator.tools import register_builtin_tools
from app.operator.tools.kb_build_tool import OfficeConfirmKbDraftTool
from app.operator.tools.registry import registry
from app.services.hermes_nous.onboarding import get_office_loop, save_kb_draft


def test_wants_confirm_kb_draft_phrases():
    assert _wants_confirm_kb_draft("положи в кб")
    assert _wants_confirm_kb_draft("Подтверди черновик")
    assert not _wants_confirm_kb_draft("давай дальше")


def test_confirm_kb_draft_tool_registered():
    register_builtin_tools()
    assert registry.get("office.confirm_kb_draft") is not None


def test_office_confirm_kb_draft_tool_commits(monkeypatch):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    tenant = Tenant(
        id=uuid.uuid4(),
        slug="confirm-kb",
        name="QL",
        settings={},
        is_active=True,
    )
    db.add(tenant)
    db.commit()
    ctx = TenantContext(tenant_id=tenant.id, tenant_slug=tenant.slug, role="tenant_owner")

    monkeypatch.setattr(
        "app.services.hermes_nous.onboarding.hermes_ops.office_setup_status",
        lambda *_a, **_k: {
            "setup_complete": False,
            "message_ru": "next",
            "progress": {},
            "checks": {"kb": {"ok": False}},
            "next_steps": [{"id": "phone", "title": "Телефон", "hint": "SIP"}],
        },
    )

    save_kb_draft(
        db,
        ctx,
        title="QL — коммерческий профиль",
        body="# Профиль\n\n## Услуги\nВыплаты\n" * 5,
        source_url="https://quantumpayouts.ru",
    )

    def fake_confirm(db_, ctx_):
        from datetime import datetime, timezone

        from app.services.hermes_nous.onboarding import _nous, _save_nous

        tenant_row = db_.query(Tenant).filter(Tenant.id == ctx_.tenant_id).one()
        nous = _nous(tenant_row)
        loop = dict(nous.get("office_loop") or {})
        draft = dict(loop.get("kb_draft") or {})
        draft["status"] = "committed"
        draft["committed_at"] = datetime.now(timezone.utc).isoformat()
        loop["kb_draft"] = draft
        loop["phase"] = "connectors"
        nous["office_loop"] = loop
        _save_nous(db_, tenant_row, nous)
        return {"ok": True, "committed": True, "loop": get_office_loop(db_, ctx_)}

    monkeypatch.setattr(
        "app.operator.tools.kb_build_tool.confirm_kb_draft",
        fake_confirm,
    )
    result = OfficeConfirmKbDraftTool().run(db, ctx)
    assert result.ok
    assert "KB" in (result.message or "")
    loop = get_office_loop(db, ctx)
    assert (loop.get("kb_draft") or {}).get("status") == "committed"
    db.close()
