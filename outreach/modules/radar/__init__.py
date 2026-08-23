"""Intent Radar MVP — capture intent signals (no auto-outreach).

Signals are stored for operator review; never triggers cold DM.
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

logger = logging.getLogger("ava-outreach.radar")

DEFAULT_TENANT = "quantum-labs"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


class RadarStore:
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
                CREATE TABLE IF NOT EXISTS intent_signals (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    signal_type TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'manual',
                    company_title TEXT NOT NULL DEFAULT '',
                    bitrix_company_id TEXT,
                    account_id TEXT,
                    summary TEXT NOT NULL DEFAULT '',
                    score REAL NOT NULL DEFAULT 0.5,
                    status TEXT NOT NULL DEFAULT 'new',
                    evidence_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_intent_status
                    ON intent_signals(tenant_id, status, created_at);
                """
            )

    def ingest(
        self,
        *,
        signal_type: str,
        summary: str,
        source: str = "manual",
        company_title: str = "",
        bitrix_company_id: str | None = None,
        account_id: str | None = None,
        score: float = 0.5,
        evidence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = _utc_now()
        sid = _new_id()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO intent_signals(
                    id, tenant_id, signal_type, source, company_title,
                    bitrix_company_id, account_id, summary, score, status,
                    evidence_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', ?, ?, ?)
                """,
                (
                    sid,
                    self.tenant_id,
                    (signal_type or "other").strip()[:80],
                    source[:80],
                    company_title[:200],
                    bitrix_company_id,
                    account_id,
                    (summary or "").strip()[:2000],
                    float(score),
                    json.dumps(evidence or {}, ensure_ascii=False),
                    now,
                    now,
                ),
            )
        return self.get(sid) or {"id": sid}

    def get(self, signal_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM intent_signals WHERE id = ? AND tenant_id = ?",
                (signal_id, self.tenant_id),
            ).fetchone()
        if not row:
            return None
        out = dict(row)
        try:
            out["evidence"] = json.loads(out.get("evidence_json") or "{}")
        except json.JSONDecodeError:
            out["evidence"] = {}
        return out

    def list_signals(self, *, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        q = "SELECT * FROM intent_signals WHERE tenant_id = ?"
        params: list[Any] = [self.tenant_id]
        if status:
            q += " AND status = ?"
            params.append(status)
        q += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(1, min(limit, 200)))
        with self.connect() as conn:
            rows = conn.execute(q, params).fetchall()
        out = []
        for r in rows:
            item = dict(r)
            try:
                item["evidence"] = json.loads(item.get("evidence_json") or "{}")
            except json.JSONDecodeError:
                item["evidence"] = {}
            out.append(item)
        return out

    def set_status(self, signal_id: str, status: str) -> dict[str, Any] | None:
        allowed = {"new", "reviewing", "accepted", "dismissed", "converted"}
        if status not in allowed:
            raise ValueError(f"invalid status: {status}")
        now = _utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE intent_signals SET status = ?, updated_at = ?
                WHERE id = ? AND tenant_id = ?
                """,
                (status, now, signal_id, self.tenant_id),
            )
        return self.get(signal_id)

    def verify_and_suggest_action(self, signal_id: str) -> dict[str, Any]:
        """Rules-first: high score → LPR search / enroll suggestion (never auto-send)."""
        sig = self.get(signal_id)
        if not sig:
            return {"ok": False, "error": "not_found"}
        score = float(sig.get("score") or 0)
        action = "review"
        if score >= 0.7:
            action = "run_lpr_search"
        elif score >= 0.4:
            action = "enrich_account"
        return {
            "ok": True,
            "signal": sig,
            "suggested_action": action,
            "auto_outreach": False,
            "approval_required": True,
        }


class RadarModule:
    name = "radar"
    version = "0.1.0"

    def __init__(self) -> None:
        self.store = RadarStore()

    def init_db(self) -> None:
        self.store.init_db()

    def on_startup(self, ctx: AppContext) -> None:
        ctx.extras["radar"] = self.store
        logger.info("radar ready")

    def on_shutdown(self) -> None:
        return None

    def health(self) -> dict[str, Any]:
        with self.store.connect() as conn:
            n = conn.execute(
                "SELECT COUNT(*) AS n FROM intent_signals WHERE tenant_id = ?",
                (self.store.tenant_id,),
            ).fetchone()["n"]
        return {"ok": True, "signals": int(n)}

    def register_routes(self, router: Any) -> None:
        from fastapi import HTTPException, Query
        from pydantic import BaseModel, Field

        @router.get("/health")
        def health() -> dict[str, Any]:
            return self.health()

        class IngestBody(BaseModel):
            signal_type: str = Field(..., min_length=2, max_length=80)
            summary: str = Field(..., min_length=2)
            source: str = "manual"
            company_title: str = ""
            bitrix_company_id: str | None = None
            account_id: str | None = None
            score: float = 0.5
            evidence: dict[str, Any] | None = None

        @router.post("/signals")
        def ingest(payload: IngestBody) -> dict[str, Any]:
            row = self.store.ingest(
                signal_type=payload.signal_type,
                summary=payload.summary,
                source=payload.source,
                company_title=payload.company_title,
                bitrix_company_id=payload.bitrix_company_id,
                account_id=payload.account_id,
                score=payload.score,
                evidence=payload.evidence,
            )
            return {"ok": True, "signal": row}

        @router.get("/signals")
        def list_signals(
            status: str | None = None, limit: int = Query(50, ge=1, le=200)
        ) -> dict[str, Any]:
            return {"ok": True, "items": self.store.list_signals(status=status, limit=limit)}

        class StatusBody(BaseModel):
            status: str

        @router.post("/signals/{signal_id}/status")
        def set_status(signal_id: str, payload: StatusBody) -> dict[str, Any]:
            try:
                row = self.store.set_status(signal_id, payload.status)
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            if not row:
                raise HTTPException(404, "not_found")
            return {"ok": True, "signal": row}

        @router.post("/signals/{signal_id}/verify")
        def verify(signal_id: str) -> dict[str, Any]:
            out = self.store.verify_and_suggest_action(signal_id)
            if not out.get("ok"):
                raise HTTPException(404, out.get("error") or "not_found")
            return out
