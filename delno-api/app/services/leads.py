import httpx

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.tenant import TenantContext
from app.models.lead import Lead
from app.services.audit import write_audit
from app.services.events import emit_event
from app.services.party_enrichment import enrich_lead_from_inn


def notify_lead_telegram(lead: Lead) -> bool:
    settings = get_settings()
    token = settings.telegram_bot_token
    chat_id = settings.telegram_chat_id
    if not token or not chat_id:
        return False
    lines = [
        "Новая заявка DELNO",
        f"Источник: {lead.source}",
        f"Имя: {lead.name}",
        f"Телефон: {lead.phone}",
    ]
    if lead.company:
        lines.append(f"Компания: {lead.company}")
    if lead.inn:
        lines.append(f"ИНН: {lead.inn}")
    if lead.email:
        lines.append(f"Почта: {lead.email}")
    if lead.website:
        lines.append(f"Сайт: {lead.website}")
    text = "\n".join(lines)
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.post(url, json={"chat_id": chat_id, "text": text})
            return response.is_success
    except httpx.HTTPError:
        return False


def create_lead_record(
    db: Session,
    ctx: TenantContext,
    *,
    name: str,
    phone: str,
    email: str | None = None,
    company: str | None = None,
    website: str | None = None,
    source: str = "website",
    inn: str | None = None,
    audit_action: str = "lead.create",
    event_source: str = "api.leads",
    channel: str | None = None,
) -> tuple[Lead, dict]:
    """Create lead, optional INN enrichment, audit + lead.created event."""
    lead = Lead(
        tenant_id=ctx.tenant_id,
        source=source,
        name=name.strip(),
        phone=phone.strip(),
        email=email.strip() if email else None,
        company=company.strip() if company else None,
        website=website.strip() if website else None,
    )
    db.add(lead)
    db.flush()

    enrich_result = enrich_lead_from_inn(
        db,
        lead,
        inn,
        tenant_id=ctx.tenant_id,
        source=f"{event_source}.enrich",
    )

    notified = notify_lead_telegram(lead)
    write_audit(
        db,
        ctx,
        action=audit_action,
        resource=f"lead:{lead.id}",
        new_value={
            "name": lead.name,
            "phone": lead.phone,
            "source": lead.source,
            "inn": lead.inn,
            "enriched": enrich_result.get("enriched"),
        },
    )
    emit_event(
        db,
        tenant_id=ctx.tenant_id,
        event_type="lead.created",
        category="operational",
        source=event_source,
        payload={
            "lead_id": str(lead.id),
            "source": lead.source,
            "channel": channel or source,
            "inn": lead.inn,
            "party_enriched": enrich_result.get("enriched"),
        },
    )
    return lead, {"telegram_notified": notified, "enrichment": enrich_result}
