"""Hermes: deep multi-source company KB draft (site + social + web + Q&A)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.operator.tools.registry import ToolResult
from app.services.hermes_kb_build import build_company_kb_draft


class OfficeBuildKbDraftTool:
    name = "office.build_kb_draft"
    description = (
        "Deep company knowledge onboarding: crawl the website (many pages), "
        "harvest Telegram/Instagram/VK/MAX links, search the open web by company "
        "profile, structure a KB draft for owner confirm, and ask clarifying "
        "questions. Prefer this over office.import_website when building KB "
        "together with the client. Does not auto-publish."
    )
    critical_write = False
    parameters_schema = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Primary website or social URL / domain",
            },
            "urls": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional extra URLs (site + Telegram + Instagram + VK…)",
            },
            "message": {
                "type": "string",
                "description": "Free text that may contain URLs and company notes",
            },
            "free_text": {
                "type": "string",
                "description": "Owner-provided company description / offer / FAQ",
            },
            "max_pages": {
                "type": "integer",
                "default": 10,
                "description": "Max same-host pages to crawl per seed URL",
            },
            "also_search": {
                "type": "boolean",
                "default": True,
                "description": "Also search the open web by company profile",
            },
        },
        "required": [],
    }

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        urls: list[str] = []
        raw_url = str(params.get("url") or "").strip()
        if raw_url:
            urls.append(raw_url)
        extra = params.get("urls")
        if isinstance(extra, (list, tuple)):
            urls.extend(str(u).strip() for u in extra if str(u).strip())
        max_pages = int(params.get("max_pages") or 10)
        also_search = bool(params.get("also_search", True))
        try:
            result = build_company_kb_draft(
                db,
                ctx,
                urls=urls or None,
                message=str(params.get("message") or "") or None,
                free_text=str(params.get("free_text") or "") or None,
                max_pages=max(3, min(max_pages, 16)),
                also_search=also_search,
            )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, message=f"Не удалось собрать KB: {exc}")

        ok = bool(result.get("ok"))
        return ToolResult(
            ok=ok,
            data=result,
            message=str(result.get("message") or ("Готово" if ok else "Ошибка сбора KB")),
        )
