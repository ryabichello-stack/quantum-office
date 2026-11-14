"""Multi-tenant Mango SIP: any tenant, account/employee login, dedicated trunk."""

from __future__ import annotations

import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.core.tenant import TenantContext
from app.models.phone_number import PhoneNumber  # noqa: F401
from app.models.tenant import Tenant
from app.services import phone_provision
from app.services.sip_probe import parse_mango_login, trunk_id_for_tenant
from app.services.tenant_vault import credential_form_spec


def test_parse_mango_login_requires_account_slash_employee():
    ok = parse_mango_login("123456789/ivan")
    assert ok["error"] is None
    assert ok["account"] == "123456789"
    assert ok["employee"] == "ivan"

    bad = parse_mango_login("ivan")
    assert bad["error"] == "login_must_be_account_slash_employee"


def test_trunk_id_is_per_tenant():
    assert trunk_id_for_tenant("acme-corp") == "delno-acme-corp"
    assert trunk_id_for_tenant("quantum-labs") != trunk_id_for_tenant("delno-demo")


def test_provision_attaches_tenant_trunk_id():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    tenant = Tenant(id=uuid.uuid4(), slug="acme-sip", name="Acme", settings={}, is_active=True)
    db.add(tenant)
    db.commit()
    ctx = TenantContext(tenant_id=tenant.id, tenant_slug=tenant.slug, role="tenant_owner")
    out = phone_provision.provision_phone(db, ctx, e164="+79991112233")
    assert out["ok"] is True
    assert out["phone"]["routing_config"]["trunk_id"] == "delno-acme-sip"
    db.close()


def test_mango_form_hint_is_generic_not_dogfood():
    form = credential_form_spec("mango_sip")
    hint = str(form.get("hint") or "")
    assert "аккаунт/сотрудник" in hint.lower() or "номер_аккаунта/сотрудник" in hint
    assert "400348777" not in hint
    assert "garik" not in hint.lower()
