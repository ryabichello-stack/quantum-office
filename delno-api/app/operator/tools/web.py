"""Hermes web search / fetch / browse tools."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.operator.tools.registry import ToolResult
from app.services import billing, web_browser
from app.services.audit import write_audit


class WebSearchTool:
    name = "web.search"
    description = (
        "Search the PUBLIC internet (DuckDuckGo). "
        "Use for open-web research, laws, news, third-party sites — NOT tenant KB. "
        "After results, call web.fetch/web.browse on the best URLs before answering."
    )
    critical_write = False
    parameters_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer", "default": 5},
        },
        "required": ["query"],
    }

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        query = str(params.get("query") or "").strip()
        limit = int(params.get("limit") or 5)
        out = web_browser.search_web(query, limit=limit)
        if out.get("ok"):
            billing.record_web_usage(db, ctx, kind="search")
            write_audit(db, ctx, action="tool.web.search", resource="web", new_value={"query": query})
            lines = [f"Поиск: {query}"]
            for i, item in enumerate(out.get("items") or [], 1):
                lines.append(f"{i}. {item.get('title')} — {item.get('url')}")
            if len(lines) == 1:
                lines.append("Ничего не найдено.")
            return ToolResult(ok=True, data=out, message="\n".join(lines))
        err = out.get("error") or "search_failed"
        detail = out.get("detail")
        msg = f"{err}" + (f": {detail}" if detail else "")
        return ToolResult(ok=False, data=out, message=msg)


class WebFetchTool:
    name = "web.fetch"
    description = "Fetch a URL and return readable text (HTML→text). For any public page."
    critical_write = False
    parameters_schema = {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "max_chars": {"type": "integer", "default": 12000},
        },
        "required": ["url"],
    }

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        url = str(params.get("url") or "").strip()
        max_chars = int(params.get("max_chars") or 12000)
        out = web_browser.fetch_url(url, max_chars=max_chars)
        if out.get("ok"):
            billing.record_web_usage(db, ctx, kind="fetch")
            title = out.get("title") or url
            preview = (out.get("text") or "")[:1500]
            return ToolResult(
                ok=True,
                data=out,
                message=f"Страница «{title}» ({out.get('chars', 0)} симв.)\n{preview}",
            )
        err = out.get("error") or "fetch_failed"
        detail = out.get("detail")
        msg = f"{err}" + (f": {detail}" if detail else "")
        return ToolResult(ok=False, data=out, message=msg)


class WebBrowseTool:
    name = "web.browse"
    description = (
        "Browse a page with Hermes browser (Playwright headless when available, else HTTP fetch). "
        "Use for JS-heavy sites after web.fetch is insufficient."
    )
    critical_write = False
    parameters_schema = {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "max_chars": {"type": "integer", "default": 12000},
        },
        "required": ["url"],
    }

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        url = str(params.get("url") or "").strip()
        max_chars = int(params.get("max_chars") or 12000)
        out = web_browser.browse_page(url, max_chars=max_chars)
        if out.get("ok"):
            billing.record_web_usage(db, ctx, kind="browse")
            title = out.get("title") or url
            preview = (out.get("text") or "")[:1500]
            engine = out.get("engine") or "unknown"
            return ToolResult(
                ok=True,
                data=out,
                message=f"Браузер ({engine}): «{title}»\n{preview}",
            )
        err = out.get("error") or "browse_failed"
        detail = out.get("detail") or out.get("playwright_error")
        msg = f"{err}" + (f": {detail}" if detail else "")
        return ToolResult(ok=False, data=out, message=msg)
