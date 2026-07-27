"""ava-sheets-campaign — dial Google Sheet leads about mass payouts."""

from __future__ import annotations

import logging
import os
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

load_dotenv()

import runner
import script_store
import sheets_io

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("ava-sheets-campaign")

WEBHOOK_TOKEN = os.getenv("WEBHOOK_TOKEN", "").strip()
app = FastAPI(title="Quantum Labs Sheets Campaign", version="0.1.0")


def _auth(x_webhook_token: Optional[str] = None) -> None:
    if not WEBHOOK_TOKEN:
        return
    if (x_webhook_token or "").strip() != WEBHOOK_TOKEN:
        raise HTTPException(status_code=401, detail="unauthorized")


class StartRequest(BaseModel):
    max_calls: int = Field(default=5, ge=0, le=200)
    sheet: Optional[str] = Field(
        default=None,
        description="Optional filter: sheet name or gid",
    )
    dry_run: Optional[bool] = None


class ScriptUpdate(BaseModel):
    greeting: Optional[str] = None
    script: Optional[str] = None
    tools: Optional[list[str]] = None


@app.on_event("startup")
def _startup() -> None:
    runner.init_db()
    runner.recover_after_restart()
    play = script_store.load_script()
    logger.info(
        "sheets-campaign ready write=%s sa=%s script_source=%s",
        sheets_io.sheets_write_enabled(),
        sheets_io.sa_email(),
        play.get("source"),
    )


@app.on_event("shutdown")
def _shutdown() -> None:
    runner.request_shutdown(timeout=25.0)


@app.get("/health")
def health():
    play = script_store.load_script()
    return {
        "ok": True,
        "service": "ava-sheets-campaign",
        "sheets_write_enabled": sheets_io.sheets_write_enabled(),
        "sa_email": sheets_io.sa_email(),
        "script_source": play.get("source"),
        "campaign": runner.get_status(),
    }


@app.get("/api/campaign/script")
def api_get_script(x_webhook_token: Optional[str] = Header(None)):
    """Greeting + full conversation playbook used for sheet dials."""
    _auth(x_webhook_token)
    doc = script_store.load_script()
    return {"ok": True, **doc}


@app.put("/api/campaign/script")
def api_put_script(body: ScriptUpdate, x_webhook_token: Optional[str] = Header(None)):
    _auth(x_webhook_token)
    doc = script_store.save_script(
        greeting=body.greeting,
        script=body.script,
        tools=body.tools,
    )
    return {"ok": True, **doc}


@app.post("/api/campaign/script/reset")
def api_reset_script(x_webhook_token: Optional[str] = Header(None)):
    _auth(x_webhook_token)
    doc = script_store.reset_script()
    return {"ok": True, **doc}


@app.get("/api/campaign/preview")
def api_preview(
    limit: int = 30,
    sheet: Optional[str] = None,
    x_webhook_token: Optional[str] = Header(None),
):
    _auth(x_webhook_token)
    return runner.preview(limit=max(1, min(limit, 200)), sheet=sheet)


@app.get("/api/campaign/results")
def api_results(
    limit: int = 50,
    x_webhook_token: Optional[str] = Header(None),
):
    """Local dial results from campaign.db (even when Sheets writeback is off)."""
    _auth(x_webhook_token)
    return runner.list_results(limit=max(1, min(limit, 500)))


@app.get("/api/campaign/status")
def api_status(x_webhook_token: Optional[str] = Header(None)):
    _auth(x_webhook_token)
    return {"ok": True, **runner.get_status()}


@app.post("/api/campaign/start")
def api_start(body: StartRequest, x_webhook_token: Optional[str] = Header(None)):
    _auth(x_webhook_token)
    return runner.start_campaign(
        max_calls=body.max_calls,
        sheet=body.sheet,
        dry_run=body.dry_run,
    )


@app.post("/api/campaign/stop")
def api_stop(x_webhook_token: Optional[str] = Header(None)):
    _auth(x_webhook_token)
    return runner.stop_campaign()


@app.post("/api/campaign/flush-writebacks")
def api_flush(x_webhook_token: Optional[str] = Header(None)):
    _auth(x_webhook_token)
    return runner.flush_writebacks()


class GoogleSaBody(BaseModel):
    """Paste Google Cloud service-account JSON to enable Sheet writeback."""

    service_account: dict = Field(
        ...,
        alias="json",
        description="Full service account key JSON object",
    )

    model_config = {"populate_by_name": True}


@app.get("/api/campaign/writeback")
def api_writeback_status(x_webhook_token: Optional[str] = Header(None)):
    _auth(x_webhook_token)
    return {"ok": True, **sheets_io.write_status()}


@app.post("/api/campaign/google-sa")
def api_install_google_sa(body: GoogleSaBody, x_webhook_token: Optional[str] = Header(None)):
    _auth(x_webhook_token)
    result = sheets_io.install_service_account(body.service_account)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "install_failed")
    flushed = runner.flush_writebacks(limit=200)
    result["flush"] = flushed
    return result
