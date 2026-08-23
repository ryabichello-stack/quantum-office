"""Content Studio MVP — objection → draft content pack (APPROVAL_REQUIRED).

Does not auto-publish. Wraps existing industry packs as templates.
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

logger = logging.getLogger("ava-outreach.content_studio")

DEFAULT_TENANT = "quantum-labs"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


class ContentStudioStore:
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
                CREATE TABLE IF NOT EXISTS content_drafts (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT 'manual',
                    objection TEXT NOT NULL DEFAULT '',
                    industry_pack TEXT,
                    status TEXT NOT NULL DEFAULT 'draft',
                    body_json TEXT NOT NULL DEFAULT '{}',
                    citations_json TEXT NOT NULL DEFAULT '[]',
                    account_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    approved_at TEXT
                );
                CREATE INDEX IF NOT EXISTS ix_content_drafts_status
                    ON content_drafts(tenant_id, status);
                """
            )

    def draft_from_objection(
        self,
        *,
        objection: str,
        industry_pack: str | None = "lombards",
        title: str = "",
        account_id: str | None = None,
        source: str = "call_objection",
    ) -> dict[str, Any]:
        now = _utc_now()
        did = _new_id()
        obj = (objection or "").strip()
        pack_id = (industry_pack or "lombards").strip()
        letters = []
        try:
            from content.packs import get_pack

            pack = get_pack(pack_id) or get_pack("lombards")
            if pack:
                for i, step in enumerate(pack.get("steps") or pack.get("letters") or [], 1):
                    if isinstance(step, dict):
                        letters.append(
                            {
                                "step": i,
                                "subject": step.get("subject") or f"Шаг {i}",
                                "plain": step.get("plain") or step.get("body") or "",
                            }
                        )
        except Exception:  # noqa: BLE001
            letters = []

        if not letters:
            letters = [
                {
                    "step": 1,
                    "subject": "Ответ на возражение",
                    "plain": (
                        f"Спасибо за обратную связь.\n\n"
                        f"По поводу «{obj[:200]}» — кратко:\n"
                        f"[уточните факт из Second Brain / product profile]\n\n"
                        f"С уважением,\nQuantum Labs"
                    ),
                }
            ]

        # Light personalization: prepend objection framing to step 1
        if letters and obj:
            letters[0]["plain"] = (
                f"(Контекст возражения: {obj[:300]})\n\n" + (letters[0].get("plain") or "")
            )

        citations: list[dict[str, Any]] = []
        try:
            from knowledge_client import fetch_reply_citations

            citations = fetch_reply_citations(query=obj or "Quantum Labs payouts", limit=3)
        except Exception:  # noqa: BLE001
            pass
        if not citations:
            citations = [
                {
                    "source": "tenant_config",
                    "ref": "config/tenants/quantum-labs/product_profile.json",
                    "note": "Approve before publish",
                    "approval_required": True,
                }
            ]

        body = {
            "approval_required": True,
            "industry_pack": pack_id,
            "letters": letters,
            "objection": obj,
        }
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO content_drafts(
                    id, tenant_id, title, source, objection, industry_pack,
                    status, body_json, citations_json, account_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'draft', ?, ?, ?, ?, ?)
                """,
                (
                    did,
                    self.tenant_id,
                    title or f"Ответ: {obj[:60]}" or "Content draft",
                    source,
                    obj,
                    pack_id,
                    json.dumps(body, ensure_ascii=False),
                    json.dumps(citations, ensure_ascii=False),
                    account_id,
                    now,
                    now,
                ),
            )
        try:
            from usage_meter import UsageMeter
            UsageMeter(self.db_path, tenant_id=self.tenant_id).incr("content_drafts")
        except Exception:
            pass
        return self.get(did) or {"id": did}

    def get(self, draft_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM content_drafts WHERE id = ? AND tenant_id = ?",
                (draft_id, self.tenant_id),
            ).fetchone()
        if not row:
            return None
        out = dict(row)
        for key in ("body_json", "citations_json"):
            try:
                out[key.replace("_json", "")] = json.loads(out.get(key) or "{}")
            except json.JSONDecodeError:
                out[key.replace("_json", "")] = {} if "body" in key else []
        return out

    def list_drafts(self, *, status: str | None = None, limit: int = 40) -> list[dict[str, Any]]:
        q = "SELECT * FROM content_drafts WHERE tenant_id = ?"
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
                item["body"] = json.loads(item.get("body_json") or "{}")
                item["citations"] = json.loads(item.get("citations_json") or "[]")
            except json.JSONDecodeError:
                item["body"] = {}
                item["citations"] = []
            out.append(item)
        return out

    def set_status(self, draft_id: str, status: str) -> dict[str, Any] | None:
        allowed = {"draft", "pending_approval", "approved", "rejected", "published"}
        if status not in allowed:
            raise ValueError(f"invalid status: {status}")
        now = _utc_now()
        approved_at = now if status == "approved" else None
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE content_drafts
                SET status = ?, updated_at = ?,
                    approved_at = COALESCE(?, approved_at)
                WHERE id = ? AND tenant_id = ?
                """,
                (status, now, approved_at, draft_id, self.tenant_id),
            )
        return self.get(draft_id)


class ContentStudioModule:
    name = "content_studio"
    version = "0.1.0"

    def __init__(self) -> None:
        self.store = ContentStudioStore()

    def init_db(self) -> None:
        self.store.init_db()

    def on_startup(self, ctx: AppContext) -> None:
        ctx.extras["content_studio"] = self.store
        logger.info("content_studio ready")

    def on_shutdown(self) -> None:
        return None

    def health(self) -> dict[str, Any]:
        with self.store.connect() as conn:
            n = conn.execute(
                "SELECT COUNT(*) AS n FROM content_drafts WHERE tenant_id = ?",
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
            objection: str = Field(..., min_length=2)
            industry_pack: str | None = "lombards"
            title: str = ""
            account_id: str | None = None
            source: str = "call_objection"

        @router.post("/drafts")
        def create_draft(payload: DraftBody) -> dict[str, Any]:
            row = self.store.draft_from_objection(
                objection=payload.objection,
                industry_pack=payload.industry_pack,
                title=payload.title,
                account_id=payload.account_id,
                source=payload.source,
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
                raise HTTPException(404, "draft_not_found")
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
                raise HTTPException(404, "draft_not_found")
            return {"ok": True, "draft": row}
