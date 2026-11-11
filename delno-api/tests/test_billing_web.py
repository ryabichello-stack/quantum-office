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
    db.refresh(tenant)
    assert billing.get_balance(tenant)["token_credits"] < 100.0


def test_html_to_text_strips_scripts():
    title, text = html_to_text("<html><head><title>Hi</title></head><body><script>x</script><p>Hello</p></body></html>")
    assert title == "Hi"
    assert "Hello" in text
    assert "x" not in text


def test_parse_billing_and_web_intents():
    assert parse_setup_intent("Покажи расход токенов и баланс")["tool"] == "billing.summary"
