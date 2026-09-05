"""Conversation-driven onboarding orchestration (O1)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.models.conversation import Conversation, Message
from app.models.tenant import Tenant
from app.services.events import emit_event
from app.services.knowledge_documents import publish_tenant_knowledge_document, upsert_draft_knowledge
from app.services.onboarding_metrics import MILESTONE_STARTED, record_ttfv_milestone

ONBOARDING_CHANNEL = "onboarding"

ONBOARDING_WELCOME = (
    "Расскажите о своём бизнесе или пришлите то, что уже есть. "
    "Можно дать ссылку на сайт, загрузить прайс, коммерческое предложение, "
    "презентацию, меню, каталог или просто написать своими словами."
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_onboarding_state(tenant: Tenant) -> dict[str, Any]:
    settings = tenant.settings if isinstance(tenant.settings, dict) else {}
    onboarding = settings.get("onboarding") if isinstance(settings.get("onboarding"), dict) else {}
    draft = settings.get("onboarding_draft") if isinstance(settings.get("onboarding_draft"), dict) else {}
    return {
        "status": onboarding.get("status") or "not_started",
        "conversation_id": onboarding.get("conversation_id"),
        "started_at": onboarding.get("started_at"),
        "completed_at": onboarding.get("completed_at"),
        "draft": draft,
    }


def _merge_tenant_settings(tenant: Tenant, patch: dict[str, Any]) -> dict[str, Any]:
    current = dict(tenant.settings or {})
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(current.get(key), dict):
            merged = dict(current[key])
            merged.update(value)
            current[key] = merged
        else:
            current[key] = value
    tenant.settings = current
    return current


def start_onboarding(
    db: Session,
    ctx: TenantContext,
    *,
    force_new: bool = False,
) -> dict[str, Any]:
    """Create or resume onboarding conversation with DELNO welcome message."""
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    state = get_onboarding_state(tenant)
    existing_id = state.get("conversation_id")

    if existing_id and not force_new:
        try:
            conversation_uuid = uuid.UUID(str(existing_id))
        except ValueError:
            conversation_uuid = None
        if conversation_uuid:
            conversation = (
                db.query(Conversation)
                .filter(
                    Conversation.id == conversation_uuid,
                    Conversation.tenant_id == ctx.tenant_id,
                    Conversation.channel == ONBOARDING_CHANNEL,
                )
                .one_or_none()
            )
            if conversation:
                return {
                    "ok": True,
                    "resumed": True,
                    "conversation_id": str(conversation.id),
                    "status": state.get("status") or "in_progress",
                    "reply": ONBOARDING_WELCOME,
                }

    conversation = Conversation(tenant_id=ctx.tenant_id, channel=ONBOARDING_CHANNEL, meta={"mode": "onboarding"})
    db.add(conversation)
    db.flush()

    db.add(
        Message(
            tenant_id=ctx.tenant_id,
            conversation_id=conversation.id,
            role="assistant",
            body=ONBOARDING_WELCOME,
            meta={"kind": "onboarding_welcome"},
        )
    )

    _merge_tenant_settings(
        tenant,
        {
            "onboarding": {
                "status": "in_progress",
                "conversation_id": str(conversation.id),
                "started_at": _utc_now_iso(),
                "completed_at": None,
            },
            "onboarding_draft": state.get("draft") or {},
        },
    )

    emit_event(
        db,
        tenant_id=ctx.tenant_id,
        event_type="onboarding.started",
        category="domain",
        source="tenant.onboarding",
        payload={
            "conversation_id": str(conversation.id),
            "resumed": False,
        },
    )
    record_ttfv_milestone(db, tenant, MILESTONE_STARTED, tenant_id=ctx.tenant_id)
    db.commit()

    return {
        "ok": True,
        "resumed": False,
        "conversation_id": str(conversation.id),
        "status": "in_progress",
        "reply": ONBOARDING_WELCOME,
    }


def add_onboarding_draft_knowledge(
    db: Session,
    tenant: Tenant,
    *,
    title: str,
    body: str,
    source: str = "onboarding.conversation",
    document_id: str | None = None,
) -> dict[str, Any]:
    result = upsert_draft_knowledge(
        db,
        tenant,
        title=title,
        body=body,
        source=source,
        document_id=document_id,
    )
    if result.get("ok"):
        emit_event(
            db,
            tenant_id=tenant.id,
            event_type="onboarding.knowledge_draft_updated",
            category="operational",
            source=source,
            payload={"document_id": result.get("document_id"), "title": title[:120]},
        )
    return result


def publish_onboarding_knowledge(
    db: Session,
    tenant: Tenant,
    *,
    document_ids: list[str],
    approved_by: str,
) -> dict[str, Any]:
    """Flip draft documents to published (HIGH_IMPACT — explicit confirm in UI/tools)."""
    published: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for doc_id in document_ids:
        result = publish_tenant_knowledge_document(
            db,
            tenant,
            document_id=doc_id,
            approved_by=approved_by,
            source="onboarding.publish",
        )
        if result.get("ok"):
            published.append({"document_id": doc_id, **result})
        else:
            errors.append({"document_id": doc_id, **result})

    if published:
        _merge_tenant_settings(
            tenant,
            {
                "onboarding": {
                    "status": "published",
                    "completed_at": _utc_now_iso(),
                },
            },
        )
        emit_event(
            db,
            tenant_id=tenant.id,
            event_type="onboarding.knowledge_published",
            category="domain",
            source="onboarding.publish",
            payload={"document_ids": [p["document_id"] for p in published], "count": len(published)},
        )
        emit_event(
            db,
            tenant_id=tenant.id,
            event_type="onboarding.completed",
            category="domain",
            source="onboarding.publish",
            payload={"document_ids": [p["document_id"] for p in published]},
        )

    db.commit()
    return {"ok": bool(published) and not errors, "published": published, "errors": errors}
