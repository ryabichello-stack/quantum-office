import uuid
from unittest.mock import MagicMock

from app.services.channel_router import ChannelContext, resolve_public_lead, resolve_widget


def test_resolve_widget_returns_guest_principal():
    tenant_id = uuid.uuid4()
    tenant = MagicMock()
    tenant.id = tenant_id
    tenant.slug = "acme"
    tenant.is_active = True

    db = MagicMock()
    db.query.return_value.filter.return_value.one_or_none.return_value = tenant

    ctx = resolve_widget(db, "pk_test")
    assert ctx is not None
    assert ctx.tenant_slug == "acme"
    assert "widget-guest" in ctx.principal_id


def test_resolve_public_lead():
    tenant_id = uuid.uuid4()
    tenant = MagicMock()
    tenant.id = tenant_id
    tenant.slug = "delno-demo"
    tenant.is_active = True

    db = MagicMock()
    db.query.return_value.filter.return_value.one_or_none.return_value = tenant

    ctx = resolve_public_lead(db, "delno-demo")
    assert isinstance(ctx, ChannelContext)
    assert ctx.channel_type == "website"
