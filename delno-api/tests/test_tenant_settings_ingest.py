"""E1.8 — tenant settings → brain sync."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.models.tenant import Tenant
from app.services.tenant_settings_ingest import sync_tenant_settings_to_brain


def test_sync_tenant_settings_skipped_when_knowledge_disabled():
    db = MagicMock()
    tenant = Tenant(slug="delno-demo", name="DELNO Demo", settings={"locale": "ru"})
    tenant.id = uuid.uuid4()

    with patch("app.services.tenant_settings_ingest.get_settings") as mock_settings:
        mock_settings.return_value.knowledge_base_url = ""
        result = sync_tenant_settings_to_brain(db, tenant)

    assert result["skipped"] is True


def test_sync_tenant_settings_posts_to_brain():
    db = MagicMock()
    tenant = Tenant(
        slug="delno-demo",
        name="DELNO Demo",
        settings={"legal": {"inn": "471405233378", "name": "ИП Рябов"}, "locale": "ru"},
    )
    tenant.id = uuid.uuid4()

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"ok": True, "document_id": "doc-delno-demo-tenant-settings"}

    with patch("app.services.tenant_settings_ingest.get_settings") as mock_settings:
        mock_settings.return_value.knowledge_base_url = "http://knowledge:8021"
        with patch("app.services.tenant_settings_ingest.emit_event"):
            with patch("httpx.Client") as mock_client:
                mock_client.return_value.__enter__.return_value.post.return_value = mock_response
                result = sync_tenant_settings_to_brain(db, tenant)

    assert result["ok"] is True
    assert result["document_id"] == "doc-delno-demo-tenant-settings"
