"""Default MCP tool grants by product phase (scoped run tokens)."""

from __future__ import annotations

# Always safe meta
META = ("office.health", "office.connectors", "hermes.profile")

# P1 — онбординг + KB
ONBOARDING_KB = META + (
    "hermes.setup_status",
    "hermes.capabilities",
    "hermes.health",
    "get_knowledge",
    "upload_knowledge_snippet",
    "office.import_website",
    "web.search",
    "web.fetch",
    "web.browse",
    "get_tenant_summary",
    "credentials.open_form",
)

# P2 — дирижирование office tools (write всё ещё через confirm в registry)
OFFICE_CONDUCT = ONBOARDING_KB + (
    "suggest_calendar_slots",
    "send_mail_draft",
    "list_files",
    "create_conference",
    "phones.list",
    "calls.list",
    "crm.funnel",
    "crm.lifecycle_set",
    "set_feature_flag",
    "update_tenant_settings",
    "billing.summary",
    "generate_image",
    "telephony.script_get",
    "telephony.tools_set",
    "files.cloud_status",
)

# P3 — задачи / outreach read
TASKS_AND_OUTREACH = OFFICE_CONDUCT + (
    "outreach.packs",
    "outreach.stage_send",
    "calls.dial",
    "calls.jobs",
    "phones.provision",
    "telephony.script_propose",
    "telephony.script_save",
)


def pack_for_mode(mode: str | None) -> list[str]:
    m = (mode or "onboarding").strip().lower()
    if m in ("conduct", "office", "p2"):
        return list(OFFICE_CONDUCT)
    if m in ("tasks", "p3", "full"):
        return list(TASKS_AND_OUTREACH)
    return list(ONBOARDING_KB)
