"""Stage 0: scoped run tokens + MCP filter isolation (no live Hermes required)."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from app.core.tenant import TenantContext
from app.models.tenant import Tenant
from app.services.hermes_nous.mcp_scope import filter_tools_catalog, tool_allowed
from app.services.hermes_nous.run_tokens import issue_run_token, revoke_run_token, verify_run_token


def _tenant(slug: str) -> Tenant:
    t = Tenant(slug=slug, name=slug.title(), settings={})
    t.id = uuid.uuid4()
    return t


def test_filter_tools_fail_closed_empty_grants():
    catalog = [
        {"name": "get_knowledge"},
        {"name": "send_mail_draft"},
        {"name": "office.health"},
    ]
    filtered = filter_tools_catalog(catalog, [])
    names = {t["name"] for t in filtered}
    assert names == {"office.health"}  # meta only (+ connectors/profile if present)
    assert not tool_allowed("send_mail_draft", [])
    assert tool_allowed("office.health", [])


def test_filter_tools_respects_grants():
    catalog = [
        {"name": "get_knowledge"},
        {"name": "send_mail_draft"},
        {"name": "office.health"},
        {"name": "hermes.profile"},
    ]
    filtered = filter_tools_catalog(catalog, ["get_knowledge"])
    names = {t["name"] for t in filtered}
    assert "get_knowledge" in names
    assert "office.health" in names
    assert "hermes.profile" in names
    assert "send_mail_draft" not in names


def test_run_token_isolation_between_tenants():
    a = _tenant("tenant-a")
    b = _tenant("tenant-b")
    db = MagicMock()

    def query_side(model):
        q = MagicMock()
        if model is Tenant:

            def filter(*_a, **_k):
                # issue_run_token: .filter(Tenant.id == ...).one()
                # verify: .filter(is_active).all()
                fq = MagicMock()
                fq.one.return_value = a
                fq.one_or_none.return_value = a
                fq.all.return_value = [a, b]
                return fq

            q.filter.side_effect = filter
        return q

    db.query.side_effect = query_side

    ctx_a = TenantContext(tenant_id=a.id, tenant_slug="tenant-a", role="tenant_owner")
    issued = issue_run_token(db, ctx_a, tool_ids=["get_knowledge"])
    assert issued.token.startswith("dnrt_")

    # verify sees both tenants; only A's hash matches
    found = verify_run_token(db, issued.token)
    assert found is not None
    assert found["tenant_id"] == str(a.id)
    assert "get_knowledge" in found["tool_ids"]

    # B must not verify with garbage
    assert verify_run_token(db, "dnrt_not_a_real_token_value_xxxxxx") is None

    revoke_run_token(db, ctx_a, run_id=issued.run_id)
    # after revoke, settings marked — re-verify uses updated settings on tenant a
    # (MagicMock keeps same object)
    a_settings = a.settings.get("hermes_nous", {}).get("run_tokens", {})
    assert any(v.get("revoked") for v in a_settings.values() if isinstance(v, dict))
