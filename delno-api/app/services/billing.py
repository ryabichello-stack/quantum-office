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

# Default dogfood tariff (RUB, client-facing). Owner can override in tenant.settings.billing
DEFAULT_TARIFF = {
    "currency": "RUB",
    "llm_input_per_1k": 0.50,  # client price, not vendor cost
    "llm_output_per_1k": 2.00,
    "tts_per_1k_chars": 0.80,
    "stt_per_minute": 3.00,
    "call_minute": 8.00,
    "web_fetch": 0.05,
    "web_search": 0.10,
    "browse_page": 0.25,
}

# OpenAI standard list price USD / 1M tokens (себестоимость). Keep in sync with platform pricing page.
VENDOR_USD_PER_1M: dict[str, tuple[float, float]] = {
    "gpt-5.4-mini": (0.75, 4.50),
    "gpt-5.4-nano": (0.20, 1.25),
    "gpt-5.4": (2.50, 15.00),
    "gpt-5.2": (1.75, 14.00),
    "gpt-5.1": (1.25, 10.00),
    "gpt-5-mini": (0.25, 2.00),
    "gpt-5-nano": (0.05, 0.40),
    "gpt-5": (1.25, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
}
_VENDOR_DEFAULT_USD = (0.75, 4.50)  # assume current Hermes default class


def _normalize_model(model: str | None) -> str:
    name = (model or "").strip().lower()
    if not name:
        return ""
    # strip dated suffixes: gpt-5.4-mini-2026-03-17
    for key in sorted(VENDOR_USD_PER_1M.keys(), key=len, reverse=True):
        if name == key or name.startswith(key + "-"):
            return key
    return name


def estimate_llm_vendor_usd(
    *,
    prompt_tokens: int,
    completion_tokens: int,
    model: str | None = None,
) -> float:
    key = _normalize_model(model)
    inp, out = VENDOR_USD_PER_1M.get(key, _VENDOR_DEFAULT_USD)
    return round(
        (int(prompt_tokens) / 1_000_000.0) * inp
        + (int(completion_tokens) / 1_000_000.0) * out,
        6,
    )


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
    cost_usd = estimate_llm_vendor_usd(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        model=model,
    )
    total_tokens = int(prompt_tokens) + int(completion_tokens)
    out = charge(
        db,
        ctx,
        metric="llm.tokens",
        quantity=float(total_tokens),
        cost=cost,
        meta={
            "prompt_tokens": int(prompt_tokens),
            "completion_tokens": int(completion_tokens),
            "model": model,
            "channel": channel,
            "cost_usd": cost_usd,
            "cost_rub": cost,
            "currency_client": tariff.get("currency") or "RUB",
        },
    )
    out["cost_usd"] = cost_usd
    out["prompt_tokens"] = int(prompt_tokens)
    out["completion_tokens"] = int(completion_tokens)
    return out


def record_web_usage(db: Session, ctx: TenantContext, *, kind: str) -> dict[str, Any]:
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    tariff = get_tariff(tenant)
    key = {"search": "web_search", "fetch": "web_fetch", "browse": "browse_page"}.get(kind, "web_fetch")
    return charge(db, ctx, metric=f"web.{kind}", quantity=1.0, cost=float(tariff.get(key) or 0), meta={"kind": kind})


def _llm_totals_from_rows(rows: list[UsageRecord]) -> dict[str, Any]:
    prompt = 0
    completion = 0
    cost_rub = 0.0
    cost_usd = 0.0
    events = 0
    for r in rows:
        if r.metric != "llm.tokens":
            continue
        events += 1
        meta = r.meta if isinstance(r.meta, dict) else {}
        p = int(meta.get("prompt_tokens") or 0)
        c = int(meta.get("completion_tokens") or 0)
        prompt += p
        completion += c
        cost_rub += float(meta.get("cost_rub") or meta.get("cost") or 0)
        if meta.get("cost_usd") is not None:
            cost_usd += float(meta.get("cost_usd") or 0)
        elif p or c:
            # backfill for rows recorded before cost_usd existed
            cost_usd += estimate_llm_vendor_usd(
                prompt_tokens=p,
                completion_tokens=c,
                model=str(meta.get("model") or "") or None,
            )
    return {
        "events": events,
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "tokens_total": prompt + completion,
        "cost_client_rub": round(cost_rub, 4),
        "cost_vendor_usd": round(cost_usd, 6),
        "margin_rub_approx": round(cost_rub, 4),  # client charge; USD is COGS
    }


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
    llm_rows = (
        db.query(UsageRecord)
        .filter(UsageRecord.tenant_id == ctx.tenant_id, UsageRecord.metric == "llm.tokens")
        .all()
    )
    llm = _llm_totals_from_rows(llm_rows)
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
        "llm": llm,
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
            f"Токены: {llm['tokens_total']} (in {llm['prompt_tokens']} / out {llm['completion_tokens']}). "
            f"Себестоимость ≈ ${llm['cost_vendor_usd']:.4f}. "
            f"Клиенту начислено {llm['cost_client_rub']:.2f} {balance['currency']}. "
            f"Баланс {balance['token_credits']:.2f} {balance['currency']}."
        ),
    }


def platform_cost_overview(db: Session) -> dict[str, Any]:
    """All tenants: tokens + vendor USD + client RUB (platform admin)."""
    tenants = db.query(Tenant).filter(Tenant.is_active.is_(True)).order_by(Tenant.slug.asc()).all()
    items: list[dict[str, Any]] = []
    totals = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "tokens_total": 0,
        "cost_vendor_usd": 0.0,
        "cost_client_rub": 0.0,
        "events": 0,
    }
    for tenant in tenants:
        rows = (
            db.query(UsageRecord)
            .filter(UsageRecord.tenant_id == tenant.id, UsageRecord.metric == "llm.tokens")
            .all()
        )
        llm = _llm_totals_from_rows(rows)
        bal = get_balance(tenant)
        items.append(
            {
                "tenant_id": str(tenant.id),
                "tenant_slug": tenant.slug,
                "tenant_name": tenant.name,
                "llm": llm,
                "balance": bal,
            }
        )
        for k in ("prompt_tokens", "completion_tokens", "tokens_total", "events"):
            totals[k] += int(llm.get(k) or 0)
        totals["cost_vendor_usd"] += float(llm.get("cost_vendor_usd") or 0)
        totals["cost_client_rub"] += float(llm.get("cost_client_rub") or 0)
    totals["cost_vendor_usd"] = round(totals["cost_vendor_usd"], 6)
    totals["cost_client_rub"] = round(totals["cost_client_rub"], 4)
    return {
        "ok": True,
        "currency_client": "RUB",
        "currency_vendor": "USD",
        "totals": totals,
        "tenants": items,
        "message_ru": (
            f"Всего токенов {totals['tokens_total']}, "
            f"себестоимость ${totals['cost_vendor_usd']:.4f}, "
            f"клиентам {totals['cost_client_rub']:.2f} RUB."
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
