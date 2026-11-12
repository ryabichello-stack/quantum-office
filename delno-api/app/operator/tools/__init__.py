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
from app.operator.tools.calls import (
    CallsDialTool,
    CallsGetTool,
    CallsJobsTool,
    CallsListTool,
    PhonesListTool,
    PhonesProvisionTool,
)
from app.operator.tools.hermes import (
    HermesAlertsTool,
    HermesHealthTool,
    HermesSetupMarkTool,
    HermesSetupStatusTool,
)
from app.operator.tools.office_setup import (
    CredentialsOpenFormTool,
    FilesCloudListTool,
    FilesCloudStatusTool,
    TelephonyScriptGetTool,
    TelephonyScriptProposeTool,
    TelephonyScriptSaveTool,
    TelephonyToolsSetTool,
)
from app.operator.tools.billing_tools import BillingSummaryTool
from app.operator.tools.web import WebBrowseTool, WebFetchTool, WebSearchTool
from app.operator.tools.website_import_tool import OfficeImportWebsiteTool
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
    # Office OS telephony + Hermes supervisor
    registry.register(CallsListTool())
    registry.register(CallsGetTool())
    registry.register(CallsDialTool())
    registry.register(CallsJobsTool())
    registry.register(PhonesListTool())
    registry.register(PhonesProvisionTool())
    registry.register(HermesSetupStatusTool())
    registry.register(HermesSetupMarkTool())
    registry.register(HermesHealthTool())
    registry.register(HermesAlertsTool())
    # Telephony script + cloud disks + secure forms (agent-callable)
    registry.register(TelephonyScriptGetTool())
    registry.register(TelephonyScriptProposeTool())
    registry.register(TelephonyScriptSaveTool())
    registry.register(TelephonyToolsSetTool())
    registry.register(FilesCloudStatusTool())
    registry.register(FilesCloudListTool())
    registry.register(CredentialsOpenFormTool())
    # Hermes browser / web
    registry.register(WebSearchTool())
    registry.register(WebFetchTool())
    registry.register(WebBrowseTool())
    registry.register(OfficeImportWebsiteTool())
    registry.register(BillingSummaryTool())
