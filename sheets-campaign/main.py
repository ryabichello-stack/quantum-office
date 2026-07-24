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


@app.on_event("startup")
def _startup() -> None:
    runner.init_db()
    logger.info(
        "sheets-campaign ready write=%s sa=%s",
        sheets_io.sheets_write_enabled(),
        sheets_io.sa_email(),
    )


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": "ava-sheets-campaign",
        "sheets_write_enabled": sheets_io.sheets_write_enabled(),
        "sa_email": sheets_io.sa_email(),
        "campaign": runner.get_status(),
    }


@app.get("/api/campaign/preview")
def api_preview(
    limit: int = 30,
    sheet: Optional[str] = None,
    x_webhook_token: Optional[str] = Header(None),
):
    _auth(x_webhook_token)
    return runner.preview(limit=max(1, min(limit, 200)), sheet=sheet)


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
