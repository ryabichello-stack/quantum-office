import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.core.tenant import TenantContext
from app.models.tenant import Tenant
from app.models.usage_record import UsageRecord  # noqa: F401
from app.operator.setup_intent import parse_setup_intent
from app.services import billing
from app.services.web_browser import html_to_text


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


def test_billing_defaults_and_charge(db):
    tenant = Tenant(slug=f"bill-{uuid.uuid4().hex[:6]}", name="Bill", settings={}, is_active=True)
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    ctx = TenantContext(tenant_id=tenant.id, tenant_slug=tenant.slug, role="tenant_owner")

    billing.ensure_billing_defaults(db, tenant, grant_credits=100.0)
    db.commit()
    bal = billing.get_balance(tenant)
    assert bal["token_credits"] == 100.0

    out = billing.record_llm_usage(db, ctx, prompt_tokens=1000, completion_tokens=500, model="gpt-4o-mini")
    assert out["ok"] is True
    assert out["cost"] > 0
    assert out["cost_usd"] > 0
    # 1000/1e6*0.15 + 500/1e6*0.60 = 0.00015 + 0.0003 = 0.00045
    assert abs(out["cost_usd"] - 0.00045) < 1e-9
    db.refresh(tenant)
    assert billing.get_balance(tenant)["token_credits"] < 100.0

    summary = billing.usage_summary(db, ctx)
    assert summary["llm"]["tokens_total"] == 1500
    assert summary["llm"]["prompt_tokens"] == 1000
    assert summary["llm"]["completion_tokens"] == 500
    assert abs(summary["llm"]["cost_vendor_usd"] - 0.00045) < 1e-9
    assert summary["llm"]["cost_client_rub"] > 0


def test_vendor_usd_model_normalize():
    usd = billing.estimate_llm_vendor_usd(
        prompt_tokens=1_000_000,
        completion_tokens=0,
        model="gpt-5.4-mini-2026-03-17",
    )
    assert abs(usd - 0.75) < 1e-9


def test_platform_cost_overview(db):
    a = Tenant(slug=f"a-{uuid.uuid4().hex[:6]}", name="A", settings={}, is_active=True)
    b = Tenant(slug=f"b-{uuid.uuid4().hex[:6]}", name="B", settings={}, is_active=True)
    db.add_all([a, b])
    db.commit()
    db.refresh(a)
    db.refresh(b)
    ctx_a = TenantContext(tenant_id=a.id, tenant_slug=a.slug, role="tenant_owner")
    ctx_b = TenantContext(tenant_id=b.id, tenant_slug=b.slug, role="tenant_owner")
    billing.ensure_billing_defaults(db, a, grant_credits=50)
    billing.ensure_billing_defaults(db, b, grant_credits=50)
    billing.record_llm_usage(db, ctx_a, prompt_tokens=2000, completion_tokens=0, model="gpt-5.4-mini")
    billing.record_llm_usage(db, ctx_b, prompt_tokens=1000, completion_tokens=0, model="gpt-5.4-mini")
    db.commit()

    overview = billing.platform_cost_overview(db)
    assert overview["ok"] is True
    assert overview["totals"]["prompt_tokens"] >= 3000
    assert overview["totals"]["cost_vendor_usd"] > 0
    slugs = {t["tenant_slug"] for t in overview["tenants"]}
    assert a.slug in slugs and b.slug in slugs


def test_html_to_text_strips_scripts():
    title, text = html_to_text("<html><head><title>Hi</title></head><body><script>x</script><p>Hello</p></body></html>")
    assert title == "Hi"
    assert "Hello" in text
    assert "x" not in text


def test_parse_billing_and_web_intents():
    assert parse_setup_intent("Покажи расход токенов и баланс")["tool"] == "billing.summary"
