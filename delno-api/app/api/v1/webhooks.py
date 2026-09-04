"""E2.5 — signed webhooks for messenger channels."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.adapters.channels import get_channel_adapter
from app.core.db import get_db
from app.services.channel_auto_reply import process_inbound_auto_reply
from app.services.channel_router import ChannelContext
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


@router.post("/telegram/{channel_account_id}")
async def telegram_webhook(
    channel_account_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    x_telegram_bot_api_secret_token: str | None = Header(default=None, alias="X-Telegram-Bot-Api-Secret-Token"),
) -> dict:
    account = resolve_channel_account(db, channel_account_id)
    if not account or account.type != "telegram":
        raise HTTPException(status_code=404, detail="channel_account_not_found")

    adapter = get_channel_adapter("telegram")
    if not adapter:
        raise HTTPException(status_code=503, detail="telegram_adapter_unavailable")

    meta = account.meta if isinstance(account.meta, dict) else {}
    expected_secret = meta.get("webhook_secret")
    if not adapter.verify_webhook_secret(
        secret_header=x_telegram_bot_api_secret_token,
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

    recorded = []
    for inbound in adapter.parse_webhook(payload):
        item = process_inbound_auto_reply(
            db,
            ctx,
            inbound,
            adapter=adapter,
            credentials=credentials,
        )
        recorded.append(item)

    db.commit()
    return {"ok": True, "recorded": recorded}
