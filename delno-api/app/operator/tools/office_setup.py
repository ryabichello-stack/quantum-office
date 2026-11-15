"""Hermes tools for telephony script/tools and cloud disks — agent-callable."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.operator.tools.registry import ToolResult
from app.adapters.connectors import CONNECTOR_KINDS
from app.services import files_cloud, telephony_script
from app.services.connectors import list_tenant_connector_readiness, probe_tenant_connector, update_tenant_connector
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
        if not tools:
            tools = list(telephony_script.LINE_TOOLS_BEFORE_TEST)
        out = telephony_script.set_telephony_tools(db, ctx, tools=list(tools))
        return ToolResult(ok=bool(out.get("ok")), data=out, message=out.get("message_ru") or out.get("error") or "")


class TelephonyVoiceSetTool:
    name = "telephony.voice_set"
    description = (
        "Set the secretary voice for THIS company. Default and required before a test call: cedar. "
        "Say to the owner simply «голос Cedar», without model jargon."
    )
    critical_write = False
    parameters_schema = {
        "type": "object",
        "properties": {"voice": {"type": "string", "description": "cedar"}},
    }

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        from app.services.ava_readiness import set_tenant_voice

        voice = str(params.get("voice") or "cedar")
        out = set_tenant_voice(db, ctx, voice)
        return ToolResult(ok=bool(out.get("ok")), data=out, message=out.get("message_ru") or "")


class MeetingTool:
    """Shared with the phone line: book / move / confirm / cancel."""

    def __init__(self, name: str, action: str, description: str) -> None:
        self.name = name
        self.action = action
        self.description = description
        self.critical_write = False
        self.parameters_schema = {
            "type": "object",
            "properties": {
                "start": {"type": "string"},
                "title": {"type": "string"},
                "email": {"type": "string"},
                "phone": {"type": "string"},
                "appointment_id": {"type": "string"},
                "confirmed_by_caller": {"type": "boolean"},
            },
        }

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        from app.services.appointments import handle

        if self.action in {"book_meeting", "reschedule_meeting", "confirm_meeting", "cancel_meeting"} and params.get(
            "confirmed_by_caller"
        ) is not True:
            return ToolResult(
                ok=False,
                data={"error": "caller_confirmation_required"},
                message="Сначала спросите человека, точно ли так сделать, и дождитесь «да».",
            )
        out = handle(db, ctx, self.action, params, channel=str(params.get("channel") or "") or None)
        return ToolResult(ok=bool(out.get("ok")), data=out, message=out.get("message_ru") or "")


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
        "Kinds: mango_sip, telegram_bot, max_bot, files_yadisk, files_mailru, files_gdrive, files_onedrive. "
        "Use for SIP, Telegram/MAX bot tokens, or cloud disks."
    )
    critical_write = False
    parameters_schema = {
        "type": "object",
        "properties": {
            "kind": {
                "type": "string",
                "description": "mango_sip | telegram_bot | max_bot | files_yadisk | files_mailru | files_gdrive | files_onedrive",
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
            "max_bot": "MAX bot",
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


class OfficeConnectorSetTool:
    name = "office.connector_set"
    description = (
        "Enable or disable an office connector for this tenant "
        "(mail | calendar | conference | files | outreach). "
        "tools_first: enabling opts the tenant into the shared upstream; "
        "then probe readiness. Use on hermes_ops mail/calendar/conference steps."
    )
    critical_write = True
    parameters_schema = {
        "type": "object",
        "properties": {
            "kind": {
                "type": "string",
                "description": "mail | calendar | conference | files | outreach",
            },
            "enabled": {"type": "boolean", "description": "true to enable, false to disable"},
        },
        "required": ["kind", "enabled"],
    }

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        kind = str(params.get("kind") or "").strip().lower()
        if kind not in CONNECTOR_KINDS:
            return ToolResult(ok=False, data={"kind": kind}, message=f"unknown_connector:{kind}")
        enabled = bool(params.get("enabled"))
        updated = update_tenant_connector(db, ctx, kind, enabled=enabled)
        if not updated.get("ok"):
            return ToolResult(
                ok=False,
                data=updated,
                message=str(updated.get("error") or "connector_update_failed"),
            )
        probed = probe_tenant_connector(db, ctx, kind)
        ready_rows = {r["kind"]: r for r in list_tenant_connector_readiness(db, ctx)}
        row = ready_rows.get(kind) or {}
        usable = bool(row.get("usable"))
        state = "включён" if enabled else "выключен"
        detail = "готово" if usable else "пока не готово — не хватает доступа"
        from app.services.instrument_catalog import stitches_for_new

        try:
            from app.services.hermes_ops import office_setup_status

            status = office_setup_status(db, ctx)
            connected = {
                str(x.get("id"))
                for x in ((status.get("instruments") or {}).get("connected") or [])
                if isinstance(x, dict)
            }
            stitches = stitches_for_new(connected, kind)
        except Exception:  # noqa: BLE001
            stitches = []
        stitch_text = " ".join(s["text"] for s in stitches[:2])
        message = f"«{kind}» {state}; {detail}."
        if stitch_text:
            message += " " + stitch_text
        elif enabled:
            message += " Можно подключить сейчас или позже то, чего ещё нет, и связать с этим."
        return ToolResult(
            ok=True,
            data={
                "kind": kind,
                "enabled": enabled,
                "update": updated,
                "probe": probed,
                "readiness": row,
                "stitches": stitches,
            },
            message=message,
        )


class TelephonyProviderSetTool:
    name = "telephony.provider_set"
    description = (
        "Запомнить оператора связи владельца. "
        "provider=mango — дальше просим номер Манго Телеком. "
        "provider=other — заявка со статусом «скоро», шаг телефона откладывается."
    )
    critical_write = True
    parameters_schema = {
        "type": "object",
        "properties": {
            "provider": {"type": "string", "enum": ["mango", "other"]},
            "name": {"type": "string", "description": "Название другого оператора, если provider=other"},
        },
        "required": ["provider"],
    }

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        provider = str(params.get("provider") or "").strip().lower()
        if provider not in ("mango", "other"):
            return ToolResult(ok=False, data={}, message="provider_must_be_mango_or_other")
        name = str(params.get("name") or "").strip()[:120]
        from sqlalchemy.orm.attributes import flag_modified

        from app.models.tenant import Tenant
        from app.services.events import emit_event
        from app.services.hermes_ops import mark_setup_progress

        tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
        settings = dict(tenant.settings) if isinstance(tenant.settings, dict) else {}
        record = {
            "provider": provider,
            "name": name or ("Манго Телеком" if provider == "mango" else ""),
            "status": "active" if provider == "mango" else "soon",
            "label": "скоро" if provider == "other" else "Манго Телеком",
        }
        settings["telephony_provider"] = record
        tenant.settings = settings
        flag_modified(tenant, "settings")
        db.add(tenant)
        db.flush()
        if provider == "other":
            emit_event(
                db,
                event_type="telephony.provider.other",
                category="operational",
                tenant_id=ctx.tenant_id,
                source="telephony.provider_set",
                payload={"provider": "other", "name": record["name"], "status": "soon"},
            )
            mark_setup_progress(
                db,
                ctx,
                defer_instrument="phone",
                note="telephony_provider=other soon",
            )
            message = (
                "Заявку на другого оператора записал — статус «скоро». "
                "Телефон можно подключить позже. Сейчас перейдём к следующему шагу."
            )
        else:
            mark_setup_progress(
                db,
                ctx,
                resume_instrument="phone",
                note="telephony_provider=mango",
            )
            message = "Оператор — Манго Телеком. Пришлите номер в формате +7 987 123-45-67."
        return ToolResult(ok=True, data={"telephony_provider": record}, message=message)
