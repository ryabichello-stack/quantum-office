"""E2.5 — signed webhooks for messenger channels."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.adapters.channels import get_channel_adapter
from app.core.db import get_db
from app.services.channel_auto_reply import process_inbound_auto_reply
from app.services.channel_router import ChannelContext
from app.services.events import emit_event
from app.services.inbound_messages import resolve_channel_account

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _context_for_account(account) -> ChannelContext:
    from app.models.tenant import Tenant

    tenant = account.tenant if hasattr(account, "tenant") else None
    if tenant is None:
        raise HTTPException(status_code=500, detail="tenant_missing")

    from app.core.principals import PRINCIPAL_TEXT_GUEST

    return ChannelContext(
        tenant_id=tenant.id,
        tenant_slug=tenant.slug,
        channel_type=account.type,
        principal_id=PRINCIPAL_TEXT_GUEST,
        channel_account_id=account.id,
    )


async def _handle_channel_webhook(
    *,
    channel_type: str,
    channel_account_id: UUID,
    request: Request,
    db: Session,
    secret_header: str | None,
) -> dict:
    account = resolve_channel_account(db, channel_account_id)
    if not account or account.type != channel_type:
        raise HTTPException(status_code=404, detail="channel_account_not_found")

    adapter = get_channel_adapter(channel_type)
    if not adapter:
        raise HTTPException(status_code=503, detail=f"{channel_type}_adapter_unavailable")

    meta = account.meta if isinstance(account.meta, dict) else {}
    expected_secret = meta.get("webhook_secret")
    if not adapter.verify_webhook_secret(
        secret_header=secret_header,
        expected_secret=str(expected_secret) if expected_secret else None,
    ):
        raise HTTPException(status_code=403, detail="invalid_webhook_secret")

    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="invalid_payload")

    from app.models.tenant import Tenant

    tenant = db.query(Tenant).filter(Tenant.id == account.tenant_id).one_or_none()
    if not tenant or not tenant.is_active:
        raise HTTPException(status_code=404, detail="tenant_inactive")

    account.tenant = tenant  # type: ignore[attr-defined]
    ctx = _context_for_account(account)
    credentials = account.credentials_encrypted if isinstance(account.credentials_encrypted, dict) else {}

    inbounds = adapter.parse_webhook(payload)
    emit_event(
        db,
        tenant_id=tenant.id,
        event_type="webhook.received",
        category="operational",
        source=f"webhook.{channel_type}",
        payload={
            "channel": channel_type,
            "channel_account_id": str(account.id),
            "update_type": payload.get("update_type"),
            "inbound_count": len(inbounds),
        },
    )

    recorded = []
    try:
        for inbound in inbounds:
            item = process_inbound_auto_reply(
                db,
                ctx,
                inbound,
                adapter=adapter,
                credentials=credentials,
            )
            recorded.append(item)

        emit_event(
            db,
            tenant_id=tenant.id,
            event_type="webhook.processed",
            category="operational",
            source=f"webhook.{channel_type}",
            payload={
                "channel": channel_type,
                "channel_account_id": str(account.id),
                "recorded_count": len(recorded),
                "delivered_count": sum(1 for item in recorded if item.get("delivered")),
            },
        )
        db.commit()
        return {"ok": True, "recorded": recorded}
    except Exception as exc:
        emit_event(
            db,
            tenant_id=tenant.id,
            event_type="webhook.failed",
            category="operational",
            source=f"webhook.{channel_type}",
            payload={
                "channel": channel_type,
                "channel_account_id": str(account.id),
                "error": str(exc)[:300],
            },
        )
        db.commit()
        raise


@router.post("/telegram/{channel_account_id}")
async def telegram_webhook(
    channel_account_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    x_telegram_bot_api_secret_token: str | None = Header(default=None, alias="X-Telegram-Bot-Api-Secret-Token"),
) -> dict:
    return await _handle_channel_webhook(
        channel_type="telegram",
        channel_account_id=channel_account_id,
        request=request,
        db=db,
        secret_header=x_telegram_bot_api_secret_token,
    )


@router.post("/max/{channel_account_id}")
async def max_webhook(
    channel_account_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    x_max_bot_api_secret: str | None = Header(default=None, alias="X-Max-Bot-Api-Secret"),
) -> dict:
    return await _handle_channel_webhook(
        channel_type="max",
        channel_account_id=channel_account_id,
        request=request,
        db=db,
        secret_header=x_max_bot_api_secret,
    )
