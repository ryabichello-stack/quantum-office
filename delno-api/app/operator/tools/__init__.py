from app.adapters.knowledge import KnowledgeAdapter
from app.operator.tools.builtin import (
    CreateLeadTool,
    GetKnowledgeTool,
    GetTenantSummaryTool,
    LookupCompanyByInnTool,
    SetFeatureFlagTool,
    UpdateTenantSettingsTool,
    UploadKnowledgeSnippetTool,
)
from app.operator.tools.crm import (
    CrmCompaniesTool,
    CrmCompanyUpsertTool,
    CrmFunnelTool,
    CrmLeadGetTool,
    CrmLeadsTool,
    CrmLifecycleSetTool,
    CrmSuggestNextTool,
)
from app.operator.tools.office import (
    CreateConferenceTool,
    ListFilesTool,
    SendMailDraftTool,
    SuggestCalendarSlotsTool,
)
from app.operator.tools.outreach import (
    OutreachDashboardTool,
    OutreachLeadCheckTool,
    OutreachPacksTool,
    OutreachPreviewTool,
    OutreachStageSendTool,
    OutreachStatusTool,
)
from app.operator.tools.registry import registry


def register_builtin_tools() -> None:
    registry.register(GetKnowledgeTool(KnowledgeAdapter()))
    registry.register(LookupCompanyByInnTool())
    registry.register(CreateLeadTool())
    registry.register(GetTenantSummaryTool())
    registry.register(UpdateTenantSettingsTool())
    registry.register(UploadKnowledgeSnippetTool())
    registry.register(SetFeatureFlagTool())
    # Office connectors (tools-first stubs)
    registry.register(SuggestCalendarSlotsTool())
    registry.register(SendMailDraftTool())
    registry.register(ListFilesTool())
    registry.register(CreateConferenceTool())
    # CRM-lite (local leads funnel)
    registry.register(CrmFunnelTool())
    registry.register(CrmLeadsTool())
    registry.register(CrmLeadGetTool())
    registry.register(CrmCompaniesTool())
    registry.register(CrmCompanyUpsertTool())
    registry.register(CrmLifecycleSetTool())
    registry.register(CrmSuggestNextTool())
    # Outreach staging (stub until OUTREACH_BASE_URL)
    registry.register(OutreachStatusTool())
    registry.register(OutreachDashboardTool())
    registry.register(OutreachPacksTool())
    registry.register(OutreachPreviewTool())
    registry.register(OutreachStageSendTool())
    registry.register(OutreachLeadCheckTool())
