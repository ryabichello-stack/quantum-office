from __future__ import annotations

from typing import Any

from app.adapters.connectors.base import ConnectorResult
from app.adapters.connectors.http_client import get_json, post_json
from app.core.config import get_settings


class ConferenceConnector:
    kind = "conference"

    def _base(self, config: dict[str, Any]) -> str:
        return str(config.get("base_url") or get_settings().conference_base_url or "").strip()

    def _token(self, config: dict[str, Any]) -> str | None:
        return (str(config.get("webhook_token") or get_settings().office_webhook_token or "").strip() or None)

    def status(self, *, tenant_slug: str, config: dict[str, Any]) -> ConnectorResult:
        base = self._base(config)
        enabled = bool(config.get("enabled", False))
        if not base:
            return ConnectorResult(
                ok=True,
                configured=False,
                kind=self.kind,
                message="Conference connector surface ready; set CONFERENCE_BASE_URL later",
                data={
                    "enabled": enabled,
                    "tenant_slug": tenant_slug,
                    "capabilities": ["create", "invite"],
                    "providers": ["yandex", "google_meet", "zoom", "teams", "jitsi"],
                },
            )
        return ConnectorResult(
            ok=True,
            configured=True,
            kind=self.kind,
            message="Conference upstream configured",
            data={
                "enabled": enabled,
                "base_url": base,
                "tenant_slug": tenant_slug,
                "providers": ["yandex", "google_meet", "zoom", "teams", "jitsi"],
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
                message="Conference upstream not configured (tools-first stub)",
                data={"tenant_slug": tenant_slug},
            )
        code, body, err = get_json(base, "/health", token=self._token(config))
        if err or code == 0:
            return ConnectorResult(ok=False, configured=True, kind=self.kind, error="unreachable", message=err or "unreachable")
        return ConnectorResult(
            ok=True,
            configured=True,
            kind=self.kind,
            message="Conference health ok",
            data={"health": body or {}, "status_code": code},
        )

    def create(
        self,
        *,
        tenant_slug: str,
        config: dict[str, Any],
        title: str,
        invitees: list[str] | None = None,
        when_text: str = "",
        provider: str = "yandex",
    ) -> ConnectorResult:
        base = self._base(config)
        title = (title or "").strip() or "Встреча DELNO"
        provider = (provider or "yandex").strip().lower() or "yandex"
        if not base:
            return ConnectorResult(
                ok=False,
                configured=False,
                kind=self.kind,
                error="not_configured",
                message="Сервис видеовстреч недоступен; ссылка не создана",
                data={
                    "provider": provider,
                    "title": title,
                    "tenant_slug": tenant_slug,
                },
            )
        access = config.get("_conference_delivery_access")
        if not isinstance(access, dict) or not access.get("tenant_id") or access.get("provider") != provider or (provider != "jitsi" and not access.get("token")):
            return ConnectorResult(ok=False, configured=True, kind=self.kind, error="conference_not_connected", message="Видеовстречи этой компании не подключены")
        code, resp, err = post_json(
            base,
            "/api/conferences",
            json={
                "title": title,
                "tenant_id": access["tenant_id"],
                "access_token": access.get("token") or "",
                "provider": provider,
                "invitees": invitees or [],
                "when_text": when_text,
                "send_invites": False,
            },
            token=self._token(config),
            headers={"X-Tenant-Id": access["tenant_id"]},
        )
        if err:
            return ConnectorResult(ok=False, configured=True, kind=self.kind, error="create_failed", message=err)
        upstream = resp or {}
        if not upstream.get("ok") or upstream.get("stub") or not upstream.get("join_url"):
            return ConnectorResult(ok=False, configured=True, kind=self.kind, error="create_failed", message=str(upstream.get("message") or "Видеовстреча не создана"))
        return ConnectorResult(
            ok=True,
            configured=True,
            kind=self.kind,
            message=str(upstream.get("message") or "Conference created"),
            data={
                "upstream": upstream,
                "status_code": code,
                "provider": upstream.get("provider") or provider,
                "stub": bool(upstream.get("stub")),
                "join_url": upstream.get("join_url") or "",
            },
        )
