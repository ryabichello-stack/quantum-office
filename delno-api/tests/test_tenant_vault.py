from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.core.tenant import TenantContext
from app.models.tenant import Tenant
from app.services.tenant_vault import (
    looks_like_credential_paste,
    parse_credential_paste,
    save_secret,
    wants_sip_secret_form,
)


def _db():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_detect_credential_paste():
    assert looks_like_credential_paste("400348777/garik\nmD0Q^m8HsBgK")
    assert not looks_like_credential_paste("какой пароль от почты?")
    assert wants_sip_secret_form("Открой безопасную форму SIP-пароля Mango")
    parsed = parse_credential_paste("400348777/garik\nmD0Q^m8HsBgK")
    assert parsed["login"] == "400348777/garik"
    assert parsed["password"] == "mD0Q^m8HsBgK"


def test_save_secret_masks_login():
    db = _db()
    tenant = Tenant(slug="sec", name="Sec", settings={}, is_active=True)
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    ctx = TenantContext(
        tenant_id=tenant.id,
        tenant_slug=tenant.slug,
        user_id=None,
        role="tenant_owner",
    )
    out = save_secret(db, ctx, kind="mango_sip", login="400348777/garik", password="mD0Q^m8HsBgK")
    assert out["ok"] is True
    assert "mD0Q" not in str(out)
    assert out["login_masked"]
    db.refresh(tenant)
    secrets = (tenant.settings or {}).get("secrets") or {}
    assert secrets["mango_sip"]["password"] == "mD0Q^m8HsBgK"
