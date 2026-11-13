"""Sticky Hermes runtime slot assignment."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.core.tenant import TenantContext
from app.models.tenant import Tenant
from app.services.hermes_nous.runtime_pool import assign_isolated_runtime, list_runtime_slots


def test_list_runtime_slots_default_two():
    slots = list_runtime_slots()
    assert len(slots) >= 2
    assert slots[0]["id"] == "tenant-a"
    assert slots[1]["id"] == "tenant-b"


def test_assign_isolated_runtime_sticky(monkeypatch):
    tenant_id = uuid.uuid4()
    ctx = TenantContext(tenant_id=tenant_id, tenant_slug="fresh-co", role="tenant_owner")
    tenant = Tenant(slug="fresh-co", name="Fresh", settings={})
    tenant.id = tenant_id
    db = MagicMock()
    db.query.return_value.filter.return_value.one.return_value = tenant
    db.query.return_value.all.return_value = [tenant]

    with (
        patch(
            "app.services.hermes_nous.runtime_pool.ensure_mcp_api_key",
            return_value="dmcp_test",
        ),
        patch(
            "app.services.hermes_nous.runtime_pool.ensure_tenant_hermes_home",
            return_value={
                "runtime_base_url": "http://delno-hermes-tenant-a:8642",
                "api_server_key_env": "HERMES_API_SERVER_KEY",
            },
        ),
    ):
        first = assign_isolated_runtime(db, ctx)
        assert first["slot_id"] == "tenant-a"
        # Simulate persisted settings after first assign
        tenant.settings = {
            "mcp_api_key": "dmcp_test",
            "hermes_nous": {"runtime": dict(first)},
        }
        second = assign_isolated_runtime(db, ctx)
        assert second["slot_id"] == "tenant-a"
