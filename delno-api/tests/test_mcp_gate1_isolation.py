"""HTTP-level isolation checks for two companies sharing one MCP gateway."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.v1.mcp import router as mcp_router, hermes_router
from app.core.db import Base, get_db
from app.core.tenant import TenantContext
from app.models.tenant import Tenant
from app.models.user import User
from app.models.platform_event import PlatformEvent
from app.operator.tools import register_builtin_tools
from app.services.hermes_nous.run_bindings import bind_run_token, revoke_binding
from app.models.hermes_runtime import HermesRunBinding
from app.services.hermes_nous.run_tokens import issue_run_token
from app.services.mcp_gateway import ensure_mcp_api_key


@pytest.fixture()
def gateway(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'mcp-gate1.sqlite'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    app = FastAPI()
    app.include_router(mcp_router, prefix="/v1")
    app.include_router(hermes_router, prefix="/v1")
    register_builtin_tools()

    def _db():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = _db
    with sessions() as db:
        tenants = []
        for slug in ("gate-a", "gate-b"):
            tenant = Tenant(slug=slug, name=f"Secret {slug}", settings={}, is_active=True)
            db.add(tenant)
            db.flush()
            user = User(tenant_id=tenant.id, email=f"{slug}@example.test", role="tenant_owner")
            db.add(user)
            db.commit()
            db.refresh(tenant)
            db.refresh(user)
            key = ensure_mcp_api_key(db, tenant)
            ctx = TenantContext(tenant_id=tenant.id, tenant_slug=slug, user_id=user.id, role=user.role)
            run_id = f"gate_{slug}_{uuid4().hex[:8]}"
            token = issue_run_token(db, ctx, run_id=run_id, tool_ids=["get_tenant_summary"])
            profile_id = f"tenant_{slug}__company_main"
            bind_run_token(
                db, tenant_id=tenant.id, profile_id=profile_id, worker_id="pool",
                run_id=run_id, session_id=f"{slug}:conversation", actor_user_id=user.id,
                agent_id="company_main", raw_token=token.token,
                tool_ids=token.tool_ids,
                expires_at_unix=int((datetime.now(timezone.utc) + timedelta(minutes=30)).timestamp()),
            )
            tenants.append({"id": tenant.id, "user_id": user.id, "slug": slug, "key": key,
                            "token": token.token, "run_id": run_id, "profile": profile_id})
    yield TestClient(app), sessions, tenants
    engine.dispose()


def _headers(company):
    return {"Authorization": f"Bearer {company['token']}",
            "X-Delno-Run-Id": company["run_id"],
            "X-Delno-Profile-Id": company["profile"]}


def test_parallel_calls_keep_company_data_and_grants_separate(gateway, monkeypatch):
    client, _, (a, b) = gateway
    monkeypatch.setenv("DELNO_MCP_REQUIRE_RUN_BINDING", "1")

    def call(company):
        profile = client.post("/v1/mcp/tools/call", headers=_headers(company),
                              json={"name": "hermes.profile", "arguments": {}})
        denied = client.post("/v1/mcp/tools/call", headers=_headers(company),
                             json={"name": "send_mail_draft", "arguments": {}})
        return company, profile, denied

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(call, [a, b] * 12))
    for company, profile, denied in results:
        assert profile.status_code == 200
        result = profile.json()["result"]
        assert result["tenant_id"] == str(company["id"])
        assert result["tenant_name"] == f"Secret {company['slug']}"
        assert "mcp_api_key" not in result
        assert denied.status_code == 403
        assert denied.json()["detail"]["error"] == "tool_not_granted"


def test_token_run_profile_swap_and_revocation_are_denied(gateway, monkeypatch):
    client, sessions, (a, b) = gateway
    monkeypatch.setenv("DELNO_MCP_REQUIRE_RUN_BINDING", "1")
    missing_headers = client.get("/v1/mcp/tools", headers={
        "Authorization": f"Bearer {a['token']}",
    })
    assert missing_headers.status_code == 401
    assert missing_headers.json()["detail"] == "run_identity_headers_required"
    for override in ({"X-Delno-Run-Id": b["run_id"]},
                     {"X-Delno-Profile-Id": b["profile"]}):
        headers = {**_headers(a), **override}
        assert client.get("/v1/mcp/tools", headers=headers).status_code == 403
    # A company's legacy key cannot claim B's bound run.
    assert client.get("/v1/mcp/tools", headers={
        "Authorization": f"Bearer {a['key']}",
        "X-Delno-Run-Id": b["run_id"],
    }).status_code == 403
    # During migration, a scoped A token cannot override B's profile key.
    assert client.get("/v1/mcp/tools", headers={
        "Authorization": f"Bearer {b['key']}",
        "X-Delno-Run-Token": a["token"],
        "X-Delno-Run-Id": a["run_id"],
    }).status_code == 403
    with sessions() as db:
        assert revoke_binding(db, run_id=a["run_id"])
    assert client.get("/v1/mcp/tools", headers=_headers(a)).status_code == 401


def test_removed_actor_and_strict_legacy_precedence(gateway, monkeypatch):
    client, sessions, (a, b) = gateway
    monkeypatch.setenv("DELNO_MCP_REQUIRE_RUN_BINDING", "1")
    with sessions() as db:
        user = db.query(User).filter(User.id == b["user_id"]).one()
        user.tenant_id = a["id"]
        db.commit()
    assert client.get("/v1/mcp/tools", headers=_headers(b)).status_code == 403
    monkeypatch.setenv("DELNO_MCP_STRICT", "1")
    monkeypatch.setenv("DELNO_MCP_LEGACY_KEY_META_ONLY", "0")
    catalog = client.get("/v1/mcp/tools", headers={"Authorization": f"Bearer {a['key']}"})
    assert catalog.status_code == 200
    assert {item["name"] for item in catalog.json()["tools"]} <= {
        "office.health", "office.connectors", "hermes.profile",
    }


def test_binding_grants_and_actor_role_cannot_be_changed_under_token(gateway, monkeypatch):
    client, sessions, (a, _) = gateway
    monkeypatch.setenv("DELNO_MCP_REQUIRE_RUN_BINDING", "1")
    with sessions() as db:
        binding = db.query(HermesRunBinding).filter(HermesRunBinding.run_id == a["run_id"]).one()
        binding.tool_ids = ["send_mail_draft"]
        db.commit()
    assert client.get("/v1/mcp/tools", headers=_headers(a)).status_code == 403
    with sessions() as db:
        binding = db.query(HermesRunBinding).filter(HermesRunBinding.run_id == a["run_id"]).one()
        binding.tool_ids = ["get_tenant_summary"]
        user = db.query(User).filter(User.id == a["user_id"]).one()
        user.role = "tenant_admin"
        db.commit()
    response = client.get("/v1/mcp/tools", headers=_headers(a))
    assert response.status_code == 403
    assert response.json()["detail"] == "run_actor_role_changed"


def test_unbound_capability_is_rejected_when_strict_binding_enabled(gateway, monkeypatch):
    client, sessions, (a, _) = gateway
    monkeypatch.setenv("DELNO_MCP_REQUIRE_RUN_BINDING", "1")
    with sessions() as db:
        ctx = TenantContext(tenant_id=a["id"], tenant_slug=a["slug"],
                            user_id=a["user_id"], role="tenant_owner")
        unbound = issue_run_token(db, ctx, tool_ids=["get_tenant_summary"])
    assert client.get("/v1/mcp/tools", headers={
        "Authorization": f"Bearer {unbound.token}",
    }).status_code == 401


def test_hermes_run_scope_to_gateway_concurrent(gateway, monkeypatch):
    """Exercise the runtime adapter and HTTP gateway together, with no shared token state."""
    client, _, (a, b) = gateway
    monkeypatch.setenv("DELNO_MCP_REQUIRE_RUN_BINDING", "1")
    module_path = Path(__file__).parents[1] / "hermes_runtime/patches/delno_run_scope.py"
    spec = importlib.util.spec_from_file_location("gate1_runtime_scope", module_path)
    assert spec and spec.loader
    runtime = importlib.util.module_from_spec(spec)
    import sys

    sys.modules[spec.name] = runtime
    spec.loader.exec_module(runtime)

    class LocalClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def post(self, url, *, headers, json):
            assert url == "http://delno-api:8020/v1/mcp/tools/call"
            return client.post("/v1/mcp/tools/call", headers=headers, json=json)

    monkeypatch.setattr(runtime.httpx, "Client", LocalClient)
    assert "delno_run_scope_missing" in runtime.call_tool("hermes.profile", {}, timeout=5)

    def call(company):
        scope = runtime.bind_run_scope(token=company["token"], run_id=company["run_id"],
                                       profile_id=company["profile"])
        try:
            import json

            own = json.loads(runtime.call_tool("hermes.profile", {}, timeout=5))
            denied = json.loads(runtime.call_tool("send_mail_draft", {}, timeout=5))
            return own["tenant_id"], denied["error"]
        finally:
            runtime.reset_run_scope(scope)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(call, [a, b] * 12))
    assert [tenant_id for tenant_id, _ in results] == [str(c["id"]) for c in [a, b] * 12]
    assert all(error == "delno_mcp_rejected" for _, error in results)


def test_legacy_catalog_can_discover_but_cannot_execute_business_tools(gateway, monkeypatch):
    client, _, (a, _) = gateway
    monkeypatch.setenv("DELNO_MCP_DENY_LEGACY_KEY", "1")
    monkeypatch.setenv("DELNO_MCP_LEGACY_CATALOG_ONLY", "1")
    headers = {"Authorization": f"Bearer {a['key']}"}
    catalog = client.get("/v1/mcp/tools", headers=headers)
    assert catalog.status_code == 200
    assert catalog.json()["auth_via"] == "legacy_catalog"
    assert any(t["name"] == "hermes.profile" for t in catalog.json()["tools"])
    assert any(t["name"] == "get_tenant_summary" for t in catalog.json()["tools"])
    assert client.post("/v1/mcp/tools/call", headers=headers,
                       json={"name": "get_tenant_summary", "arguments": {}}).status_code == 403
    assert client.get("/v1/mcp/tools", headers={
        **headers, "X-Delno-Run-Id": a["run_id"],
    }).status_code == 401
    rpc = client.post("/v1/mcp", headers=headers, json={
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "get_tenant_summary", "arguments": {}},
    })
    assert rpc.status_code == 200
    assert rpc.json()["error"]["code"] == -32003
    profile = client.get("/v1/hermes/profile", headers=headers)
    assert profile.status_code == 200
    assert "mcp_api_key" not in profile.json()


def test_flag_rollback_restores_legacy_call_without_restarting_database(gateway, monkeypatch):
    client, sessions, (a, _) = gateway
    headers = {"Authorization": f"Bearer {a['key']}"}
    body = {"name": "get_tenant_summary", "arguments": {}}
    assert client.post("/v1/mcp/tools/call", headers=headers, json=body).status_code == 200
    monkeypatch.setenv("DELNO_MCP_LEGACY_CATALOG_ONLY", "1")
    monkeypatch.setenv("DELNO_MCP_DENY_LEGACY_KEY", "1")
    assert client.post("/v1/mcp/tools/call", headers=headers, json=body).status_code == 403
    monkeypatch.delenv("DELNO_MCP_LEGACY_CATALOG_ONLY")
    monkeypatch.delenv("DELNO_MCP_DENY_LEGACY_KEY")
    assert client.post("/v1/mcp/tools/call", headers=headers, json=body).status_code == 200
    with sessions() as db:
        events = db.query(PlatformEvent).filter(PlatformEvent.tenant_id == a["id"],
                                                PlatformEvent.event_type == "mcp.tool_called").all()
        assert events
        assert all(e.payload["auth_via"] == "mcp_api_key" for e in events)
        assert all("token" not in e.payload for e in events)
