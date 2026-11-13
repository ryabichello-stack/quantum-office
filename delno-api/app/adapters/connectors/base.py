"""Office connector contract — mail / calendar / files / conference.

Tools-first: adapters always exist. Without base URL or tenant creds they
return structured `not_configured` / stub payloads instead of raising.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

CONNECTOR_KINDS = ("mail", "calendar", "files", "conference", "outreach")


@dataclass(slots=True)
class ConnectorResult:
    ok: bool
    configured: bool
    kind: str
    data: dict[str, Any] = field(default_factory=dict)
    message: str = ""
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        out = {
            "ok": self.ok,
            "configured": self.configured,
            "kind": self.kind,
            "message": self.message,
            **self.data,
        }
        if self.error:
            out["error"] = self.error
        return out


class OfficeConnector(Protocol):
    kind: str

    def status(self, *, tenant_slug: str, config: dict[str, Any]) -> ConnectorResult: ...

    def probe(self, *, tenant_slug: str, config: dict[str, Any]) -> ConnectorResult: ...
