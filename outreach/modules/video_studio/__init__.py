"""Video Studio MVP — private draft + APPROVAL_REQUIRED (no auto-publish).

Scaffold only: stores video job specs. YouTube private upload comes later.
"""

import json
import logging
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from core.paths import MODULES_DB
from core.registry import AppContext

logger = logging.getLogger("ava-outreach.video_studio")

DEFAULT_TENANT = "quantum-labs"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


class VideoStudioStore:
    def __init__(self, db_path: Path | None = None, *, tenant_id: str = DEFAULT_TENANT) -> None:
        self.db_path = Path(db_path or MODULES_DB)
        self.tenant_id = (tenant_id or DEFAULT_TENANT).strip() or DEFAULT_TENANT
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS video_drafts (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    brief TEXT NOT NULL DEFAULT '',
                    script_text TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'draft',
                    visibility TEXT NOT NULL DEFAULT 'private',
                    youtube_id TEXT,
                    content_draft_id TEXT,
                    account_id TEXT,
                    meta_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    approved_at TEXT
                );
                CREATE INDEX IF NOT EXISTS ix_video_drafts_status
                    ON video_drafts(tenant_id, status);
                """
            )

    def create_draft(
        self,
        *,
        title: str,
        brief: str = "",
        script_text: str = "",
        content_draft_id: str | None = None,
        account_id: str | None = None,
    ) -> dict[str, Any]:
        now = _utc_now()
        vid = _new_id()
        script = (script_text or "").strip()
        if not script and brief:
            script = (
                f"Черновик ролика (private).\n\n"
                f"Бриф: {brief.strip()[:500]}\n\n"
                f"[утвердите сценарий перед генерацией / загрузкой]"
            )
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO video_drafts(
                    id, tenant_id, title, brief, script_text, status, visibility,
                    content_draft_id, account_id, meta_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'draft', 'private', ?, ?, ?, ?, ?)
                """,
                (
                    vid,
                    self.tenant_id,
                    (title or "Video draft").strip()[:200],
                    (brief or "").strip()[:2000],
                    script[:20000],
                    content_draft_id,
                    account_id,
                    json.dumps(
                        {"approval_required": True, "youtube_upload": False},
                        ensure_ascii=False,
                    ),
                    now,
                    now,
                ),
            )
        return self.get(vid) or {"id": vid}

    def get(self, draft_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM video_drafts WHERE id = ? AND tenant_id = ?",
                (draft_id, self.tenant_id),
            ).fetchone()
        if not row:
            return None
        out = dict(row)
        try:
            out["meta"] = json.loads(out.get("meta_json") or "{}")
        except json.JSONDecodeError:
            out["meta"] = {}
        return out

    def list_drafts(self, *, status: str | None = None, limit: int = 40) -> list[dict[str, Any]]:
        q = "SELECT * FROM video_drafts WHERE tenant_id = ?"
        params: list[Any] = [self.tenant_id]
        if status:
            q += " AND status = ?"
            params.append(status)
        q += " ORDER BY updated_at DESC LIMIT ?"
        params.append(max(1, min(limit, 200)))
        with self.connect() as conn:
            rows = conn.execute(q, params).fetchall()
        out = []
        for r in rows:
            item = dict(r)
            try:
                item["meta"] = json.loads(item.get("meta_json") or "{}")
            except json.JSONDecodeError:
                item["meta"] = {}
            out.append(item)
        return out

    def set_status(self, draft_id: str, status: str) -> dict[str, Any] | None:
        allowed = {
            "draft",
            "pending_approval",
            "approved",
            "rejected",
            "rendering",
            "uploaded_private",
            "published",
        }
        if status not in allowed:
            raise ValueError(f"invalid status: {status}")
        now = _utc_now()
        approved_at = now if status == "approved" else None
        # Never auto-publish: uploaded_private is the max without explicit publish
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE video_drafts
                SET status = ?, updated_at = ?,
                    approved_at = COALESCE(?, approved_at)
                WHERE id = ? AND tenant_id = ?
                """,
                (status, now, approved_at, draft_id, self.tenant_id),
            )
        return self.get(draft_id)

    def queue_private_upload(self, draft_id: str) -> dict[str, Any]:
        """Mark as ready for private YouTube upload — does not call YouTube yet."""
        row = self.get(draft_id)
        if not row:
            return {"ok": False, "error": "not_found"}
        if row.get("status") not in ("approved", "pending_approval", "draft"):
            return {"ok": False, "error": "invalid_status"}
        if row.get("status") != "approved":
            return {
                "ok": False,
                "error": "approval_required",
                "message": "Сначала утвердите черновик (APPROVAL_REQUIRED)",
            }
        updated = self.set_status(draft_id, "uploaded_private")
        return {
            "ok": True,
            "draft": updated,
            "youtube_upload": False,
            "note": "Заглушка: private YouTube upload подключится на следующем шаге",
        }


class VideoStudioModule:
    name = "video_studio"
    version = "0.1.0"

    def __init__(self) -> None:
        self.store = VideoStudioStore()

    def init_db(self) -> None:
        self.store.init_db()

    def on_startup(self, ctx: AppContext) -> None:
        ctx.extras["video_studio"] = self.store
        logger.info("video_studio ready")

    def on_shutdown(self) -> None:
        return None

    def health(self) -> dict[str, Any]:
        with self.store.connect() as conn:
            n = conn.execute(
                "SELECT COUNT(*) AS n FROM video_drafts WHERE tenant_id = ?",
                (self.store.tenant_id,),
            ).fetchone()["n"]
        return {"ok": True, "drafts": int(n)}

    def register_routes(self, router: Any) -> None:
        from fastapi import HTTPException, Query
        from pydantic import BaseModel, Field

        @router.get("/health")
        def health() -> dict[str, Any]:
            return self.health()

        class DraftBody(BaseModel):
            title: str = Field(..., min_length=2, max_length=200)
            brief: str = ""
            script_text: str = ""
            content_draft_id: str | None = None
            account_id: str | None = None

        @router.post("/drafts")
        def create_draft(payload: DraftBody) -> dict[str, Any]:
            row = self.store.create_draft(
                title=payload.title,
                brief=payload.brief,
                script_text=payload.script_text,
                content_draft_id=payload.content_draft_id,
                account_id=payload.account_id,
            )
            return {"ok": True, "draft": row}

        @router.get("/drafts")
        def list_drafts(
            status: str | None = None, limit: int = Query(40, ge=1, le=200)
        ) -> dict[str, Any]:
            return {"ok": True, "items": self.store.list_drafts(status=status, limit=limit)}

        @router.get("/drafts/{draft_id}")
        def get_draft(draft_id: str) -> dict[str, Any]:
            row = self.store.get(draft_id)
            if not row:
                raise HTTPException(404, "not_found")
            return {"ok": True, "draft": row}

        class StatusBody(BaseModel):
            status: str = Field(..., min_length=2, max_length=40)

        @router.post("/drafts/{draft_id}/status")
        def set_status(draft_id: str, payload: StatusBody) -> dict[str, Any]:
            try:
                row = self.store.set_status(draft_id, payload.status)
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            if not row:
                raise HTTPException(404, "not_found")
            return {"ok": True, "draft": row}

        @router.post("/drafts/{draft_id}/queue-private-upload")
        def queue_upload(draft_id: str) -> dict[str, Any]:
            out = self.store.queue_private_upload(draft_id)
            if not out.get("ok"):
                raise HTTPException(400, out.get("error") or "failed")
            return out
