from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.models.feature_flag import FeatureFlag

FLAG_HERMES_NOUS_RUNTIME = "hermes_nous_runtime"


def is_hermes_nous_enabled(db: Session, ctx: TenantContext) -> bool:
    row = (
        db.query(FeatureFlag)
        .filter(
            FeatureFlag.tenant_id == ctx.tenant_id,
            FeatureFlag.flag_key == FLAG_HERMES_NOUS_RUNTIME,
        )
        .one_or_none()
    )
    return bool(row and row.enabled)
