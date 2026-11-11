"""Token/minute billing for tenants — usage metering + client-facing price."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.models.tenant import Tenant
from app.models.usage_record import UsageRecord
from app.services.usage import record_usage

# Default dogfood tariff (RUB). Owner can override in tenant.settings.billing
DEFAULT_TARIFF = {
    "currency": "RUB",
    "llm_input_per_1k": 0.50,  # ≈ cost+margin for gpt-4o-mini class
    "llm_output_per_1k": 2.00,
    "tts_per_1k_chars": 0.80,
    "stt_per_minute": 3.00,
    "call_minute": 8.00,
    "web_fetch": 0.05,
    "web_search": 0.10,
    "browse_page": 0.25,
}


def _billing_blob(tenant: Tenant) -> dict[str, Any]:
    settings = tenant.settings if isinstance(tenant.settings, dict) else {}
    raw = settings.get("billing")
    return dict(raw) if isinstance(raw, dict) else {}


def get_tariff(tenant: Tenant) -> dict[str, Any]:
    blob = _billing_blob(tenant)
    tariff = dict(DEFAULT_TARIFF)
    custom = blob.get("tariff") if isinstance(blob.get("tariff"), dict) else {}
    for key, value in custom.items():
        if key in tariff and isinstance(value, (int, float)):
            tariff[key] = float(value)
        elif key == "currency" and isinstance(value, str):
            tariff[key] = value
    return tariff


def get_balance(tenant: Tenant) -> dict[str, Any]:
    blob = _billing_blob(tenant)
    return {
        "currency": get_tariff(tenant)["currency"],
        "token_credits": float(blob.get("token_credits") or 0),  # prepaid RUB wallet
        "granted_credits": float(blob.get("granted_credits") or 0),
        "spent_credits": float(blob.get("spent_credits") or 0),
    }


def ensure_billing_defaults(db: Session, tenant: Tenant, *, grant_credits: float = 500.0) -> dict[str, Any]:
    settings = dict(tenant.settings) if isinstance(tenant.settings, dict) else {}
    billing = dict(settings.get("billing") or {})
    if "tariff" not in billing:
        billing["tariff"] = dict(DEFAULT_TARIFF)
    if "token_credits" not in billing:
        billing["token_credits"] = float(grant_credits)
        billing["granted_credits"] = float(grant_credits)
        billing["spent_credits"] = 0.0
    if "created_at" not in billing:
        billing["created_at"] = datetime.now(timezone.utc).isoformat()
    settings["billing"] = billing
    tenant.settings = settings
    db.flush()
    return billing


def estimate_llm_cost(tariff: dict[str, Any], *, prompt_tokens: int, completion_tokens: int) -> float:
    return (
        (prompt_tokens / 1000.0) * float(tariff["llm_input_per_1k"])
        + (completion_tokens / 1000.0) * float(tariff["llm_output_per_1k"])
    )


def charge(
    db: Session,
    ctx: TenantContext,
    *,
    metric: str,
    quantity: float,
    cost: float,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    ensure_billing_defaults(db, tenant)
    settings = dict(tenant.settings) if isinstance(tenant.settings, dict) else {}
    billing = dict(settings.get("billing") or {})
    balance = float(billing.get("token_credits") or 0)
    spent = float(billing.get("spent_credits") or 0)
    cost = round(float(cost), 4)
    if cost > 0:
        billing["token_credits"] = round(balance - cost, 4)
        billing["spent_credits"] = round(spent + cost, 4)
    settings["billing"] = billing
    tenant.settings = settings
    record_usage(
        db,
        tenant_id=ctx.tenant_id,
        metric=metric,
        quantity=quantity,
        meta={**(meta or {}), "cost": cost, "currency": get_tariff(tenant)["currency"]},
    )
    db.flush()
    return {
        "ok": True,
        "metric": metric,
        "quantity": quantity,
        "cost": cost,
        "balance": billing.get("token_credits"),
    }


def record_llm_usage(
    db: Session,
    ctx: TenantContext,
    *,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    model: str | None = None,
    channel: str | None = None,
) -> dict[str, Any]:
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    tariff = get_tariff(tenant)
    cost = estimate_llm_cost(tariff, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
    total_tokens = int(prompt_tokens) + int(completion_tokens)
    return charge(
        db,
        ctx,
        metric="llm.tokens",
        quantity=float(total_tokens),
        cost=cost,
        meta={
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "model": model,
            "channel": channel,
        },
    )


def record_web_usage(db: Session, ctx: TenantContext, *, kind: str) -> dict[str, Any]:
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    tariff = get_tariff(tenant)
    key = {"search": "web_search", "fetch": "web_fetch", "browse": "browse_page"}.get(kind, "web_fetch")
    return charge(db, ctx, metric=f"web.{kind}", quantity=1.0, cost=float(tariff.get(key) or 0), meta={"kind": kind})


def usage_summary(db: Session, ctx: TenantContext, *, limit: int = 50) -> dict[str, Any]:
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    ensure_billing_defaults(db, tenant)
    tariff = get_tariff(tenant)
    balance = get_balance(tenant)

    grouped = (
        db.query(UsageRecord.metric, func.sum(UsageRecord.quantity), func.count(UsageRecord.id))
        .filter(UsageRecord.tenant_id == ctx.tenant_id)
        .group_by(UsageRecord.metric)
        .all()
    )
    recent = (
        db.query(UsageRecord)
        .filter(UsageRecord.tenant_id == ctx.tenant_id)
        .order_by(UsageRecord.created_at.desc())
        .limit(min(limit, 100))
        .all()
    )
    return {
        "ok": True,
        "tenant_slug": ctx.tenant_slug,
        "balance": balance,
        "tariff": tariff,
        "by_metric": [
            {"metric": m, "quantity": float(q or 0), "events": int(c or 0)} for m, q, c in grouped
        ],
        "recent": [
            {
                "id": str(r.id),
                "metric": r.metric,
                "quantity": r.quantity,
                "meta": r.meta or {},
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in recent
        ],
        "message_ru": (
            f"Баланс {balance['token_credits']:.2f} {balance['currency']}. "
            f"Тариф LLM: {tariff['llm_input_per_1k']}/{tariff['llm_output_per_1k']} "
            f"за 1k input/output токенов."
        ),
    }


def top_up(db: Session, ctx: TenantContext, *, amount: float, note: str | None = None) -> dict[str, Any]:
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    ensure_billing_defaults(db, tenant)
    settings = dict(tenant.settings) if isinstance(tenant.settings, dict) else {}
    billing = dict(settings.get("billing") or {})
    amount = float(amount)
    billing["token_credits"] = round(float(billing.get("token_credits") or 0) + amount, 4)
    billing["granted_credits"] = round(float(billing.get("granted_credits") or 0) + amount, 4)
    settings["billing"] = billing
    tenant.settings = settings
    record_usage(
        db,
        tenant_id=ctx.tenant_id,
        metric="billing.topup",
        quantity=amount,
        meta={"note": note or "topup"},
    )
    db.commit()
    return {"ok": True, "balance": get_balance(tenant), "added": amount}
