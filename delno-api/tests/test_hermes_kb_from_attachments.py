"""KB draft from image/PDF attachments during onboarding."""

from __future__ import annotations

import base64
import uuid
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.core.tenant import TenantContext
from app.models.tenant import Tenant
from app.models.user import User  # noqa: F401
from app.services.hermes_kb_from_attachments import (
    try_kb_draft_from_attachments,
    wants_kb_from_attachments,
)
from app.services.operator_attachments import normalize_attachments


def _tenant_ctx():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    tenant = Tenant(
        id=uuid.uuid4(),
        slug="attach-kb",
        name="Attach Co",
        settings={},
        is_active=True,
    )
    db.add(tenant)
    db.commit()
    ctx = TenantContext(tenant_id=tenant.id, tenant_slug=tenant.slug, role="tenant_owner")
    return db, ctx


def test_wants_kb_hints_and_bare_attachment():
    fake = {"items": [{"kind": "image"}]}
    assert wants_kb_from_attachments("положи в базу знаний", fake)
    assert wants_kb_from_attachments("это наше КП", fake)
    assert wants_kb_from_attachments("презентация компании", fake)
    assert wants_kb_from_attachments("", fake)
    assert wants_kb_from_attachments("ок", fake)
    assert not wants_kb_from_attachments(
        "что на фото, просто опиши подробно для меня",
        fake,
    )


def test_file_attachment_builds_kb_draft():
    db, ctx = _tenant_ctx()
    raw = base64.b64encode(
        (
            "Коммерческое предложение Attach Co.\n"
            "Услуги: B2B выплаты ломбардам, комиссия от 0.4%.\n"
            "Контакт: sales@attach.ru. ICP — МФО и скупка."
        ).encode("utf-8")
    ).decode("ascii")
    normalized = normalize_attachments(
        [{"filename": "kp.txt", "content_type": "text/plain", "data_base64": raw}]
    )
    assert normalized["ok"]
    with (
        patch(
            "app.services.hermes_kb_from_attachments.hermes_ops.office_setup_status",
            return_value={"checks": {"kb": {"ok": False}}},
        ),
        patch(
            "app.services.hermes_kb_build.web_browser.search_web",
            return_value={"ok": True, "items": []},
        ),
        patch(
            "app.services.hermes_nous.onboarding.hermes_ops.office_setup_status",
            return_value={
                "setup_complete": False,
                "message_ru": "next",
                "progress": {},
                "checks": {"kb": {"ok": False}},
                "next_steps": [{"id": "kb", "title": "О компании", "hint": "сайт"}],
            },
        ),
    ):
        out = try_kb_draft_from_attachments(
            db, ctx, "Вот наше КП — собери базу", normalized
        )
    assert out is not None
    assert out["reply"]
    tools = {t.get("tool") for t in out["tool_calls"]}
    assert "office.build_kb_draft" in tools
    assert any(t.get("tool") == "office.build_kb_draft" and t.get("ok") for t in out["tool_calls"])
    assert "0.4" in out["reply"] or "выплат" in out["reply"].lower() or "Attach" in out["reply"]
    db.close()


def test_image_attachment_vision_then_draft():
    db, ctx = _tenant_ctx()
    png_1x1 = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    normalized = normalize_attachments(
        [
            {
                "filename": "kp-slide.png",
                "content_type": "image/png",
                "data_base64": base64.b64encode(png_1x1).decode("ascii"),
            }
        ]
    )
    assert normalized["vision_parts"]

    vision_text = (
        "Кто мы: Attach Vision LLC\n"
        "Продукты: офисный ИИ для ломбардов, тариф 9900₽/мес\n"
        "Контакты: hello@attach.ru"
    )

    with (
        patch(
            "app.services.hermes_kb_from_attachments.hermes_ops.office_setup_status",
            return_value={"checks": {"kb": {"ok": False}}},
        ),
        patch(
            "app.services.hermes_kb_from_attachments._vision_extract_commercial",
            return_value={"ok": True, "text": vision_text, "provider": "test"},
        ),
        patch(
            "app.services.hermes_kb_build.web_browser.search_web",
            return_value={"ok": True, "items": []},
        ),
        patch(
            "app.services.hermes_nous.onboarding.hermes_ops.office_setup_status",
            return_value={
                "setup_complete": False,
                "message_ru": "next",
                "progress": {},
                "checks": {"kb": {"ok": False}},
                "next_steps": [{"id": "kb", "title": "О компании", "hint": "сайт"}],
            },
        ),
    ):
        out = try_kb_draft_from_attachments(db, ctx, "", normalized)

    assert out is not None
    assert any(t.get("tool") == "vision.extract_commercial" and t.get("ok") for t in out["tool_calls"])
    assert any(t.get("tool") == "office.build_kb_draft" and t.get("ok") for t in out["tool_calls"])
    assert "9900" in out["reply"] or "ломбард" in out["reply"].lower() or "Attach" in out["reply"]
    db.close()


def test_skips_when_kb_ready_and_no_hint():
    db, ctx = _tenant_ctx()
    normalized = {
        "ok": True,
        "items": [{"kind": "image", "filename": "cat.png"}],
        "vision_parts": [{"type": "image_url", "image_url": {"url": "data:image/png;base64,xx"}}],
        "text_context": "",
        "summary_labels": ["🖼 cat.png"],
    }
    with patch(
        "app.services.hermes_kb_from_attachments.hermes_ops.office_setup_status",
        return_value={"checks": {"kb": {"ok": True}}},
    ):
        out = try_kb_draft_from_attachments(
            db, ctx, "что на этом фото, опиши подробно для меня", normalized
        )
    assert out is None
    db.close()
