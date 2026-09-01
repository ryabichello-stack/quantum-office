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


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list_openai_specs(self) -> list[dict[str, Any]]:
        specs: list[dict[str, Any]] = []
        for tool in self._tools.values():
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
