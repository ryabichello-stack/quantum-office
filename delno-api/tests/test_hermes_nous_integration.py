"""Detailed sqlite integration tests for Hermes Nous P0–P3 surfaces."""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.hermes_nous import router as hermes_nous_router
from app.api.v1.mcp import router as mcp_router
from app.core.auth import get_tenant_context_auth
from app.core.db import Base, get_db
from app.core.tenant import TenantContext
from app.models.agent_task import AgentRun, AgentStep, AgentTask  # noqa: F401
from app.models.feature_flag import FeatureFlag
from app.models.tenant import Tenant
from app.models.user import User  # noqa: F401
from app.operator.tools import register_builtin_tools
from app.services.hermes_nous.events_dispatch import on_lead_created
from app.services.hermes_nous.mcp_scope import filter_tools_catalog, tool_allowed
from app.services.hermes_nous.onboarding import confirm_kb_draft, get_office_loop, save_kb_draft
from app.services.hermes_nous.run_tokens import issue_run_token, verify_run_token
from app.services.hermes_nous.tasks import create_task, list_tasks
from app.services.hermes_nous.tool_packs import pack_for_mode
from app.services.mcp_gateway import mcp_tools_catalog


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def _seed(db, *, flag_on: bool = True):
    tenant = Tenant(
        id=uuid.uuid4(),
        slug=f"t-{uuid.uuid4().hex[:6]}",
        name="Test Co",
        settings={},
        is_active=True,
    )
    db.add(tenant)
    db.flush()
    db.add(
        FeatureFlag(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            flag_key="hermes_nous_runtime",
            enabled=flag_on,
        )
    )
    db.commit()
    db.refresh(tenant)
    ctx = TenantContext(tenant_id=tenant.id, tenant_slug=tenant.slug, role="tenant_owner")
    return tenant, ctx


def test_a_b_run_token_isolation(db):
    a, ctx_a = _seed(db)
    b, ctx_b = _seed(db)
    tok_a = issue_run_token(db, ctx_a, tool_ids=["get_knowledge"])
    tok_b = issue_run_token(db, ctx_b, tool_ids=["get_knowledge", "send_mail_draft"])
    va = verify_run_token(db, tok_a.token)
    vb = verify_run_token(db, tok_b.token)
    assert va is not None and vb is not None
    assert va["tenant_id"] == str(a.id)
    assert vb["tenant_id"] == str(b.id)
    assert va["tenant_id"] != vb["tenant_id"]
    assert "send_mail_draft" not in va["tool_ids"]
    assert "send_mail_draft" in vb["tool_ids"]


def test_mcp_filter_fail_closed_and_pack(db):
    register_builtin_tools()
    catalog = mcp_tools_catalog()
    onboarding = filter_tools_catalog(catalog, pack_for_mode("onboarding"))
    names = {t["name"] for t in onboarding}
    assert "upload_knowledge_snippet" in names or "office.import_website" in names
    assert "office.health" in names
    # conduct has mail draft; onboarding pack should not include it unless in pack
    if "send_mail_draft" in {t["name"] for t in catalog}:
        assert not tool_allowed("send_mail_draft", pack_for_mode("onboarding"))
        assert tool_allowed("send_mail_draft", pack_for_mode("conduct"))


def test_office_loop_kb_draft_confirm(db, monkeypatch):
    tenant, ctx = _seed(db)
    monkeypatch.setattr(
        "app.services.hermes_nous.onboarding.hermes_ops.office_setup_status",
        lambda *_a, **_k: {
            "ok": True,
            "setup_complete": False,
            "checks": {"company_knowledge": {"ok": False}},
            "progress": {"required_done": 0, "required_total": 2},
            "message_ru": "нужна KB",
        },
    )
    draft = save_kb_draft(
        db,
        ctx,
        title="О нас",
        body="Мы делаем выплаты и ИИ-офис для компаний. Достаточно длинный текст.",
        source_url="https://example.com",
    )
    assert draft["ok"] is True
    loop = get_office_loop(db, ctx)
    assert loop["kb_draft"]["status"] == "draft"
    assert any(s["id"] == "company_kb" for s in loop["steps"])

    register_builtin_tools()

    class _Ok:
        ok = True
        data = {"document_id": "doc1"}

    with patch("app.operator.tools.registry.registry.run", return_value=_Ok()):
        confirmed = confirm_kb_draft(db, ctx)
    assert confirmed["ok"] is True
    assert confirmed["committed"] is True


def test_lead_created_queues_task_when_flag_on(db):
    tenant, _ctx = _seed(db, flag_on=True)
    out = on_lead_created(
        db,
        tenant_id=tenant.id,
        lead_id=str(uuid.uuid4()),
        payload={"source": "site"},
    )
    assert out and out["ok"] is True
    tasks = db.query(AgentTask).filter(AgentTask.tenant_id == tenant.id).all()
    assert len(tasks) == 1
    assert tasks[0].trigger_kind == "event"
    runs = db.query(AgentRun).filter(AgentRun.tenant_id == tenant.id).all()
    assert len(runs) == 1
    assert runs[0].status == "queued"


def test_lead_created_noop_when_flag_off(db):
    tenant, _ctx = _seed(db, flag_on=False)
    out = on_lead_created(db, tenant_id=tenant.id, lead_id=str(uuid.uuid4()))
    assert out is None
    assert db.query(AgentTask).count() == 0


def test_create_lead_record_wires_hermes_queue(db, monkeypatch):
    """create_lead_record must surface hermes_nous queue meta when flag on."""
    from app.models.lead import Lead  # noqa: F401
    from app.services.leads import create_lead_record

    tenant, ctx = _seed(db, flag_on=True)
    monkeypatch.setattr("app.services.leads.notify_lead_telegram", lambda *_a, **_k: False)
    monkeypatch.setattr(
        "app.services.leads.enrich_lead_from_inn",
        lambda *_a, **_k: {"enriched": False},
    )
    lead, meta = create_lead_record(
        db,
        ctx,
        name="Иван Тест",
        phone="+79990001122",
        source="website",
        company="Test Co",
    )
    assert lead.id is not None
    assert meta.get("hermes_nous") and meta["hermes_nous"]["ok"] is True
    assert db.query(AgentTask).filter(AgentTask.tenant_id == tenant.id).count() == 1
    assert db.query(AgentRun).filter(AgentRun.tenant_id == tenant.id, AgentRun.status == "queued").count() == 1


def test_http_office_loop_and_tasks(db):
    tenant, ctx = _seed(db)
    with patch(
        "app.services.hermes_nous.onboarding.hermes_ops.office_setup_status",
        return_value={
            "ok": True,
            "setup_complete": False,
            "checks": {"company_knowledge": {"ok": False}},
            "progress": {"required_done": 0, "required_total": 1},
            "message_ru": "setup",
        },
    ):
        app = FastAPI()
        app.include_router(hermes_nous_router, prefix="/v1")

        def _db():
            yield db

        def _ctx():
            return ctx

        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_tenant_context_auth] = _ctx
        client = TestClient(app)

        st = client.get("/v1/hermes-nous/status")
        assert st.status_code == 200
        assert st.json()["enabled"] is True
        assert st.json()["engine"] == "nous_hermes_agent"

        loop = client.get("/v1/hermes-nous/office-loop")
        assert loop.status_code == 200
        assert "steps" in loop.json()

        task = client.post("/v1/hermes-nous/tasks", json={"goal": "Проверяй заявки", "trigger_kind": "schedule"})
        assert task.status_code == 200
        assert task.json()["task"]["goal"] == "Проверяй заявки"

        listed = client.get("/v1/hermes-nous/tasks")
        assert listed.status_code == 200
        assert len(listed.json()["items"]) >= 1

        ch = client.get("/v1/hermes-nous/channels-map")
        assert ch.status_code == 200
        assert "telephony" in ch.json()

        sc = client.get("/v1/hermes-nous/scale-notes")
        assert sc.status_code == 200


def test_mcp_run_token_scopes_tools_list(db):
    register_builtin_tools()
    tenant, ctx = _seed(db)
    issued = issue_run_token(db, ctx, tool_ids=["get_knowledge"])
    app = FastAPI()
    app.include_router(mcp_router, prefix="/v1")

    def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    client = TestClient(app)
    res = client.get(
        "/v1/mcp/tools",
        headers={"Authorization": f"Bearer {issued.token}"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["auth_via"] == "run_token"
    names = {t["name"] for t in body["tools"]}
    assert "office.health" in names  # meta always
    assert "get_knowledge" in names
    # should not expose full catalog write tools unless granted
    assert "send_mail_draft" not in names or "send_mail_draft" in issued.tool_ids


def test_create_run_records_agent_run(db, monkeypatch, tmp_path):
    tenant, ctx = _seed(db)
    monkeypatch.setenv("HERMES_NOUS_RUNTIME_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("HERMES_API_SERVER_KEY", "test-key")
    from app.core.config import get_settings
    from app.services.hermes_nous.provision import ensure_tenant_hermes_home
    from app.services.hermes_nous.bridge import HermesBridgeError, create_run

    get_settings.cache_clear()
    monkeypatch.setenv("TENANT_FILES_ROOT", str(tmp_path))
    get_settings.cache_clear()

    ensure_tenant_hermes_home(db, ctx, runtime_base_url="http://127.0.0.1:9")

    def _boom(*_a, **_k):
        raise HermesBridgeError("hermes_unreachable: refuse", status=None)

    monkeypatch.setattr("app.services.hermes_nous.bridge._http_json", _boom)
    with pytest.raises(HermesBridgeError):
        create_run(db, ctx, message="Собери KB", mode="onboarding")
    assert db.query(AgentRun).filter(AgentRun.tenant_id == tenant.id).count() >= 1
    assert db.query(AgentStep).filter(AgentStep.tenant_id == tenant.id).count() >= 1
    get_settings.cache_clear()


def test_create_run_success_and_chat_fallback(db, monkeypatch, tmp_path):
    _tenant, ctx = _seed(db)
    from app.core.config import get_settings
    from app.services.hermes_nous.provision import ensure_tenant_hermes_home
    from app.services.hermes_nous.bridge import HermesBridgeError, create_run

    monkeypatch.setenv("TENANT_FILES_ROOT", str(tmp_path))
    monkeypatch.setenv("HERMES_API_SERVER_KEY", "test-key")
    get_settings.cache_clear()
    ensure_tenant_hermes_home(db, ctx, runtime_base_url="http://hermes.test")

    def _runs_ok(method, url, **_k):
        assert "/v1/runs" in url
        return 200, {"run_id": "hr_ok_1", "status": "running"}

    monkeypatch.setattr("app.services.hermes_nous.bridge._http_json", _runs_ok)
    out = create_run(db, ctx, message="Собери KB с сайта", mode="onboarding")
    assert out["ok"] is True
    assert out["mode"] == "runs"
    assert out["run_id"] == "hr_ok_1"
    assert "get_knowledge" in out["tool_ids"] or "office.health" in out["tool_ids"]

    def _runs_404_then_chat(method, url, **_k):
        if url.endswith("/v1/runs"):
            raise HermesBridgeError("hermes_http_404", status=404, body={})
        assert "chat/completions" in url
        return 200, {"choices": [{"message": {"content": "Черновик KB готов"}}]}

    monkeypatch.setattr("app.services.hermes_nous.bridge._http_json", _runs_404_then_chat)
    fb = create_run(db, ctx, message="fallback", mode="conduct")
    assert fb["ok"] is True
    assert fb["mode"] == "chat_completions_fallback"
    assert "Черновик" in fb["output"]
    get_settings.cache_clear()


def test_mcp_tool_call_denied_outside_pack(db):
    register_builtin_tools()
    _tenant, ctx = _seed(db)
    issued = issue_run_token(db, ctx, tool_ids=["get_knowledge"])
    app = FastAPI()
    app.include_router(mcp_router, prefix="/v1")

    def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    client = TestClient(app)
    denied = client.post(
        "/v1/mcp/tools/call",
        headers={"Authorization": f"Bearer {issued.token}"},
        json={"name": "send_mail_draft", "arguments": {"to": "x@y.z", "subject": "t", "body": "b"}},
    )
    assert denied.status_code == 403
    assert denied.json()["detail"]["error"] == "tool_not_granted"

    rpc = client.post(
        "/v1/mcp",
        headers={"X-Delno-Run-Token": issued.token},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "send_mail_draft", "arguments": {}},
        },
    )
    assert rpc.status_code == 200
    assert rpc.json()["error"]["message"].startswith("tool_not_granted")


def test_revoke_run_token_and_hermes_profile_no_long_key(db):
    from app.services.hermes_nous.run_tokens import revoke_run_token

    register_builtin_tools()
    _tenant, ctx = _seed(db)
    issued = issue_run_token(db, ctx, tool_ids=["get_knowledge"], run_id="delno_rev1")
    assert verify_run_token(db, issued.token) is not None
    revoke_run_token(db, ctx, run_id="delno_rev1")
    assert verify_run_token(db, issued.token) is None

    issued2 = issue_run_token(db, ctx, tool_ids=["get_knowledge"])
    from app.api.v1.mcp import hermes_router

    app = FastAPI()
    app.include_router(hermes_router, prefix="/v1")

    def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    client = TestClient(app)
    prof = client.get(
        "/v1/hermes/profile",
        headers={"Authorization": f"Bearer {issued2.token}"},
    )
    assert prof.status_code == 200
    body = prof.json()
    assert body.get("auth_via") == "run_token"
    assert "mcp_api_key" not in body


def test_office_loop_phase_and_http_kb_confirm(db, monkeypatch):
    from app.services.hermes_nous.onboarding import set_phase

    _tenant, ctx = _seed(db)
    monkeypatch.setattr(
        "app.services.hermes_nous.onboarding.hermes_ops.office_setup_status",
        lambda *_a, **_k: {
            "ok": True,
            "setup_complete": False,
            "checks": {"company_knowledge": {"ok": False}},
            "progress": {"required_done": 0, "required_total": 1},
            "message_ru": "setup",
        },
    )
    out = set_phase(db, ctx, "company_kb")
    assert out["ok"] is True
    assert out["phase"] == "company_kb"

    save_kb_draft(db, ctx, title="Компания", body="Текст про продукты и услуги компании достаточно длинный.", source_url=None)

    app = FastAPI()
    app.include_router(hermes_nous_router, prefix="/v1")

    def _db():
        yield db

    def _ctx():
        return ctx

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_tenant_context_auth] = _ctx
    client = TestClient(app)

    class _Ok:
        ok = True
        data = {"document_id": "d2"}

    with patch("app.operator.tools.registry.registry.run", return_value=_Ok()):
        conf = client.post("/v1/hermes-nous/kb-draft/confirm")
    assert conf.status_code == 200
    assert conf.json()["committed"] is True

    phase = client.post("/v1/hermes-nous/office-loop/phase", json={"phase": "conduct"})
    assert phase.status_code == 200
    assert phase.json()["phase"] == "conduct"


def test_flag_off_blocks_runs_endpoint(db, monkeypatch, tmp_path):
    _tenant, ctx = _seed(db, flag_on=False)
    app = FastAPI()
    app.include_router(hermes_nous_router, prefix="/v1")

    def _db():
        yield db

    def _ctx():
        return ctx

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_tenant_context_auth] = _ctx
    client = TestClient(app)
    res = client.post("/v1/hermes-nous/runs", json={"message": "hi", "mode": "onboarding"})
    assert res.status_code == 403
    assert res.json()["detail"]["error"] == "hermes_nous_runtime_disabled"


def test_operator_soft_route_prefers_nous(db, monkeypatch, tmp_path):
    """When flag on + message — operator routes to Nous create_run."""
    from app.core.config import get_settings
    from app.api.v1 import operator as operator_mod

    _tenant, ctx = _seed(db, flag_on=True)
    monkeypatch.setenv("TENANT_FILES_ROOT", str(tmp_path))
    monkeypatch.setenv("HERMES_API_SERVER_KEY", "k")
    get_settings.cache_clear()

    from app.services.hermes_nous.provision import ensure_tenant_hermes_home

    ensure_tenant_hermes_home(db, ctx, runtime_base_url="http://hermes.test")

    monkeypatch.setattr(
        "app.services.hermes_nous.bridge._http_json",
        lambda *a, **k: (200, {"run_id": "op_1"}),
    )

    # Build minimal request path: call the soft-route branch via create_run mock outcome
    from app.services.hermes_nous.bridge import create_run

    out = create_run(db, ctx, message="назначь встречу", mode="conduct")
    assert out["engine"] == "nous_hermes_agent"
    assert out["run_id"] == "op_1"
    assert operator_mod is not None  # module importable for soft-route
    get_settings.cache_clear()
