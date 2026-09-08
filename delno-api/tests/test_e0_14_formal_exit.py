"""E0.14 formal exit — admin creates tenant, default flags, events, audit."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.api.v1.admin import DEFAULT_FLAGS, create_tenant
from app.api.v1.tenant import FeatureFlagUpdate, list_feature_flags, update_feature_flag
from app.core.tenant import TenantContext
from app.models.feature_flag import FeatureFlag
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.admin import TenantCreateRequest


def test_e0_14_create_tenant_seeds_flags_emits_event_and_audit():
    admin_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    admin = MagicMock(spec=User)
    admin.id = admin_id
    admin.role = "platform_admin"

    db = MagicMock()
    db.query.return_value.filter.return_value.one_or_none.return_value = None

    added: list[object] = []

    def capture_add(obj: object) -> None:
        added.append(obj)
        if isinstance(obj, Tenant):
            obj.id = tenant_id
            obj.is_active = True

    db.add.side_effect = capture_add
    db.flush = MagicMock()
    db.commit = MagicMock()
    db.refresh = MagicMock()

    body = TenantCreateRequest(slug="exit-test-co", name="Exit Test Co")

    with patch("app.api.v1.admin.emit_event") as mock_emit:
        with patch("app.api.v1.admin.write_audit") as mock_audit:
            with patch("app.api.v1.admin.hash_password", return_value="hashed"):
                result = create_tenant(body, db=db, admin=admin)

    assert result.slug == "exit-test-co"
    flag_rows = [obj for obj in added if isinstance(obj, FeatureFlag)]
    assert len(flag_rows) == len(DEFAULT_FLAGS)
    assert {f.flag_key for f in flag_rows} == set(DEFAULT_FLAGS)
    assert all(f.tenant_id == tenant_id and f.enabled is False for f in flag_rows)

    mock_emit.assert_called_once()
    emit_kwargs = mock_emit.call_args.kwargs
    assert emit_kwargs["event_type"] == "tenant.created"
    assert emit_kwargs["tenant_id"] == tenant_id
    assert emit_kwargs["source"] == "admin.tenants"

    mock_audit.assert_called_once()
    assert mock_audit.call_args.kwargs["action"] == "admin.create_tenant"
    db.commit.assert_called_once()


def test_e0_14_feature_flags_list_and_update():
    tenant_id = uuid.uuid4()
    ctx = TenantContext(tenant_id=tenant_id, tenant_slug="exit-test-co", role="tenant_owner")

    flag_web = FeatureFlag(tenant_id=tenant_id, flag_key="web_voice", enabled=False)
    flag_tg = FeatureFlag(tenant_id=tenant_id, flag_key="telegram", enabled=False)

    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [flag_tg, flag_web]
    listed = list_feature_flags(db=db, ctx=ctx)
    assert len(listed) == 2
    assert listed[0].flag_key == "telegram"

    flag_web.enabled = False
    db.query.return_value.filter.return_value.one_or_none.return_value = flag_web

    with patch("app.api.v1.tenant.emit_event") as mock_emit:
        updated = update_feature_flag("web_voice", FeatureFlagUpdate(enabled=True), db=db, ctx=ctx)

    assert updated.enabled is True
    assert flag_web.enabled is True
    mock_emit.assert_called_once()
    kwargs = mock_emit.call_args.kwargs
    assert kwargs["event_type"] == "feature.flag.updated"
    assert kwargs["tenant_id"] == tenant_id
    assert kwargs["payload"]["flag_key"] == "web_voice"
    assert kwargs["payload"]["enabled"] is True
    db.commit.assert_called_once()
