"""Hermes billing tools — balance / tariff for the owner."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.operator.tools.registry import ToolResult
from app.services import billing


class BillingSummaryTool:
    name = "billing.summary"
    description = "Show tenant token balance, tariff (RUB per 1k tokens) and recent usage."
    critical_write = False
    parameters_schema = {"type": "object", "properties": {}}

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        out = billing.usage_summary(db, ctx)
        return ToolResult(ok=True, data=out, message=out.get("message_ru") or "ok")
