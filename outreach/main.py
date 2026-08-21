"""Quantum Labs Bitrix outreach — API (8012) + admin UI + CLI."""

from __future__ import annotations

import argparse
import json
import logging
import os
import secrets
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from bitrix_client import BitrixClient
from core.registry import AppContext, ModuleRegistry
from modules.clients import (
    ClientsModule,
    backfill_company_geo_and_fio,
    geo_stats,
    rebuild_outbox_from_clients,
    sync_from_bitrix,
)
from modules.deliverability import DeliverabilityModule
from modules.analytics import AnalyticsModule
from modules.dadata import DaDataModule
from modules.telephony import TelephonyModule, ingest_telephony_lead
from modules.runner import RunnerModule
from modules.tracking import PIXEL_GIF, TrackingModule
from modules.verification import VerificationModule
from modules.sequences import SequencesModule
from modules.policy import PolicyModule
from modules.replies import RepliesModule
from outbox import OutboxStore
from reply_watcher import ReplyWatchThread, check_replies, imap_configured
from runtime_settings import RuntimeSettings
from sender import send_batch, send_one, smtp_configured
from sync import sync_companies
from templates import (
    DEFAULT_HTML,
    DEFAULT_PLAIN,
    DEFAULT_SIGNATURE,
    default_logo_url,
    public_base_url,
    render_cooperation,
)
from content.packs import get_pack, list_packs, pack_campaign_templates
from content.pack_drafts import (
    PackDraftStore,
    normalize_steps,
    pack_letters_payload,
    resolve_pack,
)
from presentations import (
    presentation_meta,
    reset_presentation,
    save_presentation,
)

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("ava-outreach")

DATA_DIR = Path(os.getenv("DATA_DIR", "/opt/ava-outreach/data"))
DB_PATH = DATA_DIR / "outbox.db"
SETTINGS_DB = DATA_DIR / "settings.db"
STATIC_DIR = Path(__file__).resolve().parent / "static"
ASSETS_DIR = Path(__file__).resolve().parent / "assets"
BRAND_DATA_DIR = DATA_DIR / "brand"

_reply_thread: ReplyWatchThread | None = None
_settings: RuntimeSettings | None = None
_registry = ModuleRegistry()
_tracking_mod = TrackingModule()
_deliver_mod = DeliverabilityModule()
_runner_mod = RunnerModule()
_clients_mod = ClientsModule()
_analytics_mod = AnalyticsModule()
_dadata_mod = DaDataModule()
_telephony_mod = TelephonyModule()
_verification_mod = VerificationModule()
_sequences_mod = SequencesModule()
_policy_mod = PolicyModule()
_replies_mod = RepliesModule()
_registry.register(_tracking_mod)
_registry.register(_deliver_mod)
_registry.register(_runner_mod)
_registry.register(_clients_mod)
_registry.register(_analytics_mod)
_registry.register(_dadata_mod)
_registry.register(_telephony_mod)
_registry.register(_verification_mod)
_registry.register(_sequences_mod)
_registry.register(_policy_mod)
_registry.register(_replies_mod)
_app_ctx: AppContext | None = None


def _ensure_ui_token() -> str:
    token = (os.getenv("OUTREACH_UI_TOKEN") or "").strip()
    if token:
        return token
    token = secrets.token_urlsafe(24)
    os.environ["OUTREACH_UI_TOKEN"] = token
    env_path = Path(os.getenv("OUTREACH_ENV_PATH", "/opt/ava-outreach/.env"))
    try:
        if env_path.is_file():
            text = env_path.read_text(encoding="utf-8")
            if "OUTREACH_UI_TOKEN=" in text:
                lines = []
                for line in text.splitlines():
                    if line.startswith("OUTREACH_UI_TOKEN="):
                        lines.append(f"OUTREACH_UI_TOKEN={token}")
                    else:
                        lines.append(line)
                env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            else:
                with env_path.open("a", encoding="utf-8") as fh:
                    fh.write(f"\nOUTREACH_UI_TOKEN={token}\n")
            logger.info("generated OUTREACH_UI_TOKEN and wrote to %s", env_path)
        else:
            logger.warning("OUTREACH_UI_TOKEN generated in-memory only (no .env)")
    except OSError as exc:
        logger.warning("could not persist OUTREACH_UI_TOKEN: %s", exc)
    return token


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _reply_thread, _settings, _app_ctx
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    store = OutboxStore(DB_PATH)
    store.init_db()
    _settings = RuntimeSettings(SETTINGS_DB)
    try:
        from callback_cta import init_db as _cb_init

        _cb_init()
    except Exception:  # noqa: BLE001
        logger.exception("callback_cta init failed")
    _ensure_ui_token()
    _registry.init_all()

    def _campaign_send(n: int) -> dict[str, Any]:
        bitrix = _bitrix_or_none()
        try:
            return send_batch(
                _store(),
                limit=n,
                dry_run=False,
                bitrix=bitrix,
                settings=_settings,
                tracking=_tracking_mod.store,
                deliverability=_deliver_mod.store,
            )
        finally:
            if bitrix:
                bitrix.close()

    _runner_mod.bind_send_fn(_campaign_send)
    _app_ctx = AppContext(
        settings=_settings,
        outbox=store,
        bitrix_factory=_bitrix_or_none,
    )
    _registry.startup_all(_app_ctx)
    logger.info("ava-outreach ready db=%s modules=%s", DB_PATH, [m.name for m in _registry.modules])

    if _settings.get_bool("REPLY_WATCH_ENABLED", True) or os.getenv(
        "REPLY_WATCH_ENABLED", "true"
    ).lower() in ("1", "true", "yes", "on"):
        _reply_thread = ReplyWatchThread(store, _webhook_url())
        _reply_thread.start()

    yield

    _registry.shutdown_all()
    if _reply_thread is not None:
        _reply_thread.stop()
        _reply_thread.join(timeout=5)
        _reply_thread = None


app = FastAPI(title="AVA Outreach", version="0.10.0", lifespan=lifespan)



def _store() -> OutboxStore:
    return OutboxStore(DB_PATH)


_pack_drafts: PackDraftStore | None = None


def _drafts() -> PackDraftStore:
    global _pack_drafts
    if _pack_drafts is None:
        _pack_drafts = PackDraftStore(SETTINGS_DB)
    return _pack_drafts


def _rt() -> RuntimeSettings:
    global _settings
    if _settings is None:
        _settings = RuntimeSettings(SETTINGS_DB)
    return _settings


def _webhook_url() -> str:
    return (os.getenv("BITRIX_WEBHOOK_URL") or "").strip()


def _bitrix_or_none() -> BitrixClient | None:
    url = _webhook_url()
    if not url:
        return None
    return BitrixClient(url)


def _status_payload() -> dict[str, Any]:
    store = _store()
    rt = _rt()
    webhook = bool(_webhook_url())
    portal = (os.getenv("BITRIX_PORTAL_URL") or "").strip()
    return {
        "ok": True,
        "service": "ava-outreach",
        "version": "0.10.0",
        "outreach_enabled": rt.get_bool("OUTREACH_ENABLED", False),
        "run_state": (rt.get("OUTREACH_RUN_STATE", "stopped") or "stopped").lower(),
        "daily_limit": rt.get_int("OUTREACH_DAILY_LIMIT", 15),
        "effective_daily_limit": _deliver_mod.store.effective_daily_limit(
            rt, rt.get_int("OUTREACH_DAILY_LIMIT", 15)
        ),
        "smtp_configured": smtp_configured(),
        "bitrix_webhook_configured": webhook,
        "bitrix_portal_url": portal,
        "bitrix_create_deal": rt.get_bool("BITRIX_CREATE_DEAL", False),
        "bitrix_assigned_by_id": rt.get_int("BITRIX_ASSIGNED_BY_ID", 1),
        "imap_configured": imap_configured(),
        "reply_watch_enabled": rt.get_bool("REPLY_WATCH_ENABLED", True),
        "schedule_enabled": rt.get_bool("SCHEDULE_ENABLED", False),
        "tracking_plus_reply_to": rt.get_bool("TRACKING_PLUS_REPLY_TO", False),
        "open_tracking_enabled": rt.get_bool("OPEN_TRACKING_ENABLED", True),
        "tracking_public_base": rt.get("TRACKING_PUBLIC_BASE")
        or "https://a.47z.ru/_ava_outreach",
        "dadata_configured": _dadata_mod.health().get("configured"),
        "dadata": _dadata_mod.health(),
        "telephony": _telephony_mod.health(),
        "verification": _verification_mod.health(),
        "sequences": _sequences_mod.health(),
        "policy": _policy_mod.health(),
        "reply_inbox": _replies_mod.health(),
        "deliverability": _deliver_mod.store.stats(rt, rt.get_int("OUTREACH_DAILY_LIMIT", 15)),
        "engagement": _tracking_mod.store.engagement_counts(),
        "warmup_enabled": rt.get_bool("WARMUP_ENABLED", True),
        "primary_mailbox_protection": True,
        "run_respect_window": rt.get_bool("RUN_RESPECT_WINDOW", True),
        "schedule_local_windows": rt.get_bool("SCHEDULE_LOCAL_WINDOWS", True),
        "schedule_window": {
            "start": rt.get_int("SCHEDULE_WINDOW_START", 10),
            "end": rt.get_int("SCHEDULE_WINDOW_END", 18),
            "timezone": rt.get("SCHEDULE_TIMEZONE", "Europe/Moscow"),
            "batch_size": rt.get_int("SCHEDULE_BATCH_SIZE", 1),
            "local_windows": rt.get_bool("SCHEDULE_LOCAL_WINDOWS", True),
            "slots": rt.get("SCHEDULE_SLOTS", "10:00-11:30,14:30-16:30"),
            "preferred_weekdays": rt.get("SCHEDULE_PREFERRED_WEEKDAYS", "1,2,3"),
            "allowed_weekdays": rt.get("SCHEDULE_ALLOWED_WEEKDAYS", "0,1,2,3,4"),
            "default_timezone": rt.get("SCHEDULE_DEFAULT_TIMEZONE", "Europe/Moscow"),
        },
        "runner": _runner_mod.health(),
        "clients": {
            "counts": _clients_mod.store.counts(),
            "db_path": str(_clients_mod.store.db_path),
            "last_sync": _clients_mod.store.last_sync(),
            "geo": geo_stats(_clients_mod.store),
        },
        "modules": _registry.catalog(),
        "outbox": store.status_report(),
        "daily": store.stats_daily(14),
    }


def _extract_token(request: Request, authorization: str | None, x_token: str | None) -> str:
    if x_token:
        return x_token.strip()
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    cookie = request.cookies.get("outreach_token")
    if cookie:
        return cookie.strip()
    q = request.query_params.get("token")
    if q:
        return q.strip()
    return ""


async def require_ui_auth(
    request: Request,
    authorization: str | None = Header(default=None),
    x_outreach_token: str | None = Header(default=None, alias="X-Outreach-Token"),
) -> None:
    expected = (os.getenv("OUTREACH_UI_TOKEN") or "").strip()
    if not expected:
        expected = _ensure_ui_token()
    got = _extract_token(request, authorization, x_outreach_token)
    if not got or not secrets.compare_digest(got, expected):
        raise HTTPException(status_code=401, detail="Unauthorized — set OUTREACH_UI_TOKEN")


# Module routes (independent feature APIs) — after auth helper exists
_registry.mount_routes(
    app, prefix="/api/modules", dependencies=[Depends(require_ui_auth)]
)


# --- public ---


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "service": "ava-outreach"}


def _telephony_token_ok(got: str) -> bool:
    got = (got or "").strip()
    if not got:
        return False
    candidates = [
        (os.getenv("TELEPHONY_INGEST_TOKEN") or "").strip(),
        (os.getenv("OUTREACH_UI_TOKEN") or "").strip(),
    ]
    for expected in candidates:
        if expected and secrets.compare_digest(got, expected):
            return True
    return False


@app.post("/api/telephony/lead")
async def telephony_lead_ingest(
    request: Request,
    x_webhook_token: str | None = Header(default=None, alias="X-Webhook-Token"),
    x_outreach_token: str | None = Header(default=None, alias="X-Outreach-Token"),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Public ingest from ava-mailer (post-call) → Bitrix CRM."""
    got = (x_webhook_token or x_outreach_token or "").strip()
    if authorization and authorization.lower().startswith("bearer "):
        got = got or authorization[7:].strip()
    if not _telephony_token_ok(got):
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        body = await request.json()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"invalid json: {exc}") from exc
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="json object required")
    bitrix = _bitrix_or_none()
    if bitrix is None:
        raise HTTPException(status_code=400, detail="BITRIX_WEBHOOK_URL missing")
    try:
        return ingest_telephony_lead(
            bitrix,
            _telephony_mod.store,
            body,
            settings=_rt(),
        )
    finally:
        bitrix.close()


@app.get("/t/o/{token}.gif")
def open_pixel(token: str):
    """Public open-tracking pixel (no auth). Always returns 1×1 GIF."""
    from fastapi.responses import Response

    try:
        tok = (token or "").strip()
        if tok:
            _tracking_mod.store.record_open(tok)
    except Exception:  # noqa: BLE001
        logger.debug("open pixel record failed", exc_info=True)
    return Response(
        content=PIXEL_GIF,
        media_type="image/gif",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


def _apply_unsubscribe(token: str) -> dict[str, Any]:
    """Idempotent unsubscribe by HTTPS token."""
    from modules.tracking import parse_unsubscribe_token, verify_unsubscribe_token

    tok = (token or "").strip()
    store = _store()
    ev = _tracking_mod.store.by_unsub_token(tok)
    row = None
    email = None
    if ev:
        row = store.get_row(ev.outbox_id)
        email = ev.email
    else:
        parsed = parse_unsubscribe_token(tok)
        if not parsed:
            return {"ok": False, "error": "invalid_token"}
        row = store.get_row(parsed["outbox_id"])
        if not row:
            return {"ok": False, "error": "unknown_token"}
        if not verify_unsubscribe_token(tok, email=row.email):
            return {"ok": False, "error": "bad_signature"}
        email = row.email

    assert email
    _deliver_mod.store.add_suppression(email, reason="unsubscribe", source="https-unsub")
    if row:
        store.cancel(row.id, reason="unsubscribe")
        try:
            from modules.sequences import SequenceStore
            from modules.policy import ContactPolicyStore

            SequenceStore().stop(email=email, company_id=row.company_id or None, reason="unsubscribe")
            if row.company_id:
                ContactPolicyStore().note_unsubscribe(row.company_id)
        except Exception:  # noqa: BLE001
            logger.debug("unsub sequence/policy failed", exc_info=True)
    try:
        bitrix = _bitrix_or_none()
        if bitrix and row and row.company_id:
            bitrix.add_timeline_comment(
                row.company_id,
                f"🚫 Unsubscribe (HTTPS): {email} отказался от email-коммуникаций.",
                entity_type="company",
            )
            bitrix.close()
    except Exception:  # noqa: BLE001
        logger.debug("unsub bitrix note failed", exc_info=True)
    return {"ok": True, "email": email, "outbox_id": row.id if row else None}


@app.api_route("/unsubscribe/{token}", methods=["GET", "POST"])
async def unsubscribe_one_click(token: str, request: Request):
    """Public List-Unsubscribe one-click / browser page (no auth)."""
    result = _apply_unsubscribe(token)
    if request.method == "POST":
        if not result.get("ok"):
            raise HTTPException(status_code=400, detail=result.get("error", "failed"))
        return JSONResponse({"ok": True})
    if not result.get("ok"):
        return JSONResponse(
            {
                "ok": False,
                "message": "Ссылка отписки недействительна или устарела.",
                "error": result.get("error"),
            },
            status_code=400,
        )
    return JSONResponse(
        {
            "ok": True,
            "message": (
                "Вы отписаны от рассылки Quantum Labs Outreach. "
                "Письма больше не будут отправляться."
            ),
            "email": result.get("email"),
        }
    )


def _callback_source_email(token: str) -> str | None:
    from callback_cta import parse_callback_token

    parsed = parse_callback_token(token)
    if not parsed:
        return None
    oid = int(parsed["outbox_id"] or 0)
    if oid <= 0:
        return "campaign"
    row = _store().get_row(oid)
    return row.email if row else None


@app.api_route("/callback/{token}", methods=["GET", "POST"])
async def callback_request_page(token: str, request: Request):
    """Public landing: FIO + phone form → notify + optional AVA dial."""
    from fastapi.responses import HTMLResponse

    from callback_cta import (
        form_page_html,
        parse_callback_token,
        process_callback_request,
        verify_callback_token,
    )

    rt = _rt()
    source_email = _callback_source_email(token)
    verified = verify_callback_token(token, email=source_email or "campaign")
    if not verified:
        return HTMLResponse(
            form_page_html(token=token, settings=rt, error="Ссылка недействительна или устарела."),
            status_code=400,
        )

    if request.method == "GET":
        q_fio = (request.query_params.get("fio") or "").strip()
        q_phone = (request.query_params.get("phone") or "").strip()
        if q_fio and q_phone:
            result = process_callback_request(
                token=token,
                fio=q_fio,
                phone=q_phone,
                settings=rt,
                source_email=source_email,
                user_agent=request.headers.get("user-agent"),
                ip=request.client.host if request.client else None,
            )
            if result.get("ok"):
                return HTMLResponse(
                    form_page_html(
                        token=token,
                        settings=rt,
                        done=True,
                        done_message=str(result.get("message") or ""),
                    )
                )
            err_map = {
                "fio_required": "Укажите ФИО",
                "phone_invalid": "Укажите корректный телефон",
                "rate_limited": "Заявка с этого номера уже принята. Подождите немного.",
                "bad_signature": "Ссылка недействительна",
            }
            return HTMLResponse(
                form_page_html(
                    token=token,
                    settings=rt,
                    prefill_fio=q_fio,
                    prefill_phone=q_phone,
                    error=err_map.get(str(result.get("error")), "Не удалось отправить заявку"),
                ),
                status_code=400,
            )
        return HTMLResponse(
            form_page_html(
                token=token,
                settings=rt,
                prefill_fio=q_fio,
                prefill_phone=q_phone,
            )
        )

    fio = ""
    phone = ""
    ctype = (request.headers.get("content-type") or "").lower()
    if "application/json" in ctype:
        try:
            payload = await request.json()
        except Exception:  # noqa: BLE001
            payload = {}
        fio = str((payload or {}).get("fio") or "")
        phone = str((payload or {}).get("phone") or "")
    else:
        form = await request.form()
        fio = str(form.get("fio") or "")
        phone = str(form.get("phone") or "")

    result = process_callback_request(
        token=token,
        fio=fio,
        phone=phone,
        settings=rt,
        source_email=source_email,
        user_agent=request.headers.get("user-agent"),
        ip=request.client.host if request.client else None,
    )
    if "application/json" in ctype:
        code = 200 if result.get("ok") else 400
        return JSONResponse(result, status_code=code)

    if not result.get("ok"):
        err_map = {
            "fio_required": "Укажите ФИО",
            "phone_invalid": "Укажите корректный телефон",
            "rate_limited": "Заявка с этого номера уже принята. Подождите немного.",
            "bad_signature": "Ссылка недействительна",
        }
        return HTMLResponse(
            form_page_html(
                token=token,
                settings=rt,
                prefill_fio=fio,
                prefill_phone=phone,
                error=err_map.get(str(result.get("error")), "Не удалось отправить заявку"),
            ),
            status_code=400,
        )
    # Bitrix note (best-effort)
    try:
        parsed = parse_callback_token(token)
        oid = int((parsed or {}).get("outbox_id") or 0)
        row = _store().get_row(oid) if oid else None
        bitrix = _bitrix_or_none()
        if bitrix and row and row.company_id:
            bitrix.add_timeline_comment(
                row.company_id,
                (
                    f"📞 Заявка на звонок из письма: {result.get('fio')} "
                    f"+{result.get('phone')} (notify={result.get('notify_ok')}, "
                    f"dial={((result.get('dial') or {}).get('mode'))})"
                ),
                entity_type="company",
            )
            bitrix.close()
    except Exception:  # noqa: BLE001
        logger.debug("callback bitrix note failed", exc_info=True)

    return HTMLResponse(
        form_page_html(
            token=token,
            settings=rt,
            done=True,
            done_message=str(result.get("message") or ""),
        )
    )


class CallbackCtaSettingsBody(BaseModel):
    settings: dict[str, Any] = Field(default_factory=dict)


@app.get("/api/callback-cta/settings", dependencies=[Depends(require_ui_auth)])
def api_callback_cta_settings() -> dict[str, Any]:
    from callback_cta import settings_snapshot

    return {"ok": True, "settings": settings_snapshot(_rt())}


@app.put("/api/callback-cta/settings", dependencies=[Depends(require_ui_auth)])
def api_callback_cta_settings_put(body: CallbackCtaSettingsBody) -> dict[str, Any]:
    from callback_cta import settings_snapshot

    updated = _rt().set_many(body.settings or {})
    return {"ok": True, "updated": sorted(updated.keys()), "settings": settings_snapshot(_rt())}


@app.get("/api/callback-cta/requests", dependencies=[Depends(require_ui_auth)])
def api_callback_cta_requests(limit: int = 30) -> dict[str, Any]:
    from callback_cta import recent_requests

    return {"ok": True, "items": recent_requests(limit=limit)}


@app.get("/")
def root() -> RedirectResponse:
    return RedirectResponse(url="/ui/")


# --- auth gate for UI + API ---


@app.get("/status")
def status() -> dict[str, Any]:
    return _status_payload()


@app.post("/sync", dependencies=[Depends(require_ui_auth)])
def api_sync() -> dict[str, Any]:
    """Sync Bitrix → local clients DB, then refresh outbox from local mirror."""
    client = _bitrix_or_none()
    if client is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "BITRIX_WEBHOOK_URL missing. Create incoming webhook on "
                f"{os.getenv('BITRIX_PORTAL_URL', 'https://b24-m5614z.bitrix24.ru/')} "
                "with crm rights and set it in /opt/ava-outreach/.env"
            ),
        )
    try:
        clients_report = sync_from_bitrix(_clients_mod.store, client)
        outbox_report = rebuild_outbox_from_clients(_clients_mod.store, _store())
        return {
            "ok": bool(clients_report.get("ok")),
            "clients": clients_report,
            "outbox_rebuild": outbox_report,
        }
    finally:
        client.close()


@app.post("/api/modules/clients/sync-bitrix", dependencies=[Depends(require_ui_auth)])
def api_clients_sync_bitrix() -> dict[str, Any]:
    return api_sync()


@app.post("/api/modules/clients/rebuild-outbox", dependencies=[Depends(require_ui_auth)])
def api_clients_rebuild_outbox() -> dict[str, Any]:
    """Rebuild outbox from local clients.db without calling Bitrix."""
    return rebuild_outbox_from_clients(_clients_mod.store, _store())


@app.get("/api/modules/clients/geo", dependencies=[Depends(require_ui_auth)])
def api_clients_geo_stats() -> dict[str, Any]:
    return geo_stats(_clients_mod.store)


@app.post("/api/modules/clients/backfill-geo", dependencies=[Depends(require_ui_auth)])
def api_clients_backfill_geo(limit: int | None = None) -> dict[str, Any]:
    """Backfill city/timezone + director Имя/Отчество from DaData cache / Bitrix raw."""
    report = backfill_company_geo_and_fio(_clients_mod.store, limit=limit)
    report["stats"] = geo_stats(_clients_mod.store)
    return report


@app.post("/check-replies", dependencies=[Depends(require_ui_auth)])
def api_check_replies() -> dict[str, Any]:
    bitrix = _bitrix_or_none()
    try:
        return check_replies(_store(), bitrix)
    finally:
        if bitrix:
            bitrix.close()


class SendBody(BaseModel):
    limit: int = Field(default=1, ge=1, le=50)
    dry_run: bool = False
    only_email: str | None = None


@app.post("/send-batch", dependencies=[Depends(require_ui_auth)])
def api_send_batch(body: SendBody) -> dict[str, Any]:
    bitrix = _bitrix_or_none()
    try:
        result = send_batch(
            _store(),
            limit=body.limit,
            dry_run=body.dry_run,
            bitrix=bitrix,
            only_email=body.only_email,
            settings=_rt(),
            tracking=_tracking_mod.store,
            deliverability=_deliver_mod.store,
        )
        if not result.get("ok"):
            raise HTTPException(status_code=400, detail=result.get("error") or "send failed")
        return result
    finally:
        if bitrix:
            bitrix.close()


@app.post("/dry-run", dependencies=[Depends(require_ui_auth)])
def api_dry_run(limit: int = 5) -> dict[str, Any]:
    return api_send_batch(SendBody(limit=max(1, min(limit, 50)), dry_run=True))


class SendOneBody(BaseModel):
    to: str = Field(..., min_length=3)
    contact_name: str | None = None
    dry_run: bool = False
    create_bitrix_deal: bool = False
    attach_presentation: bool | None = None


@app.post("/send-one", dependencies=[Depends(require_ui_auth)])
def api_send_one(body: SendOneBody) -> dict[str, Any]:
    """One-shot send to an explicit address (test to yourself). No OUTREACH_ENABLED needed."""
    bitrix = _bitrix_or_none() if body.create_bitrix_deal else None
    try:
        result = send_one(
            _store(),
            to=body.to,
            contact_name=body.contact_name,
            dry_run=body.dry_run,
            settings=_rt(),
            tracking=_tracking_mod.store,
            deliverability=_deliver_mod.store,
            create_bitrix_deal=body.create_bitrix_deal,
            bitrix=bitrix,
            attach_presentation=body.attach_presentation,
        )
        if not result.get("ok"):
            raise HTTPException(status_code=400, detail=result.get("error") or "send failed")
        return result
    finally:
        if bitrix:
            bitrix.close()


# --- richer admin API ---


@app.get("/api/dashboard", dependencies=[Depends(require_ui_auth)])
def api_dashboard() -> dict[str, Any]:
    return _status_payload()


@app.get("/api/outbox", dependencies=[Depends(require_ui_auth)])
def api_outbox(
    status: str | None = None,
    q: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    rows, total = _store().list_outbox(status=status, q=q, limit=limit, offset=offset)
    return {
        "ok": True,
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [
            {
                "id": r.id,
                "email": r.email,
                "company_id": r.company_id,
                "contact_id": r.contact_id,
                "contact_name": r.contact_name,
                "status": r.status,
                "attempts": r.attempts,
                "last_error": r.last_error,
                "sent_at": r.sent_at,
                "deal_id": r.deal_id,
                "created_at": r.created_at,
                "updated_at": r.updated_at,
            }
            for r in rows
        ],
    }


class StatusBody(BaseModel):
    status: str


@app.patch("/api/outbox/{row_id}", dependencies=[Depends(require_ui_auth)])
def api_outbox_patch(row_id: int, body: StatusBody) -> dict[str, Any]:
    allowed = {"pending", "skipped", "failed", "sent", "replied"}
    if body.status not in allowed:
        raise HTTPException(status_code=400, detail=f"status must be one of {sorted(allowed)}")
    ok = _store().set_status(row_id, body.status)  # type: ignore[arg-type]
    if not ok:
        raise HTTPException(status_code=404, detail="not found")
    row = _store().get_row(row_id)
    return {"ok": True, "item": row.__dict__ if row else None}


@app.get("/api/replies", dependencies=[Depends(require_ui_auth)])
def api_replies(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    items, total = _store().list_inbound(limit=limit, offset=offset)
    return {"ok": True, "total": total, "items": items}


@app.get("/api/settings", dependencies=[Depends(require_ui_auth)])
def api_settings_get() -> dict[str, Any]:
    snap = _rt().snapshot()
    if not (snap.get("OUTREACH_TEMPLATE_PLAIN") or "").strip():
        snap["OUTREACH_TEMPLATE_PLAIN"] = DEFAULT_PLAIN
    if not (snap.get("OUTREACH_TEMPLATE_HTML") or "").strip():
        snap["OUTREACH_TEMPLATE_HTML"] = DEFAULT_HTML
    if not (snap.get("OUTREACH_SIGNATURE") or "").strip():
        snap["OUTREACH_SIGNATURE"] = DEFAULT_SIGNATURE
    else:
        from templates import normalize_signature_template

        snap["OUTREACH_SIGNATURE"] = normalize_signature_template(snap.get("OUTREACH_SIGNATURE"))
    if not (snap.get("OUTREACH_LOGO_URL") or "").strip():
        snap["OUTREACH_LOGO_URL"] = default_logo_url(lambda k: snap.get(k) or "")
    if snap.get("OUTREACH_LOGO_ENABLED") in (None, ""):
        snap["OUTREACH_LOGO_ENABLED"] = "true"
    return {"ok": True, "settings": snap}


class SettingsBody(BaseModel):
    settings: dict[str, Any]


@app.put("/api/settings", dependencies=[Depends(require_ui_auth)])
def api_settings_put(body: SettingsBody) -> dict[str, Any]:
    updated = _rt().set_many(body.settings)
    return {"ok": True, "updated": sorted(updated.keys()), "settings": _rt().snapshot()}


class PreviewBody(BaseModel):
    contact_name: str = "коллега"
    subject: str | None = None
    plain: str | None = None
    html: str | None = None
    company_name: str | None = None
    website: str | None = None
    phone: str | None = None
    contact_email: str | None = None
    signature: str | None = None
    logo_url: str | None = None
    logo_enabled: bool | None = None


@app.post("/api/preview", dependencies=[Depends(require_ui_auth)])
def api_preview(body: PreviewBody) -> dict[str, Any]:
    rt = _rt()
    subject = body.subject or rt.get("OUTREACH_SUBJECT", "Сотрудничество — Quantum Labs")
    company = (
        body.company_name
        if body.company_name is not None
        else (rt.get("OUTREACH_COMPANY_NAME", "Quantum Labs") or "Quantum Labs")
    )
    website = (
        body.website
        if body.website is not None
        else (rt.get("OUTREACH_WEBSITE", "https://quantumlabs.ru") or "https://quantumlabs.ru")
    )
    phone = body.phone if body.phone is not None else (rt.get("OUTREACH_CONTACT_PHONE", "") or "")
    contact_email = (
        body.contact_email
        if body.contact_email is not None
        else (
            (rt.get("OUTREACH_CONTACT_EMAIL", "") or "").strip()
            or rt.get("OUTREACH_UNSUBSCRIBE_MAILTO", "")
            or os.getenv("MAIL_USERNAME")
            or "office@quantumlabs.ru"
        )
    )
    signature = (
        body.signature
        if body.signature is not None
        else (rt.get("OUTREACH_SIGNATURE", "") or DEFAULT_SIGNATURE)
    )
    logo_url = (
        body.logo_url
        if body.logo_url is not None
        else (
            (rt.get("OUTREACH_LOGO_URL", "") or "").strip()
            or default_logo_url(lambda k: rt.get(k, "") or "")
        )
    )
    logo_on = (
        body.logo_enabled
        if body.logo_enabled is not None
        else rt.get_bool("OUTREACH_LOGO_ENABLED", True)
    )
    cb_url = None
    try:
        from callback_cta import callback_url_for, cta_enabled, make_callback_token

        if cta_enabled(rt):
            cb_url = callback_url_for(
                make_callback_token(outbox_id=0, email="preview"),
                rt,
            )
    except Exception:  # noqa: BLE001
        cb_url = None
    plain, html = render_cooperation(
        contact_name=body.contact_name,
        company_name=company or "Quantum Labs",
        website=website or "https://quantumlabs.ru",
        phone=phone or "",
        unsubscribe_mailto=rt.get("OUTREACH_UNSUBSCRIBE_MAILTO", "")
        or os.getenv("MAIL_USERNAME")
        or "office@quantumlabs.ru",
        plain_template=body.plain
        if body.plain is not None
        else (rt.get("OUTREACH_TEMPLATE_PLAIN") or None),
        html_template=body.html
        if body.html is not None
        else (rt.get("OUTREACH_TEMPLATE_HTML") or None),
        signature_template=signature or DEFAULT_SIGNATURE,
        logo_url=logo_url,
        logo_enabled=bool(logo_on),
        contact_email=contact_email or "",
        icon_base_url=public_base_url(lambda k: rt.get(k, "") or ""),
        callback_url=cb_url,
    )
    attach_on = rt.get_bool("OUTREACH_ATTACH_PRESENTATION", False)
    return {
        "ok": True,
        "subject": subject,
        "plain": plain,
        "html": html,
        "attach_presentation": attach_on,
        "sequence_pack": rt.get("OUTREACH_SEQUENCE_PACK", "") or "",
        "logo_url": logo_url,
    }


@app.get("/assets/brand/custom.png")
def brand_custom_logo() -> FileResponse:
    path = BRAND_DATA_DIR / "logo.png"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="no custom logo")
    return FileResponse(path, media_type="image/png")


@app.get("/api/brand/logo", dependencies=[Depends(require_ui_auth)])
def api_brand_logo_meta() -> dict[str, Any]:
    rt = _rt()
    custom = BRAND_DATA_DIR / "logo.png"
    url = (rt.get("OUTREACH_LOGO_URL", "") or "").strip() or default_logo_url(
        lambda k: rt.get(k, "") or ""
    )
    return {
        "ok": True,
        "logo_url": url,
        "default_url": default_logo_url(lambda k: rt.get(k, "") or ""),
        "has_custom": custom.is_file(),
        "enabled": rt.get_bool("OUTREACH_LOGO_ENABLED", True),
    }


@app.post("/api/brand/logo", dependencies=[Depends(require_ui_auth)])
async def api_brand_logo_upload(file: UploadFile = File(...)) -> dict[str, Any]:
    raw = await file.read()
    if not raw or len(raw) > 512_000:
        raise HTTPException(status_code=400, detail="logo must be PNG/SVG/JPEG under 512KB")
    content_type = (file.content_type or "").lower()
    name = (file.filename or "").lower()
    if not (
        content_type in ("image/png", "image/jpeg", "image/jpg", "image/webp", "image/svg+xml")
        or name.endswith((".png", ".jpg", ".jpeg", ".webp", ".svg"))
    ):
        raise HTTPException(status_code=400, detail="unsupported image type")
    BRAND_DATA_DIR.mkdir(parents=True, exist_ok=True)
    dest = BRAND_DATA_DIR / "logo.png"
    dest.write_bytes(raw)
    base = public_base_url(lambda k: _rt().get(k, "") or "")
    logo_url = f"{base}/assets/brand/custom.png?v={int(dest.stat().st_mtime)}"
    _rt().set_many({"OUTREACH_LOGO_URL": logo_url, "OUTREACH_LOGO_ENABLED": "true"})
    return {"ok": True, "logo_url": logo_url, "bytes": len(raw)}


@app.delete("/api/brand/logo", dependencies=[Depends(require_ui_auth)])
def api_brand_logo_reset() -> dict[str, Any]:
    custom = BRAND_DATA_DIR / "logo.png"
    if custom.is_file():
        custom.unlink()
    url = default_logo_url(lambda k: _rt().get(k, "") or "")
    _rt().set_many({"OUTREACH_LOGO_URL": url, "OUTREACH_LOGO_ENABLED": "true"})
    return {"ok": True, "logo_url": url}


class ApplyPackBody(BaseModel):
    pack_id: str
    attach_presentation: bool | None = None
    reset_draft: bool = False


class PackLetterStepBody(BaseModel):
    step: int | None = None
    delay_days: int = 0
    label: str = ""
    subject: str = ""
    plain: str = ""
    html: str = ""
    attach_presentation: bool = False


class PackLettersBody(BaseModel):
    steps: list[PackLetterStepBody] = Field(..., min_length=1)


def _sync_step1_settings(pack: dict[str, Any], *, attach: bool | None = None) -> dict[str, str]:
    """Mirror letter 1 into campaign settings used by batch send."""
    steps = list(pack.get("steps") or [])
    step1 = steps[0] if steps else {}
    attach_flag = (
        attach
        if attach is not None
        else bool(step1.get("attach_presentation") or pack.get("attach_presentation_default"))
    )
    return {
        "OUTREACH_SEQUENCE_PACK": pack["id"],
        "OUTREACH_SUBJECT": str(step1.get("subject") or ""),
        "OUTREACH_TEMPLATE_PLAIN": str(step1.get("plain") or ""),
        "OUTREACH_TEMPLATE_HTML": str(step1.get("html") or ""),
        "OUTREACH_ATTACH_PRESENTATION": "true" if attach_flag else "false",
        "OUTREACH_PRESENTATION_PDF": pack.get("presentation")
        or "quantum_payouts_presentation_small.pdf",
        "SEQUENCES_ENABLED": "true",
    }


@app.get("/api/packs", dependencies=[Depends(require_ui_auth)])
def api_packs() -> dict[str, Any]:
    items = list_packs()
    drafts = _drafts()
    for it in items:
        it["presentation_meta"] = presentation_meta(it.get("id"))
        it["has_draft"] = drafts.has_draft(it.get("id") or "")
    return {"ok": True, "items": items}


@app.get("/api/packs/{pack_id}", dependencies=[Depends(require_ui_auth)])
def api_pack_get(pack_id: str) -> dict[str, Any]:
    pack = resolve_pack(pack_id, _drafts())
    if not pack:
        raise HTTPException(status_code=404, detail="unknown pack")
    tpl = pack_letters_payload(pack)
    tpl["presentation_meta"] = presentation_meta(tpl.get("pack_id"))
    return {"ok": True, "pack": tpl}


@app.put("/api/packs/{pack_id}/letters", dependencies=[Depends(require_ui_auth)])
def api_pack_letters_save(pack_id: str, body: PackLettersBody) -> dict[str, Any]:
    base = get_pack(pack_id)
    if not base:
        raise HTTPException(status_code=404, detail="unknown pack")
    try:
        steps = normalize_steps([s.model_dump() for s in body.steps])
        saved = _drafts().save_steps(base["id"], steps)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    pack = dict(base)
    pack["steps"] = saved
    pack["has_draft"] = True
    tpl = pack_letters_payload(pack)
    tpl["presentation_meta"] = presentation_meta(tpl.get("pack_id"))
    # If this pack is active (or none set), sync letter 1 into campaign settings
    rt = _rt()
    active = (rt.get("OUTREACH_SEQUENCE_PACK", "") or "").strip()
    updated: dict[str, str] = {}
    if not active or active == base["id"]:
        updated = rt.set_many(_sync_step1_settings(pack))
    return {
        "ok": True,
        "pack": tpl,
        "updated": sorted(updated.keys()),
        "settings": rt.snapshot() if updated else None,
    }


@app.post("/api/packs/{pack_id}/letters/reset", dependencies=[Depends(require_ui_auth)])
def api_pack_letters_reset(pack_id: str) -> dict[str, Any]:
    base = get_pack(pack_id)
    if not base:
        raise HTTPException(status_code=404, detail="unknown pack")
    cleared = _drafts().clear(base["id"])
    pack = resolve_pack(base["id"], _drafts()) or base
    tpl = pack_letters_payload(pack)
    tpl["presentation_meta"] = presentation_meta(tpl.get("pack_id"))
    rt = _rt()
    active = (rt.get("OUTREACH_SEQUENCE_PACK", "") or "").strip()
    updated: dict[str, str] = {}
    if active == base["id"]:
        updated = rt.set_many(_sync_step1_settings(pack))
    return {
        "ok": True,
        "cleared": cleared,
        "pack": tpl,
        "updated": sorted(updated.keys()),
        "settings": rt.snapshot() if updated else None,
    }


@app.get("/api/packs/{pack_id}/presentation", dependencies=[Depends(require_ui_auth)])
def api_pack_presentation_meta(pack_id: str) -> dict[str, Any]:
    if not get_pack(pack_id):
        raise HTTPException(status_code=404, detail="unknown pack")
    return {"ok": True, "presentation": presentation_meta(pack_id)}


@app.post("/api/packs/{pack_id}/presentation", dependencies=[Depends(require_ui_auth)])
async def api_pack_presentation_upload(
    pack_id: str,
    file: UploadFile = File(...),
) -> dict[str, Any]:
    pack = get_pack(pack_id)
    if not pack:
        raise HTTPException(status_code=404, detail="unknown pack")
    raw = await file.read()
    try:
        meta = save_presentation(pack["id"], raw, original_name=file.filename or "")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # Point active campaign at this pack slot if it is the selected industry
    rt = _rt()
    active = (rt.get("OUTREACH_SEQUENCE_PACK", "") or "").strip()
    if active == pack["id"]:
        rt.set_many({"OUTREACH_PRESENTATION_PDF": f"presentations/{pack['id']}.pdf"})
    return {"ok": True, "presentation": meta, "pack_id": pack["id"]}


@app.delete("/api/packs/{pack_id}/presentation", dependencies=[Depends(require_ui_auth)])
def api_pack_presentation_reset(pack_id: str) -> dict[str, Any]:
    pack = get_pack(pack_id)
    if not pack:
        raise HTTPException(status_code=404, detail="unknown pack")
    try:
        meta = reset_presentation(pack["id"])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "presentation": meta, "pack_id": pack["id"]}


@app.post("/api/packs/apply", dependencies=[Depends(require_ui_auth)])
def api_packs_apply(body: ApplyPackBody) -> dict[str, Any]:
    """Activate industry pack: sync letter 1 + keep/restore draft chain."""
    base = get_pack(body.pack_id)
    if not base:
        raise HTTPException(status_code=404, detail="unknown pack")
    if body.reset_draft:
        _drafts().clear(base["id"])
    pack = resolve_pack(base["id"], _drafts()) or base
    attach = (
        body.attach_presentation
        if body.attach_presentation is not None
        else bool(
            (pack["steps"][0].get("attach_presentation") if pack.get("steps") else False)
            or pack.get("attach_presentation_default")
        )
    )
    updated = _rt().set_many(_sync_step1_settings(pack, attach=attach))
    tpl = pack_letters_payload(pack)
    tpl["presentation_meta"] = presentation_meta(tpl.get("pack_id"))
    return {
        "ok": True,
        "updated": sorted(updated.keys()),
        "pack": tpl,
        "settings": _rt().snapshot(),
    }


@app.post("/api/auth/login")
async def api_login(request: Request) -> JSONResponse:
    """Exchange token for cookie (UI helper). Body: {"token":"..."}"""
    try:
        payload = await request.json()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="JSON required") from exc
    token = str((payload or {}).get("token") or "").strip()
    expected = (os.getenv("OUTREACH_UI_TOKEN") or "").strip() or _ensure_ui_token()
    if not token or not secrets.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="bad token")
    resp = JSONResponse({"ok": True})
    resp.set_cookie(
        "outreach_token",
        token,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 30,
        path="/",
    )
    return resp


# --- static UI + brand assets ---
# custom.png route is registered above; packaged assets follow.

if ASSETS_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")

if STATIC_DIR.is_dir():
    app.mount("/ui", StaticFiles(directory=str(STATIC_DIR), html=True), name="ui")


@app.get("/ui")
def ui_redirect() -> RedirectResponse:
    return RedirectResponse(url="/ui/")


def _print(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def cli_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AVA Bitrix outreach CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="Show outbox / config status")
    sub.add_parser("sync", help="Download Bitrix → local clients.db + refresh outbox")
    sub.add_parser("rebuild-outbox", help="Rebuild outbox from local clients.db (no Bitrix)")
    sub.add_parser(
        "backfill-geo",
        help="Backfill city/timezone + director first/patronymic from DaData cache",
    )

    p_dry = sub.add_parser("dry-run", help="Preview N pending without SMTP")
    p_dry.add_argument("n", nargs="?", type=int, default=5)
    p_dry.add_argument("--email", dest="only_email", default=None)

    p_send = sub.add_parser("send-batch", help="Send up to N emails (requires OUTREACH_ENABLED)")
    p_send.add_argument("n", type=int)
    p_send.add_argument(
        "--email",
        dest="only_email",
        default=None,
        help="Send only to this pending email (safe test mode)",
    )

    p_one = sub.add_parser("send-one", help="One-shot send to explicit address (no OUTREACH_ENABLED)")
    p_one.add_argument("email")
    p_one.add_argument("--name", dest="contact_name", default=None)
    p_one.add_argument("--dry-run", action="store_true")

    sub.add_parser("check-replies", help="Poll office@ IMAP for replies to outreach")
    p_smoke = sub.add_parser("bitrix-smoke", help="crm.company.list + crm.contact.list smoke")
    sub.add_parser("ui-token", help="Print / generate OUTREACH_UI_TOKEN")
    args = parser.parse_args(argv)

    # Ensure settings DB for CLI paths that use runtime overrides
    _rt()

    if args.cmd == "ui-token":
        print(_ensure_ui_token())
        return 0

    if args.cmd == "status":
        _print(_status_payload())
        return 0

    if args.cmd == "bitrix-smoke":
        client = _bitrix_or_none()
        if client is None:
            print(
                "BITRIX_WEBHOOK_URL missing. Need incoming webhook URL with crm rights "
                f"for portal {os.getenv('BITRIX_PORTAL_URL', 'https://b24-m5614z.bitrix24.ru/')}",
                file=sys.stderr,
            )
            return 2
        try:
            _print(
                {
                    "ok": True,
                    "company_total": client.smoke_company_count(),
                    "contact_total": client.smoke_contact_count(),
                }
            )
            return 0
        finally:
            client.close()

    if args.cmd == "sync":
        client = _bitrix_or_none()
        if client is None:
            print(
                "BITRIX_WEBHOOK_URL missing — set in .env (incoming webhook, crm).",
                file=sys.stderr,
            )
            return 2
        try:
            _clients_mod.store.init_db()
            clients_report = sync_from_bitrix(_clients_mod.store, client)
            outbox_report = rebuild_outbox_from_clients(_clients_mod.store, _store())
            _print(
                {
                    "ok": bool(clients_report.get("ok")),
                    "clients": clients_report,
                    "outbox_rebuild": outbox_report,
                }
            )
            return 0 if clients_report.get("ok") else 1
        finally:
            client.close()

    if args.cmd == "rebuild-outbox":
        _clients_mod.store.init_db()
        _print(rebuild_outbox_from_clients(_clients_mod.store, _store()))
        return 0

    if args.cmd == "backfill-geo":
        _clients_mod.store.init_db()
        report = backfill_company_geo_and_fio(_clients_mod.store)
        report["stats"] = geo_stats(_clients_mod.store)
        _print(report)
        return 0

    if args.cmd == "check-replies":
        bitrix = _bitrix_or_none()
        try:
            _print(check_replies(_store(), bitrix))
            return 0
        finally:
            if bitrix:
                bitrix.close()

    if args.cmd == "dry-run":
        _print(
            send_batch(
                _store(),
                limit=args.n,
                dry_run=True,
                bitrix=None,
                only_email=args.only_email,
                settings=_rt(),
                tracking=_tracking_mod.store,
                deliverability=_deliver_mod.store,
            )
        )
        return 0

    if args.cmd == "send-one":
        _tracking_mod.store.init_db()
        _deliver_mod.store.init_db()
        result = send_one(
            _store(),
            to=args.email,
            contact_name=args.contact_name,
            dry_run=bool(args.dry_run),
            settings=_rt(),
            tracking=_tracking_mod.store,
            deliverability=_deliver_mod.store,
        )
        _print(result)
        return 0 if result.get("ok") else 1

    if args.cmd == "send-batch":
        bitrix = _bitrix_or_none()
        try:
            result = send_batch(
                _store(),
                limit=args.n,
                dry_run=False,
                bitrix=bitrix,
                only_email=args.only_email,
                settings=_rt(),
                tracking=_tracking_mod.store,
                deliverability=_deliver_mod.store,
            )
            _print(result)
            return 0 if result.get("ok") else 1
        finally:
            if bitrix:
                bitrix.close()

    return 1


if __name__ == "__main__":
    raise SystemExit(cli_main())
