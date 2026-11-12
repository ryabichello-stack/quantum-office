"""Bridge: register archived Quantum Office MCP tools into DELNO ToolRegistry.

Source of truth: `third_party/quantum_office_mcp` (restored from office-mcp @ 9f715c4).
Calls live QO brokers (console/outreach/text-bot/…) — not AVA in-call MCP.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, ClassVar

from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.operator.tools.registry import ToolResult, registry

logger = logging.getLogger(__name__)

_THIRD_PARTY = Path(__file__).resolve().parents[3] / "third_party"
if _THIRD_PARTY.is_dir() and str(_THIRD_PARTY) not in sys.path:
    sys.path.insert(0, str(_THIRD_PARTY))

# Alias-only names from the old catalog — DELNO already has tenant-scoped
# equivalents (calls.*, etc.). Skip so we do not overwrite.
_SKIP_NAMES = frozenset(
    {
        "calls.dial",
        "calls.assign_task",
        "calls.list",
        "calls.get",
        "line.get",
        "line.set",
        "office.health",  # provided by mcp_gateway meta / hermes
    }
)

_HIGH_IMPACT = frozenset(
    {
        "telephony.dial",
        "telephony.assign_task",
        "telephony.callback",
        "telephony.inbound_line_set",
        "telephony.scenario_set",
        "campaign.start",
        "campaign.stop",
        "campaign.set_script",
        "messenger.send",
        "telegram.send",
        "max.send",
        "outreach.send_one",
        "outreach.send_batch",
        "outreach.outbox_set_status",
        "outreach.settings_set",
        "outreach.pack_apply",
        "outreach.rebuild_outbox",
        "outreach.leads_import",
        "mail.send",
        "mailru.send",
        "mailru.upload",
        "files.send",
        "files.upload",
        "calendar.create",
        "conference.create",
        "crm.company_upsert",
        "crm.lifecycle_set",
    }
)

# Hermes cabinet allowlist = full QO MCP surface (minus aliases / meta).
# Use a list so importers that bind the name still see updates via this object.
QO_MCP_CABINET_TOOLS: list[str] = []


def qo_mcp_cabinet_tools() -> tuple[str, ...]:
    return tuple(QO_MCP_CABINET_TOOLS)


def _ensure_qo_env() -> None:
    """Map DELNO/QO env so archived client.py finds brokers + tokens."""
    defaults = {
        "CONSOLE_BASE": "http://qo-console:8013",
        "OUTREACH_BASE": "http://qo-outreach:8012",
        "TEXT_BOT_BASE": "http://qo-text-bot:8011",
        "AVA_KNOWLEDGE_BASE": "http://qo-knowledge:8017",
        "KNOWLEDGE_BASE": "http://qo-knowledge:8017",
        "CALENDAR_BASE": "http://qo-calendar:8014",
        "FILES_BASE": "http://qo-files:8015",
        "CONFERENCE_BASE": "http://qo-conference:8016",
        "MAILER_BASE": "http://qo-mailer:8000",
        "CAMPAIGN_BASE": "http://host.docker.internal:8018",
    }
    # Prefer explicit QO_* / already-set; else docker DNS defaults for Cloud4Box.
    for key, default in defaults.items():
        if not (os.getenv(key) or "").strip():
            os.environ[key] = default

    # Token aliases (values must already be in process env — never hardcode).
    if not (os.getenv("CONSOLE_TOKEN") or "").strip():
        for alt in ("QO_CONSOLE_TOKEN", "OFFICE_CONSOLE_TOKEN"):
            if (os.getenv(alt) or "").strip():
                os.environ["CONSOLE_TOKEN"] = os.environ[alt]
                break
    if not (os.getenv("WEBHOOK_TOKEN") or "").strip():
        for alt in ("OFFICE_WEBHOOK_TOKEN", "QO_WEBHOOK_TOKEN"):
            if (os.getenv(alt) or "").strip():
                os.environ["WEBHOOK_TOKEN"] = os.environ[alt]
                break
    if not (os.getenv("OUTREACH_UI_TOKEN") or "").strip():
        for alt in ("OUTREACH_TOKEN", "QO_OUTREACH_UI_TOKEN"):
            if (os.getenv(alt) or "").strip():
                os.environ["OUTREACH_UI_TOKEN"] = os.environ[alt]
                break

    # Bypass OpenAI egress proxy for internal QO hostnames.
    no_proxy = os.getenv("NO_PROXY") or os.getenv("no_proxy") or ""
    extra = (
        "qo-console,qo-outreach,qo-text-bot,qo-knowledge,qo-calendar,"
        "qo-files,qo-conference,qo-mailer,console,outreach,text-bot,"
        "knowledge,calendar,files,conference,mailer,host.docker.internal"
    )
    merged = ",".join(x for x in (no_proxy, extra) if x)
    os.environ["NO_PROXY"] = merged
    os.environ["no_proxy"] = merged


def _unwrap_handler_result(raw: dict[str, Any]) -> ToolResult:
    """office-mcp handlers return MCP content blocks; flatten for Hermes."""
    is_error = bool(raw.get("isError"))
    payload: Any = raw
    content = raw.get("content")
    if isinstance(content, list) and content:
        text = content[0].get("text") if isinstance(content[0], dict) else None
        if isinstance(text, str):
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                payload = {"raw": text[:8000]}
    if isinstance(payload, dict):
        ok = bool(payload.get("ok", not is_error))
        message = str(payload.get("message") or payload.get("error") or "")[:500]
        return ToolResult(ok=ok and not is_error, data=payload, message=message)
    return ToolResult(ok=not is_error, data={"result": payload}, message="")


class _QoMcpTool:
    """One archived MCP tool as a DELNO registry Tool."""

    critical_write: ClassVar[bool] = False

    def __init__(self, name: str, description: str, parameters_schema: dict[str, Any]):
        self.name = name
        self.description = description
        self.parameters_schema = parameters_schema or {"type": "object", "properties": {}}
        self.critical_write = name in _HIGH_IMPACT

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        _ensure_qo_env()
        # Force urllib to honor updated NO_PROXY for this process.
        try:
            from quantum_office_mcp.handlers import call_tool
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, message=f"qo_mcp_import_failed: {exc}", data={})
        try:
            raw = call_tool(self.name, params)
        except Exception as exc:  # noqa: BLE001
            logger.exception("qo mcp tool %s failed", self.name)
            return ToolResult(ok=False, message=str(exc), data={"tool": self.name})
        result = _unwrap_handler_result(raw if isinstance(raw, dict) else {"raw": raw})
        result.data.setdefault("tenant_slug", ctx.tenant_slug)
        result.data.setdefault("source", "quantum_office_mcp")
        return result


def register_qo_mcp_tools(*, overwrite: bool = False) -> list[str]:
    """Register archived office-mcp tools. Returns names newly registered."""
    _ensure_qo_env()
    try:
        from quantum_office_mcp.tools import TOOLS
    except Exception as exc:  # noqa: BLE001
        logger.warning("quantum_office_mcp not available: %s", exc)
        QO_MCP_CABINET_TOOLS.clear()
        return []

    registered: list[str] = []
    for spec in TOOLS:
        name = str(spec.get("name") or "").strip()
        if not name or name in _SKIP_NAMES:
            continue
        if registry.get(name) is not None and not overwrite:
            continue
        tool = _QoMcpTool(
            name=name,
            description=str(spec.get("description") or name),
            parameters_schema=spec.get("inputSchema") or {"type": "object", "properties": {}},
        )
        registry.register(tool)
        registered.append(name)

    # Stable cabinet list: every registered QO MCP tool name currently in registry
    # that comes from this catalog (including ones that already existed).
    catalog_names = [
        str(s.get("name") or "").strip()
        for s in TOOLS
        if str(s.get("name") or "").strip() and str(s.get("name")).strip() not in _SKIP_NAMES
    ]
    QO_MCP_CABINET_TOOLS.clear()
    QO_MCP_CABINET_TOOLS.extend(n for n in catalog_names if registry.get(n) is not None)
    logger.info("qo_mcp_bridge registered=%s cabinet=%s", len(registered), len(QO_MCP_CABINET_TOOLS))
    return registered
