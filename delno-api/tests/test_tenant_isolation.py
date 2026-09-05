"""E0.13 — delno-api tenant context must not leak across tenants."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from app.adapters.knowledge import KnowledgeAdapter
from app.core.principals import (
    PRINCIPAL_TEXT_GUEST,
    PRINCIPAL_TEXT_OWNER,
    PRINCIPAL_WIDGET_GUEST,
    brain_principal_id,
    principal_for_operator,
    principal_for_public_channel,
)
from app.core.tenant import TenantContext
from app.operator.tools.builtin import GetKnowledgeTool


class RecordingAdapter:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def search(self, query: str, *, tenant_slug: str, principal_id: str, limit: int = 5, mode: str = "hybrid") -> dict:
        self.calls.append(
            {
                "query": query,
                "tenant_slug": tenant_slug,
                "principal_id": principal_id,
            }
        )
        return {"ok": True, "matches": [], "text": ""}


def test_knowledge_tool_uses_context_tenant_slug_only():
    adapter = RecordingAdapter()
    tool = GetKnowledgeTool(adapter)
    ctx_a = TenantContext(tenant_id=uuid.uuid4(), tenant_slug="tenant-a", role="tenant_owner")
    ctx_b = TenantContext(tenant_id=uuid.uuid4(), tenant_slug="tenant-b", role="tenant_owner")

    tool.run(MagicMock(), ctx_a, query="pricing")
    tool.run(MagicMock(), ctx_b, query="pricing")

    assert adapter.calls[0]["tenant_slug"] == "tenant-a"
    assert adapter.calls[1]["tenant_slug"] == "tenant-b"
    assert "tenant_id" not in adapter.calls[0]


def test_operator_owner_vs_guest_principal():
    owner_ctx = TenantContext(tenant_id=uuid.uuid4(), tenant_slug="demo", role="tenant_owner")
    guest_ctx = TenantContext(tenant_id=uuid.uuid4(), tenant_slug="demo", role="viewer")

    adapter = RecordingAdapter()
    tool = GetKnowledgeTool(adapter)
    tool.run(MagicMock(), owner_ctx, query="policy")
    tool.run(MagicMock(), guest_ctx, query="policy")

    assert adapter.calls[0]["principal_id"] == PRINCIPAL_TEXT_OWNER
    assert adapter.calls[1]["principal_id"] == PRINCIPAL_TEXT_GUEST


def test_widget_guest_maps_to_brain_text_guest_legacy():
    widget = principal_for_public_channel("widget")
    assert widget == PRINCIPAL_WIDGET_GUEST
    assert brain_principal_id(widget, use_legacy=True) == "service:text-guest"


def test_knowledge_adapter_rejects_cross_tenant_via_headers(monkeypatch):
    captured: list[dict] = []

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"ok": True, "text": "", "matches": []}

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, json=None, headers=None):
            captured.append({"url": url, "json": json, "headers": headers})
            return FakeResponse()

    monkeypatch.setattr("app.adapters.knowledge.httpx.Client", lambda **kwargs: FakeClient())
    monkeypatch.setattr(
        "app.adapters.knowledge.get_settings",
        lambda: MagicMock(
            knowledge_base_url="http://knowledge:8021",
            knowledge_use_legacy_principals=True,
        ),
    )

    adapter = KnowledgeAdapter()
    adapter.search("secret", tenant_slug="tenant-a", principal_id=PRINCIPAL_TEXT_OWNER)
    adapter.search("secret", tenant_slug="tenant-b", principal_id=PRINCIPAL_TEXT_OWNER)

    assert captured[0]["headers"]["X-Tenant-Id"] == "tenant-a"
    assert captured[1]["headers"]["X-Tenant-Id"] == "tenant-b"
    assert captured[0]["headers"]["X-Tenant-Id"] != captured[1]["headers"]["X-Tenant-Id"]
    assert "tenant_id" not in (captured[0]["json"] or {})


def test_default_operator_role_is_owner_context_not_guest():
    ctx = TenantContext(tenant_id=uuid.uuid4(), tenant_slug="demo", role=None)
    adapter = RecordingAdapter()
    GetKnowledgeTool(adapter).run(MagicMock(), ctx, query="status")
    assert adapter.calls[0]["principal_id"] == PRINCIPAL_TEXT_OWNER
