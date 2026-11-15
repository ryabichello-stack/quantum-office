from __future__ import annotations

from typing import Any

from app.adapters.connectors.base import ConnectorResult
from app.adapters.connectors.http_client import get_json, post_json
from app.core.config import get_settings


class CalendarConnector:
    kind = "calendar"

    def _base(self, config: dict[str, Any]) -> str:
        return str(config.get("base_url") or get_settings().calendar_base_url or "").strip()

    def _token(self, config: dict[str, Any]) -> str | None:
        return (str(config.get("webhook_token") or get_settings().office_webhook_token or "").strip() or None)

    def _with_access(self, config: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        out = dict(payload)
        tenant_id = str(config.get("_tenant_id") or "").strip()
        if tenant_id:
            out["tenant_id"] = tenant_id
        creds = config.get("_request_credentials")
        merged: dict[str, Any] = dict(creds) if isinstance(creds, dict) else {}
        if config.get("_allow_env_fallback"):
            merged["allow_env_fallback"] = True
            out["allow_env_fallback"] = True
        if merged:
            out["credentials"] = merged
        return out

    def status(self, *, tenant_slug: str, config: dict[str, Any]) -> ConnectorResult:
        base = self._base(config)
        enabled = bool(config.get("enabled", False))
        if not base:
            return ConnectorResult(
                ok=True,
                configured=False,
                kind=self.kind,
                message="Calendar connector surface ready; set CALENDAR_BASE_URL later",
                data={
                    "enabled": enabled,
                    "tenant_slug": tenant_slug,
                    "capabilities": ["check", "suggest", "create", "providers"],
                    "sources": ["mailru", "yandex", "google", "outlook"],
                    "creds_policy": "tools_first",
                },
            )
        return ConnectorResult(
            ok=True,
            configured=True,
            kind=self.kind,
            message="Calendar upstream configured",
            data={
                "enabled": enabled,
                "base_url": base,
                "tenant_slug": tenant_slug,
                "sources": ["mailru", "yandex", "google", "outlook"],
            },
        )

    def probe(self, *, tenant_slug: str, config: dict[str, Any]) -> ConnectorResult:
        base = self._base(config)
        if not base:
            return ConnectorResult(
                ok=True,
                configured=False,
                kind=self.kind,
                error="not_configured",
                message="Calendar upstream not configured (tools-first stub)",
                data={"tenant_slug": tenant_slug},
            )
        code, body, err = get_json(base, "/health", token=self._token(config))
        if err or code == 0:
            return ConnectorResult(ok=False, configured=True, kind=self.kind, error="unreachable", message=err or "unreachable")
        return ConnectorResult(
            ok=True,
            configured=True,
            kind=self.kind,
            message="Calendar health ok",
            data={"health": body or {}, "status_code": code},
        )

    def suggest_slots(
        self,
        *,
        tenant_slug: str,
        config: dict[str, Any],
        start: str,
        duration_min: int = 60,
        source: str | None = None,
    ) -> ConnectorResult:
        base = self._base(config)
        source = (source or str(config.get("default_source") or "mailru")).strip() or "mailru"
        if not base:
            # Deterministic stub slots so operator/Hermes can rehearse without CalDAV.
            stub = [
                {
                    "start": start,
                    "label": f"{start} (stub:{source})",
                    "duration_min": duration_min,
                    "source": source,
                    "stub": True,
                },
            ]
            return ConnectorResult(
                ok=True,
                configured=False,
                kind=self.kind,
                error="not_configured",
                message="Stub suggestions — wire CALENDAR_BASE_URL for live providers",
                data={
                    "suggestions": stub,
                    "count": 1,
                    "stub": True,
                    "source": source,
                    "tenant_slug": tenant_slug,
                },
            )
        payload = self._with_access(
            config,
            {
                "start": start,
                "duration_min": duration_min,
                "source": source,
                "tenant_slug": tenant_slug,
            },
        )
        code, resp, err = post_json(
            base,
            "/api/calendar/suggest",
            json=payload,
            token=self._token(config),
        )
        if err:
            return ConnectorResult(ok=False, configured=True, kind=self.kind, error="suggest_failed", message=err)
        upstream = resp if isinstance(resp, dict) else {}
        suggestions = (
            upstream.get("suggestions")
            or upstream.get("slots")
            or upstream.get("items")
            or []
        )
        if not isinstance(suggestions, list):
            suggestions = []
        return ConnectorResult(
            ok=True,
            configured=True,
            kind=self.kind,
            message="Calendar suggestions",
            data={
                "upstream": upstream,
                "status_code": code,
                "source": source,
                "suggestions": suggestions,
                "count": len(suggestions),
                "stub": bool(upstream.get("stub")),
            },
        )

    def check(
        self,
        *,
        tenant_slug: str,
        config: dict[str, Any],
        start: str,
        timezone: str | None = None,
        source: str | None = None,
    ) -> ConnectorResult:
        base = self._base(config)
        source = (source or str(config.get("default_source") or "mailru")).strip() or "mailru"
        payload = self._with_access(
            config,
            {
                "start": start,
                "source": source,
                "tenant_slug": tenant_slug,
            },
        )
        if timezone:
            payload["timezone"] = timezone
        if not base:
            return ConnectorResult(
                ok=True,
                configured=False,
                kind=self.kind,
                message="Stub check — wire CALENDAR_BASE_URL for live providers",
                data={"free": True, "stub": True, "start": start, "source": source},
            )
        code, resp, err = post_json(base, "/api/calendar/check", json=payload, token=self._token(config))
        if err:
            return ConnectorResult(ok=False, configured=True, kind=self.kind, error="check_failed", message=err)
        upstream = resp if isinstance(resp, dict) else {}
        return ConnectorResult(
            ok=True,
            configured=True,
            kind=self.kind,
            message="Calendar check",
            data={"upstream": upstream, "status_code": code, "stub": bool(upstream.get("stub")), **upstream},
        )

    def create_event(
        self,
        *,
        tenant_slug: str,
        config: dict[str, Any],
        start: str,
        summary: str,
        description: str | None = None,
        attendee_email: str | None = None,
        timezone: str | None = None,
        end: str | None = None,
        source: str | None = None,
        create_telemost: bool | None = None,
        invitees: list[Any] | None = None,
    ) -> ConnectorResult:
        base = self._base(config)
        source = (source or str(config.get("default_source") or "mailru")).strip() or "mailru"
        payload = self._with_access(
            config,
            {
                "start": start,
                "summary": summary,
                "source": source,
                "tenant_slug": tenant_slug,
            },
        )
        if description:
            payload["description"] = description
        if attendee_email:
            payload["attendee_email"] = attendee_email
        if timezone:
            payload["timezone"] = timezone
        if end:
            payload["end"] = end
        if create_telemost is not None:
            payload["create_telemost"] = bool(create_telemost)
        if invitees:
            payload["invitees"] = invitees
        if not base:
            return ConnectorResult(
                ok=True,
                configured=False,
                kind=self.kind,
                message="Stub booking — wire CALENDAR_BASE_URL for live create",
                data={"created": True, "stub": True, **payload},
            )
        code, resp, err = post_json(base, "/api/calendar/create", json=payload, token=self._token(config))
        if err:
            return ConnectorResult(ok=False, configured=True, kind=self.kind, error="create_failed", message=err)
        upstream = resp if isinstance(resp, dict) else {}
        return ConnectorResult(
            ok=bool(upstream.get("ok", True)),
            configured=True,
            kind=self.kind,
            message=str(upstream.get("message") or "Calendar create"),
            data={"upstream": upstream, "status_code": code, "stub": bool(upstream.get("stub")), **upstream},
        )
