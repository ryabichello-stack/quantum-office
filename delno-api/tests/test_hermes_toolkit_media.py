"""Toolkit inventory + generate_image registration."""

from __future__ import annotations

import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.core.tenant import TenantContext
from app.models.feature_flag import FeatureFlag
from app.models.tenant import Tenant
from app.models.user import User  # noqa: F401
from app.operator.tools import register_builtin_tools
from app.operator.tools.registry import registry
from app.services.hermes_nous.toolkit import get_toolkit


def test_generate_image_registered():
    register_builtin_tools()
    tool = registry.get("generate_image")
    assert tool is not None
    assert "prompt" in (tool.parameters_schema.get("properties") or {})


def test_toolkit_includes_ava_tools(monkeypatch):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    tenant = Tenant(id=uuid.uuid4(), slug="t-kit", name="Kit", settings={}, is_active=True)
    db.add(tenant)
    db.commit()
    ctx = TenantContext(tenant_id=tenant.id, tenant_slug=tenant.slug, role="tenant_owner")

    monkeypatch.setattr(
        "app.services.hermes_nous.toolkit.hermes_ops.office_setup_status",
        lambda *_a, **_k: {
            "setup_complete": False,
            "message_ru": "setup",
            "progress": {},
            "checks": {"telephony": {"ok": False, "detail": "need DID"}},
        },
    )
    monkeypatch.setattr(
        "app.services.hermes_nous.toolkit.hermes_ops.office_health_report",
        lambda *_a, **_k: {"healthy": True, "message_ru": "ok", "alerts": []},
    )
    monkeypatch.setattr(
        "app.services.hermes_nous.toolkit.list_tenant_connector_readiness",
        lambda *_a, **_k: [{"kind": "mail", "usable": True, "label": "Почта"}],
    )

    out = get_toolkit(db, ctx)
    assert out["ok"] is True
    assert out["ava"]["tools"]
    assert any(t["id"] == "telephony.tools_set" for t in out["ava"]["tools"])
    assert any(t["id"] == "generate_image" for t in out["media"]["tools"])
    db.close()
