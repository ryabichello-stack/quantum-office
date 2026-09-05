"""delno-knowledge — Second Brain API only (no legacy ava-knowledge store)."""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("delno-knowledge")

BRAIN_ENABLED = os.getenv("BRAIN_ENABLED", "true").lower() not in ("0", "false", "no", "off")

app = FastAPI(title="delno-knowledge", version="0.1.0")


@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "service": "delno-knowledge",
        "brain_enabled": BRAIN_ENABLED,
    }


if BRAIN_ENABLED:
    from brain_platform.api.router import router as brain_router

    app.include_router(brain_router)
    logger.info("Second Brain router mounted at /api/brain/*")
