"""
ava-files — file broker: fetch from sources, deliver via email/Telegram.

Sources: local (allowlisted), github repo, Yandex Disk, Mail.ru Cloud (WebDAV).
Does not own Bitrix outreach, Asterisk, or Polyhub trading.
"""

from __future__ import annotations

import logging
import os
from typing import Literal, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

load_dotenv()

import delivery
import sources
from models import SourceError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("ava-files")

WEBHOOK_TOKEN = os.getenv("WEBHOOK_TOKEN", "").strip()
SERVICE_NAME = "ava-files"

app = FastAPI(title="Quantum Labs Files", version="0.1.0")


def _check_token(x_webhook_token: Optional[str] = None) -> None:
    if not WEBHOOK_TOKEN:
        return
    if (x_webhook_token or "").strip() != WEBHOOK_TOKEN:
        raise HTTPException(status_code=401, detail="unauthorized")


class FileSendRequest(BaseModel):
    source: Literal["local", "repo", "github", "yadisk", "yandex", "mailru"] = Field(
        ...,
        description="Where to read the file from",
    )
    path: str = Field(..., min_length=1, max_length=1000)
    via: Literal["email", "telegram", "mail", "tg"] = Field(
        ...,
        description="Delivery channel",
    )
    to: str = Field(..., min_length=1, max_length=200, description="email or telegram chat_id")
    caption: str = Field(default="", max_length=1000)
    subject: str = Field(default="", max_length=200, description="email subject only")
    ref: Optional[str] = Field(default=None, description="git ref for repo source")
    repo: Optional[str] = Field(default=None, description="owner/name override for repo source")


class FileFetchRequest(BaseModel):
    source: Literal["local", "repo", "github", "yadisk", "yandex", "mailru"]
    path: str = Field(..., min_length=1, max_length=1000)
    ref: Optional[str] = None
    repo: Optional[str] = None


class FileListRequest(BaseModel):
    source: Literal["local", "yadisk", "yandex", "mailru"] = Field(
        default="mailru",
        description="Cloud/local source to browse",
    )
    path: str = Field(default="/", max_length=1000, description="Directory path, default root")


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": SERVICE_NAME,
        "sources": sources.sources_status(),
        "delivery": delivery.delivery_status(),
    }


@app.post("/api/files/list")
def files_list(
    req: FileListRequest,
    x_webhook_token: Optional[str] = Header(None),
):
    """List folders and files in one directory level (browse / drill-down)."""
    _check_token(x_webhook_token)
    path = (req.path or "/").strip() or "/"
    try:
        entries = sources.list_entries(req.source, path)
    except SourceError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": exc.code, "message": exc.message},
        ) from exc
    dirs = [e for e in entries if e.type == "dir"]
    files = [e for e in entries if e.type == "file"]
    return {
        "ok": True,
        "source": req.source,
        "path": path if path.startswith("/") or req.source == "local" else f"/{path}",
        "account": (sources.sources_status().get("mailru_user") if req.source == "mailru" else None),
        "dirs": [{"name": e.name, "path": e.path, "type": "dir"} for e in dirs],
        "files": [
            {
                "name": e.name,
                "path": e.path,
                "type": "file",
                "bytes": e.bytes,
            }
            for e in files
        ],
        "entries": [
            {
                "name": e.name,
                "path": e.path,
                "type": e.type,
                "bytes": e.bytes,
            }
            for e in entries
        ],
        "counts": {"dirs": len(dirs), "files": len(files), "total": len(entries)},
    }


@app.post("/api/files/fetch")
def files_fetch(
    req: FileFetchRequest,
    x_webhook_token: Optional[str] = Header(None),
):
    """Resolve/fetch metadata (does not deliver). Returns size + filename, not raw bytes."""
    _check_token(x_webhook_token)
    try:
        f = sources.fetch(req.source, req.path, ref=req.ref, repo=req.repo)
    except SourceError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.code, "message": exc.message}) from exc
    return {
        "ok": True,
        "filename": f.filename,
        "bytes": len(f.content),
        "content_type": f.content_type,
        "source": f.source,
        "path": f.path,
    }


@app.post("/api/files/send")
def files_send(
    req: FileSendRequest,
    x_webhook_token: Optional[str] = Header(None),
):
    """Fetch file from source and send via email or Telegram."""
    _check_token(x_webhook_token)
    try:
        f = sources.fetch(req.source, req.path, ref=req.ref, repo=req.repo)
    except SourceError as exc:
        logger.warning("fetch failed: %s %s", exc.code, exc.message)
        return {
            "ok": False,
            "sent": False,
            "error": exc.code,
            "message": exc.message,
        }

    ok, err = delivery.deliver(
        req.via,
        req.to,
        f,
        caption=req.caption,
        subject=req.subject,
    )
    if not ok:
        return {
            "ok": False,
            "sent": False,
            "error": err or "delivery_failed",
            "message": f"Не удалось отправить {f.filename}",
            "filename": f.filename,
            "bytes": len(f.content),
            "source": f.source,
        }

    return {
        "ok": True,
        "sent": True,
        "filename": f.filename,
        "bytes": len(f.content),
        "content_type": f.content_type,
        "source": f.source,
        "path": f.path,
        "via": req.via,
        "to": req.to,
        "message": f"Отправлено: {f.filename} → {req.via}:{req.to}",
    }
