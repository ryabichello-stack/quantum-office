import uuid

from app.core.tenant import TenantContext
from app.operator.tools.registry import ToolRegistry, tool_confirmation_class, requires_confirmation
from app.operator.tools.builtin import CreateLeadTool, GetKnowledgeTool, GetTenantSummaryTool


class _FakeAdapter:
    def search(self, query: str, *, tenant_slug: str, principal_id: str, limit: int = 5, mode: str = "hybrid") -> dict:
        return {"results": [{"text": f"Answer for {query}", "principal": principal_id}]}


def test_tool_registry_register_and_list():
    reg = ToolRegistry()
    tool = GetKnowledgeTool(_FakeAdapter())
    reg.register(tool)
    assert reg.get("get_knowledge") is tool
    specs = reg.list_openai_specs()
    assert specs[0]["function"]["name"] == "get_knowledge"


def test_tenant_context_frozen():
    ctx = TenantContext(tenant_id=uuid.uuid4(), tenant_slug="demo")
    assert ctx.tenant_slug == "demo"


def test_tool_confirmation_classes():
    assert tool_confirmation_class(GetTenantSummaryTool()) == "READ"
    assert requires_confirmation(GetTenantSummaryTool()) is False
    assert tool_confirmation_class(CreateLeadTool()) == "HIGH_IMPACT"
    assert requires_confirmation(CreateLeadTool()) is True


def test_list_openai_specs_filtered():
    reg = ToolRegistry()
    reg.register(GetKnowledgeTool(_FakeAdapter()))
    reg.register(GetTenantSummaryTool())
    specs = reg.list_openai_specs(names=["get_tenant_summary"])
    assert len(specs) == 1
    assert specs[0]["function"]["name"] == "get_tenant_summary"
