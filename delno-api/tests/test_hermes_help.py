"""Hermes «Помощь» — freeze conversation + office state."""

from __future__ import annotations

import uuid
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.core.tenant import TenantContext
from app.models.conversation import Conversation, Message
from app.models.tenant import Tenant
from app.models.user import User  # noqa: F401
from app.services.hermes_help import (
    HELP_EVENT,
    capture_help_request,
    get_help_request,
    list_help_requests,
)
from app.models.platform_event import PlatformEvent


def _ctx():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    tenant = Tenant(
        id=uuid.uuid4(),
        slug="help-co",
        name="Help Co",
        settings={},
        is_active=True,
    )
    db.add(tenant)
    db.commit()
    ctx = TenantContext(tenant_id=tenant.id, tenant_slug=tenant.slug, role="tenant_owner")
    return db, ctx, tenant


def test_capture_help_freezes_messages_and_redacts_secrets():
    db, ctx, tenant = _ctx()
    conv = Conversation(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        channel="hermes",
        status="open",
        meta={},
    )
    db.add(conv)
    db.add(
        Message(
            tenant_id=tenant.id,
            conversation_id=conv.id,
            role="user",
            body="Вот сайт acme.ru — собери базу",
            meta={"modality": "text"},
        )
    )
    db.add(
        Message(
            tenant_id=tenant.id,
            conversation_id=conv.id,
            role="user",
            body="password: SuperSecret123!",
            meta={},
        )
    )
    db.commit()

    with (
        patch(
            "app.services.hermes_ops.office_setup_status",
            return_value={
                "setup_complete": False,
                "progress": {"required_done": 0, "required_total": 5},
                "checks": {"kb": {"ok": False, "title": "О компании"}},
                "next_steps": [{"id": "kb", "title": "О компании", "hint": "сайт"}],
                "message_ru": "next",
            },
        ),
        patch(
            "app.services.hermes_nous.onboarding.get_office_loop",
            return_value={
                "phase": "company_kb",
                "kb_ok": False,
                "setup_next": {"id": "kb", "title": "О компании"},
                "kb_draft": {
                    "status": "draft",
                    "title": "Acme",
                    "body": "Услуги B2B" * 200,
                    "source_url": "https://acme.ru",
                },
            },
        ),
    ):
        out = capture_help_request(
            db,
            ctx,
            conversation_id=conv.id,
            note="Форма SIP не открылась после «делай»",
            client_meta={"path": "/dashboard/hermes", "password": "should-drop"},
        )

    assert out["ok"] is True
    assert out["ticket_id"]
    ticket = get_help_request(db, ticket_id=out["ticket_id"], tenant_id=tenant.id)
    assert ticket is not None
    assert ticket["note"].startswith("Форма SIP")
    assert ticket["message_count"] >= 2
    bodies = [m["body"] for m in ticket["messages"]]
    assert any("acme.ru" in b for b in bodies)
    assert not any("SuperSecret123" in b for b in bodies)
    assert "password" not in (ticket.get("client") or {})
    assert ticket["office_loop"]["phase"] == "company_kb"
    assert "body_preview" in ticket["office_loop"]["kb_draft"]

    events = (
        db.query(PlatformEvent)
        .filter(PlatformEvent.tenant_id == tenant.id, PlatformEvent.event_type == HELP_EVENT)
        .all()
    )
    assert len(events) == 1

    listed = list_help_requests(db, tenant_id=tenant.id)
    assert len(listed) == 1
    assert listed[0]["ticket_id"] == out["ticket_id"]

    # Ack message landed in chat
    msgs = (
        db.query(Message)
        .filter(Message.conversation_id == conv.id)
        .order_by(Message.created_at.asc())
        .all()
    )
    assert any((m.meta or {}).get("kind") == "help_ack" for m in msgs)
    db.close()


def test_capture_without_conversation_still_saves_setup():
    db, ctx, tenant = _ctx()
    with (
        patch(
            "app.services.hermes_ops.office_setup_status",
            return_value={
                "setup_complete": False,
                "progress": {},
                "checks": {},
                "next_steps": [],
            },
        ),
        patch(
            "app.services.hermes_nous.onboarding.get_office_loop",
            return_value={"phase": "welcome", "kb_ok": False},
        ),
    ):
        out = capture_help_request(db, ctx, note="пусто", client_meta={})
    assert out["ok"]
    assert out["message_count"] == 0
    db.close()
