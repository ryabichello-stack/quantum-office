from dataclasses import dataclass, field
from typing import Any, Protocol

from sqlalchemy.orm import Session

from app.core.tenant import TenantContext


@dataclass(slots=True)
class ToolResult:
    ok: bool
    data: dict[str, Any] = field(default_factory=dict)
    message: str = ""


@dataclass(slots=True)
class PendingConfirmation:
    """Critical write blocked until user confirms (voice or text)."""

    confirmation_id: str
    tool_name: str
    summary: str
    payload: dict[str, Any]


class Tool(Protocol):
    name: str
    description: str
    critical_write: bool

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult | PendingConfirmation: ...


CONFIRMATION_READ = "READ"
CONFIRMATION_SAFE_WRITE = "SAFE_WRITE"
CONFIRMATION_HIGH_IMPACT = "HIGH_IMPACT"

# Tools requiring explicit user confirm before execution in cabinet.
_HIGH_IMPACT_TOOLS = frozenset({"create_lead"})


def tool_confirmation_class(tool: Tool) -> str:
    if tool.name in _HIGH_IMPACT_TOOLS:
        return CONFIRMATION_HIGH_IMPACT
    if getattr(tool, "critical_write", False):
        return CONFIRMATION_SAFE_WRITE
    return CONFIRMATION_READ


def requires_confirmation(tool: Tool) -> bool:
    return tool_confirmation_class(tool) != CONFIRMATION_READ


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list_openai_specs(self, *, names: list[str] | None = None) -> list[dict[str, Any]]:
        specs: list[dict[str, Any]] = []
        for tool in self._tools.values():
            if names is not None and tool.name not in names:
                continue
            specs.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": getattr(tool, "parameters_schema", {"type": "object", "properties": {}}),
                    },
                }
            )
        return specs

    def run(self, db: Session, ctx: TenantContext, name: str, **params: Any) -> ToolResult | PendingConfirmation:
        tool = self.get(name)
        if not tool:
            return ToolResult(ok=False, message=f"Unknown tool: {name}")
        return tool.run(db, ctx, **params)


registry = ToolRegistry()
