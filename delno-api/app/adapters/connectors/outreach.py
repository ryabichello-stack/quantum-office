"""Outreach connector — cold email staging without SMTP until OUTREACH_BASE_URL."""

from __future__ import annotations

from typing import Any

from app.adapters.connectors.base import ConnectorResult
from app.adapters.connectors.http_client import get_json, post_json
from app.core.config import get_settings

STUB_PACKS = [
    {
        "id": "b2b-intro",
        "title": "B2B intro",
        "subject": "Коротко про {{company}} и DELNO",
        "steps": 3,
    },
    {
        "id": "follow-up",
        "title": "Follow-up after reply",
        "subject": "Продолжаем разговор",
        "steps": 2,
    },
    {
        "id": "lombards",
        "title": "Ломбарды (pack stub)",
        "subject": "По выплатам и автоматизации",
        "steps": 4,
    },
]


class OutreachConnector:
    kind = "outreach"

    def _base(self, config: dict[str, Any]) -> str:
        return str(config.get("base_url") or get_settings().outreach_base_url or "").strip()

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
                message="Outreach surface ready; set base_url / OUTREACH_BASE_URL later",
                data={
                    "enabled": enabled,
                    "tenant_slug": tenant_slug,
                    "capabilities": ["status", "dashboard", "preview", "stage_send", "packs", "lead_check"],
                    "stub_packs": len(STUB_PACKS),
                },
            )
        return ConnectorResult(
            ok=True,
            configured=True,
            kind=self.kind,
            message="Outreach upstream configured",
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
                message="Outreach upstream not configured (tools-first stub)",
                data={"tenant_slug": tenant_slug},
            )
        code, body, err = get_json(base, "/health", token=self._token(config))
        if err or code == 0:
            return ConnectorResult(
                ok=False, configured=True, kind=self.kind, error="unreachable", message=err or "unreachable"
            )
        return ConnectorResult(
            ok=True,
            configured=True,
            kind=self.kind,
            message="Outreach health ok",
            data={"health": body or {}, "status_code": code},
        )

    def dashboard(self, *, tenant_slug: str, config: dict[str, Any]) -> ConnectorResult:
        base = self._base(config)
        if not base:
            return ConnectorResult(
                ok=True,
                configured=False,
                kind=self.kind,
                message="Stub outreach dashboard (no SMTP / Bitrix yet)",
                data={
                    "stub": True,
                    "tenant_slug": tenant_slug,
                    "metrics": {
                        "outbox_pending": 0,
                        "sent_24h": 0,
                        "replies_24h": 0,
                        "bounces_24h": 0,
                        "paused": False,
                    },
                },
            )
        code, body, err = get_json(base, "/api/dashboard", token=self._token(config))
        if err:
            return ConnectorResult(ok=False, configured=True, kind=self.kind, error="dashboard_failed", message=err)
        return ConnectorResult(
            ok=True,
            configured=True,
            kind=self.kind,
            message="Outreach dashboard",
            data={"upstream": body or {}, "status_code": code},
        )

    def packs(self, *, tenant_slug: str, config: dict[str, Any]) -> ConnectorResult:
        base = self._base(config)
        if not base:
            return ConnectorResult(
                ok=True,
                configured=False,
                kind=self.kind,
                message="Stub industry packs (local catalog)",
                data={"stub": True, "tenant_slug": tenant_slug, "packs": STUB_PACKS},
            )
        code, body, err = get_json(base, "/api/packs", token=self._token(config))
        if err:
            return ConnectorResult(ok=False, configured=True, kind=self.kind, error="packs_failed", message=err)
        return ConnectorResult(
            ok=True,
            configured=True,
            kind=self.kind,
            message="Outreach packs",
            data={"upstream": body or {}, "status_code": code},
        )

    def preview(
        self,
        *,
        tenant_slug: str,
        config: dict[str, Any],
        to: str,
        company: str,
        pack_id: str | None = None,
        subject: str | None = None,
        body: str | None = None,
    ) -> ConnectorResult:
        base = self._base(config)
        pack = next((p for p in STUB_PACKS if p["id"] == (pack_id or "b2b-intro")), STUB_PACKS[0])
        rendered_subject = subject or str(pack["subject"]).replace("{{company}}", company or "компании")
        rendered_body = body or (
            f"Здравствуйте!\n\nПишем из DELNO по поводу {company or 'вашей компании'}.\n"
            f"(stub preview — SMTP не подключён)\n\n— {tenant_slug}"
        )
        if not base:
            return ConnectorResult(
                ok=True,
                configured=False,
                kind=self.kind,
                message="Stub email preview",
                data={
                    "stub": True,
                    "queued": False,
                    "to": to,
                    "company": company,
                    "pack_id": pack["id"],
                    "subject": rendered_subject,
                    "body": rendered_body,
                    "tenant_slug": tenant_slug,
                },
            )
        code, resp, err = post_json(
            base,
            "/api/preview",
            json={
                "to": to,
                "company": company,
                "pack_id": pack_id,
                "subject": subject,
                "body": body,
                "tenant_slug": tenant_slug,
            },
            token=self._token(config),
        )
        if err:
            return ConnectorResult(ok=False, configured=True, kind=self.kind, error="preview_failed", message=err)
        return ConnectorResult(
            ok=True,
            configured=True,
            kind=self.kind,
            message="Outreach preview",
            data={"upstream": resp or {}, "status_code": code},
        )

    def stage_send(
        self,
        *,
        tenant_slug: str,
        config: dict[str, Any],
        to: str,
        company: str,
        pack_id: str | None = None,
        subject: str | None = None,
        body: str | None = None,
        dry_run: bool = True,
    ) -> ConnectorResult:
        base = self._base(config)
        preview = self.preview(
            tenant_slug=tenant_slug,
            config=config,
            to=to,
            company=company,
            pack_id=pack_id,
            subject=subject,
            body=body,
        )
        if not base:
            return ConnectorResult(
                ok=True,
                configured=False,
                kind=self.kind,
                error="not_configured",
                message="Campaign staged locally; SMTP/outreach not wired (dry_run enforced)",
                data={
                    "stub": True,
                    "staged": True,
                    "sent": False,
                    "dry_run": True,
                    "tenant_slug": tenant_slug,
                    "preview": {
                        "to": to,
                        "company": company,
                        "pack_id": pack_id or "b2b-intro",
                        "subject": preview.data.get("subject"),
                        "body_preview": str(preview.data.get("body") or "")[:240],
                    },
                },
            )
        code, resp, err = post_json(
            base,
            "/api/send-one",
            json={
                "to": to,
                "company": company,
                "pack_id": pack_id,
                "subject": subject,
                "body": body,
                "dry_run": dry_run,
                "tenant_slug": tenant_slug,
            },
            token=self._token(config),
        )
        if err:
            return ConnectorResult(ok=False, configured=True, kind=self.kind, error="send_failed", message=err)
        return ConnectorResult(
            ok=True,
            configured=True,
            kind=self.kind,
            message="Outreach send staged/sent via upstream",
            data={"upstream": resp or {}, "status_code": code, "dry_run": dry_run},
        )

    def lead_check(
        self,
        *,
        tenant_slug: str,
        config: dict[str, Any],
        email: str | None = None,
        company: str | None = None,
    ) -> ConnectorResult:
        base = self._base(config)
        if not base:
            return ConnectorResult(
                ok=True,
                configured=False,
                kind=self.kind,
                message="Stub lead_check — no Bitrix mirror yet; treat as unknown",
                data={
                    "stub": True,
                    "tenant_slug": tenant_slug,
                    "email": email,
                    "company": company,
                    "in_bitrix": False,
                    "in_outbox": False,
                    "duplicate": False,
                    "recommendation": "ok_to_stage",
                },
            )
        code, resp, err = post_json(
            base,
            "/api/lead-check",
            json={"email": email, "company": company, "tenant_slug": tenant_slug},
            token=self._token(config),
        )
        if err:
            return ConnectorResult(ok=False, configured=True, kind=self.kind, error="lead_check_failed", message=err)
        return ConnectorResult(
            ok=True,
            configured=True,
            kind=self.kind,
            message="Outreach lead_check",
            data={"upstream": resp or {}, "status_code": code},
        )
