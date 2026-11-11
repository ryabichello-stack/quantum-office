from __future__ import annotations

from typing import Any

from app.adapters.connectors.base import ConnectorResult
from app.adapters.connectors.http_client import get_json, post_json
from app.core.config import get_settings


class MailConnector:
    kind = "mail"

    def _base(self, config: dict[str, Any]) -> str:
        return str(config.get("base_url") or get_settings().mailer_base_url or "").strip()

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
                message="Mail connector surface ready; set base_url / MAILER_BASE_URL later",
                data={"enabled": enabled, "tenant_slug": tenant_slug, "capabilities": ["send_draft", "health"]},
            )
        return ConnectorResult(
            ok=True,
            configured=True,
            kind=self.kind,
            message="Mail upstream configured",
            data={"enabled": enabled, "base_url": base, "tenant_slug": tenant_slug},
        )

    def probe(self, *, tenant_slug: str, config: dict[str, Any]) -> ConnectorResult:
        base = self._base(config)
        if not base:
            return ConnectorResult(
                ok=True,
                configured=False,
                kind=self.kind,
                error="not_configured",
                message="Mail upstream not configured (tools-first stub)",
                data={"tenant_slug": tenant_slug},
            )
        code, body, err = get_json(base, "/health", token=self._token(config))
        if err or code == 0:
            return ConnectorResult(ok=False, configured=True, kind=self.kind, error="unreachable", message=err or "unreachable")
        return ConnectorResult(
            ok=True,
            configured=True,
            kind=self.kind,
            message="Mail health ok",
            data={"health": body or {}, "status_code": code},
        )

    def send_draft(
        self,
        *,
        tenant_slug: str,
        config: dict[str, Any],
        to: str,
        subject: str,
        body: str,
    ) -> ConnectorResult:
        base = self._base(config)
        if not base:
            return ConnectorResult(
                ok=True,
                configured=False,
                kind=self.kind,
                error="not_configured",
                message="Draft accepted locally; mailer not wired yet",
                data={
                    "queued": False,
                    "stub": True,
                    "to": to,
                    "subject": subject[:200],
                    "body_preview": body[:240],
                    "tenant_slug": tenant_slug,
                },
            )
        code, resp, err = post_json(
            base,
            "/api/mail/send",
            json={"to": to, "subject": subject, "body": body, "tenant_slug": tenant_slug},
            token=self._token(config),
        )
        if err:
            return ConnectorResult(ok=False, configured=True, kind=self.kind, error="send_failed", message=err)
        return ConnectorResult(
            ok=True,
            configured=True,
            kind=self.kind,
            message="Mail sent via upstream",
            data={"upstream": resp or {}, "status_code": code},
        )
