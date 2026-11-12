import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.core.tenant import TenantContext
from app.models.conversation import Conversation, Message
from app.models.tenant import Tenant
from app.operator.agent import _conversation_history_for_llm, _try_kb_credential_lookup
from app.operator.setup_intent import parse_setup_intent


def _db():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_conversation_history_excludes_latest_user():
    db = _db()
    tenant = Tenant(slug="mem", name="Mem", settings={}, is_active=True)
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    conv = Conversation(tenant_id=tenant.id, channel="hermes")
    db.add(conv)
    db.flush()
    from datetime import datetime, timedelta, timezone

    t0 = datetime.now(timezone.utc)
    db.add_all(
        [
            Message(
                tenant_id=tenant.id,
                conversation_id=conv.id,
                role="user",
                body="привет",
                created_at=t0,
            ),
            Message(
                tenant_id=tenant.id,
                conversation_id=conv.id,
                role="assistant",
                body="слушаю",
                created_at=t0 + timedelta(seconds=1),
            ),
            Message(
                tenant_id=tenant.id,
                conversation_id=conv.id,
                role="user",
                body="какой пароль",
                created_at=t0 + timedelta(seconds=2),
            ),
        ]
    )
    db.commit()

    hist = _conversation_history_for_llm(db, tenant_id=tenant.id, conversation_id=conv.id, limit=24)
    assert len(hist) == 2
    assert hist[0] == {"role": "user", "content": "привет"}
    assert hist[1] == {"role": "assistant", "content": "слушаю"}


def test_password_intent_routes_to_kb_not_settings():
    # regression: credential questions must not become note patches
    assert parse_setup_intent("какой пароль от почты") is None or parse_setup_intent(
        "какой пароль от почты"
    )["tool"] != "update_tenant_settings"
