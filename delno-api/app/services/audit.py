from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.models.audit import AuditLog


def write_audit(
    db: Session,
    ctx: TenantContext,
    *,
    action: str,
    actor: str = "operator",
    resource: str | None = None,
    old_value: dict | None = None,
    new_value: dict | None = None,
    result: str = "ok",
    detail: str | None = None,
) -> AuditLog:
    row = AuditLog(
        tenant_id=ctx.tenant_id,
        actor=actor,
        action=action,
        resource=resource,
        old_value=old_value,
        new_value=new_value,
        result=result,
        detail=detail,
    )
    db.add(row)
    db.flush()
    return row
