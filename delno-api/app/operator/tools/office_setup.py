"""Hermes tools for telephony script/tools and cloud disks — agent-callable."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.operator.tools.registry import ToolResult
from app.services import files_cloud, telephony_script
from app.services.tenant_vault import credential_form_spec


class TelephonyScriptGetTool:
    name = "telephony.script_get"
    description = (
        "Read the tenant inbound telephony secretary script and enabled in-call tools. "
        "Use when the owner asks about Ava/scenario/скрипт/тулзы на линии."
    )
    critical_write = False
    parameters_schema = {"type": "object", "properties": {}}

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        cfg = telephony_script.get_telephony_config(db, ctx)
        return ToolResult(
            ok=True,
            data=cfg,
            message=(
                "Сценарий сохранён."
                if cfg.get("configured")
                else "Сценария ещё нет — предложите черновик или сохраните текст."
            ),
        )


class TelephonyScriptProposeTool:
    name = "telephony.script_propose"
    description = (
        "Draft an inbound telephony script from company knowledge / blank template. "
        "Does not save until telephony.script_save. Use when owner asks to propose/сгенерировать сценарий."
    )
    critical_write = False
    parameters_schema = {"type": "object", "properties": {}}

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        draft = telephony_script.propose_script_from_knowledge(db, ctx)
        return ToolResult(
            ok=True,
            data=draft,
            message=(draft.get("message_ru") or "Черновик готов.") + "\n\n" + (draft.get("draft") or "")[:5000],
        )


class TelephonyScriptSaveTool:
    name = "telephony.script_save"
    description = (
        "Save inbound telephony script markdown for this tenant. "
        "Pass script text, or omit to save a fresh propose draft."
    )
    critical_write = True
    parameters_schema = {
        "type": "object",
        "properties": {
            "script": {"type": "string", "description": "Full script markdown"},
            "greeting": {"type": "string"},
        },
    }

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        body = str(params.get("script") or "").strip()
        if len(body) < 40:
            draft = telephony_script.propose_script_from_knowledge(db, ctx)
            body = str(draft.get("draft") or "")
        out = telephony_script.save_telephony_script(
            db,
            ctx,
            script=body,
            greeting=str(params.get("greeting") or "") or None,
            source="hermes.tool.save",
        )
        return ToolResult(ok=bool(out.get("ok")), data=out, message=out.get("message_ru") or "saved")


class TelephonyToolsSetTool:
    name = "telephony.tools_set"
    description = (
        "Enable in-call tools on the telephony script: calendar, email, conference (Telemost), "
        "knowledge, hangup. Requires a saved script. Pass tools array of ids, e.g. "
        "check_calendar, create_calendar_event, send_email, send_welcome_email, create_conference, "
        "get_company_knowledge, hangup_call."
    )
    critical_write = True
    parameters_schema = {
        "type": "object",
        "properties": {
            "tools": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Tool ids to enable on the line",
            }
        },
        "required": ["tools"],
    }

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        tools = params.get("tools") or []
        if isinstance(tools, str):
            tools = [t.strip() for t in tools.split(",") if t.strip()]
        out = telephony_script.set_telephony_tools(db, ctx, tools=list(tools))
        return ToolResult(ok=bool(out.get("ok")), data=out, message=out.get("message_ru") or out.get("error") or "")


class FilesCloudStatusTool:
    name = "files.cloud_status"
    description = (
        "List which cloud disks are connected for this tenant (Yandex Disk, Mail.ru, Google Drive, OneDrive)."
    )
    critical_write = False
    parameters_schema = {"type": "object", "properties": {}}

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        out = files_cloud.cloud_status(db, ctx)
        lines = [out.get("message_ru") or "Облака:", ""]
        for item in out.get("items") or []:
            mark = "готово" if item.get("ready") else "нет"
            lines.append(f"- {item.get('title')}: {mark}")
        return ToolResult(ok=True, data=out, message="\n".join(lines))


class FilesCloudListTool:
    name = "files.cloud_list"
    description = "List root (or path) of a connected cloud: yadisk | mailru | gdrive | onedrive."
    critical_write = False
    parameters_schema = {
        "type": "object",
        "properties": {
            "source": {"type": "string"},
            "path": {"type": "string", "default": "/"},
        },
        "required": ["source"],
    }

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        source = str(params.get("source") or "").strip()
        path = str(params.get("path") or "/").strip() or "/"
        out = files_cloud.probe_cloud_list(db, ctx, source=source, path=path)
        return ToolResult(ok=bool(out.get("ok")), data=out, message=out.get("message_ru") or "")


class CredentialsOpenFormTool:
    name = "credentials.open_form"
    description = (
        "Open a secure UI credential form (never ask to paste secrets in chat). "
        "Kinds: mango_sip, telegram_bot, files_yadisk, files_mailru, files_gdrive, files_onedrive. "
        "Use for SIP, Telegram bot token, or cloud disks."
    )
    critical_write = False
    parameters_schema = {
        "type": "object",
        "properties": {
            "kind": {
                "type": "string",
                "description": "mango_sip | telegram_bot | files_yadisk | files_mailru | files_gdrive | files_onedrive",
            }
        },
        "required": ["kind"],
    }

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        kind = str(params.get("kind") or "mango_sip").strip()
        form = credential_form_spec(kind)
        titles = {
            "mango_sip": "SIP Mango",
            "telegram_bot": "Telegram bot",
            "files_yadisk": "Яндекс.Диск",
            "files_mailru": "Облако Mail.ru",
            "files_gdrive": "Google Drive",
            "files_onedrive": "OneDrive",
        }
        title = titles.get(kind, kind)
        return ToolResult(
            ok=True,
            data={"pending_credential_form": form, "kind": kind},
            message=(
                f"Открыл безопасную форму «{title}». "
                "Секрет не пишите в чат — только в форме."
                + (
                    " Для Google/OneDrive отметьте согласие на зарубежную обработку."
                    if kind in ("files_gdrive", "files_onedrive")
                    else ""
                )
            ),
        )
