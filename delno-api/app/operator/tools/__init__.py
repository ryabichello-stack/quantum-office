from app.adapters.knowledge import KnowledgeAdapter
from app.operator.tools.builtin import CreateLeadTool, GetKnowledgeTool, LookupCompanyByInnTool
from app.operator.tools.registry import registry


def register_builtin_tools() -> None:
    registry.register(GetKnowledgeTool(KnowledgeAdapter()))
    registry.register(LookupCompanyByInnTool())
    registry.register(CreateLeadTool())
