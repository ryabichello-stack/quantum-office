"""Hermes: deep multi-source company KB draft (site + social + web + Q&A)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.operator.tools.registry import ToolResult
from app.services.hermes_kb_build import build_company_kb_draft
from app.services.hermes_nous.onboarding import confirm_kb_draft, get_office_loop


class OfficeBuildKbDraftTool:
    name = "office.build_kb_draft"
    description = (
        "Deep company knowledge onboarding OR enrichment: crawl the website (many pages), "
        "harvest Telegram/Instagram/VK/MAX links, search the open web by company "
        "profile, structure a KB draft for owner review, and ask clarifying "
        "questions. Use again with also_search=true when the owner says «обогати» / "
        "enrich — that is NOT a publish. Prefer this over office.import_website when "
        "building KB together with the client. Does not auto-publish; after the draft "
        "the reply must show the full profile and offer save / enrich / edit."
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


class OfficeConfirmKbDraftTool:
    """Commit office_loop.kb_draft into knowledge + mark kb_ready / advance phase.

    Owner phrases like «положи в кб» / «подтверди черновик» are the confirmation —
    do not wrap this in a second upload_knowledge_snippet confirm card.
    """

    name = "office.confirm_kb_draft"
    description = (
        "Commit the saved commercial KB draft into the live knowledge base and "
        "mark the office KB setup step done. Use ONLY when the owner explicitly says "
        "«положи в кб», «подтверди черновик», «сохрани в базу / профиль» after a draft "
        "exists. NEVER use for «обогати» / enrich / «найди ещё» — that needs "
        "office.build_kb_draft instead. Prefer this over upload_knowledge_snippet "
        "for onboarding drafts."
    )
    critical_write = False  # owner already confirmed in chat text
    parameters_schema = {"type": "object", "properties": {}}

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        loop = get_office_loop(db, ctx)
        draft = loop.get("kb_draft") if isinstance(loop, dict) else None
        if not isinstance(draft, dict) or not str(draft.get("body") or "").strip():
            return ToolResult(
                ok=False,
                message="Нет черновика KB — сначала соберите профиль (office.build_kb_draft).",
                data={"loop": loop},
            )
        if str(draft.get("status") or "") == "committed":
            return ToolResult(
                ok=True,
                data={"already": True, "loop": loop},
                message=(
                    "Черновик уже в боевой KB. Шаг «знания» закрыт — "
                    "дальше подключаем инструменты (hermes.setup_status)."
                ),
            )
        out = confirm_kb_draft(db, ctx)
        if not out.get("ok"):
            return ToolResult(
                ok=False,
                data=out,
                message=f"Не удалось положить черновик в KB: {out.get('error') or 'error'}",
            )
        title = str(draft.get("title") or "Профиль компании")
        next_chips: list[dict[str, str]] = []
        try:
            from app.services.hermes_guide import chip_actions_for_office

            next_chips = chip_actions_for_office(db, ctx, tool_calls=None)
        except Exception:
            next_chips = [
                {"title": "Телефон", "text": "Настрой телефон секретаря"},
                {"title": "Каналы", "text": "Что ещё настроить в каналах?"},
                {"title": "Статус", "text": "Статус сетапа"},
            ]
        data = dict(out or {})
        data["suggested_actions"] = next_chips
        return ToolResult(
            ok=True,
            data=data,
            message=(
                f"Черновик «{title}» записан в боевую KB. "
                "Шаг «знания» готов — следующий: инструменты офиса "
                "(телефон / каналы / почта). Смотри hermes.setup_status."
            ),
        )
