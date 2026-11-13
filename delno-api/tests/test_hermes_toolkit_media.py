"""Toolkit inventory + generate_image registration."""

from __future__ import annotations

import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.operator import (
    _calendar_duration_min,
    _calendar_slot_start_iso,
    _conference_provider,
    _conference_title,
    _wants_calendar_slots,
    _wants_conference_create,
    _wants_media_generation,
)
from app.core.db import Base
from app.core.tenant import TenantContext
from app.models.feature_flag import FeatureFlag
from app.models.tenant import Tenant
from app.models.user import User  # noqa: F401
from app.operator.tools import register_builtin_tools
from app.operator.tools.media import GenerateImageTool
from app.operator.tools.registry import ToolResult, registry
from app.services.hermes_nous.toolkit import get_toolkit


def test_generate_image_registered():
    register_builtin_tools()
    tool = registry.get("generate_image")
    assert tool is not None
    assert "prompt" in (tool.parameters_schema.get("properties") or {})


def test_wants_media_generation_routes():
    assert _wants_media_generation("Сгенерируй картинку: робот")
    assert _wants_media_generation("сгенерируй простую картинку: синий квадрат")
    assert _wants_media_generation("Сделай мокап обложки для лендинга")
    assert _wants_media_generation("Please generate an image of a cat")
    assert not _wants_media_generation("Какие звонки были сегодня?")
    assert not _wants_media_generation("Создай конференцию на завтра")


def test_wants_calendar_slots_routes():
    assert _wants_calendar_slots("предложи свободные слоты календаря на завтра на час")
    assert _wants_calendar_slots("Подбери встречу на завтра утром")
    assert not _wants_calendar_slots("что в календаре?")
    assert _calendar_duration_min("на час") == 60
    assert _calendar_duration_min("на 30 минут") == 30
    start = _calendar_slot_start_iso("завтра утром")
    assert "+03:00" in start or "+03" in start


def test_wants_conference_create_routes():
    msg = "создай видеовстречу Telemost на завтра в 11:00, название Демо DELNO"
    assert _wants_conference_create(msg)
    assert _conference_provider(msg) == "yandex"
    assert "Демо DELNO" in _conference_title(msg)
    assert not _wants_conference_create("создай картинку кота")
    assert not _wants_media_generation(msg)


def test_generate_image_prefers_proxy_friendly_models(monkeypatch):
    """RU proxy often exposes gpt-image-1-mini / chatgpt-image-latest only."""
    register_builtin_tools()
    calls: list[dict] = []

    class _Resp:
        def __init__(self, status: int, payload: dict):
            self.status_code = status
            self._payload = payload
            self.text = str(payload)

        def json(self):
            return self._payload

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, headers=None, json=None):
            calls.append(json or {})
            model = (json or {}).get("model")
            if model == "gpt-image-1-mini":
                return _Resp(200, {"data": [{"b64_json": "aaa"}]})
            return _Resp(400, {"error": {"message": f"The model '{model}' does not exist."}})

    monkeypatch.setattr("app.operator.tools.media.httpx.Client", _Client)
    monkeypatch.setattr(
        "app.operator.tools.media.get_settings",
        lambda: type(
            "S",
            (),
            {
                "openai_api_key": "sk-test",
                "openai_base_url": "https://api.openai.com/v1",
                "openai_http_proxy": "http://127.0.0.1:10808",
            },
        )(),
    )

    tool = GenerateImageTool()
    result = tool.run(None, None, prompt="yellow circle logo")  # type: ignore[arg-type]
    assert isinstance(result, ToolResult)
    assert result.ok is True
    assert (result.data or {}).get("model") == "gpt-image-1-mini"
    assert str((result.data or {}).get("markdown") or "").startswith("![Hermes image](data:image/png;base64,")
    assert calls and calls[0].get("model") == "gpt-image-1-mini"


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
            "checks": {
                "phone": {
                    "ok": False,
                    "detail": {
                        "active_dids": 0,
                        "sip_configured": False,
                        "registration_ok": True,
                        "registration_message": "Registered",
                    },
                },
                "telephony_script": {"ok": True, "detail": {"configured": True, "tools": ["hangup_call"]}},
            },
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
    assert out["ava"]["script_ready"] is True
    assert "сценарий готов" in (out["ava"]["detail"] or "")
    assert any(t["id"] == "telephony.tools_set" for t in out["ava"]["tools"])
    assert any(t["id"] == "generate_image" for t in out["media"]["tools"])
    db.close()
