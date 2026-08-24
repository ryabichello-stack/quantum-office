"""Revenue Orchestrator — journeys wrapping sequences (rules-first, Stage 4 scaffold).

Does not replace SequenceStore; enrolls accounts/emails into versioned journeys
and applies global guardrails + stop-on-reply.
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

logger = logging.getLogger("ava-outreach.orchestrator")

DEFAULT_TENANT = "quantum-labs"

DEFAULT_JOURNEY = {
    "id": "quantum-labs-payouts-v1",
    "version": 1,
    "name": "Quantum Payouts outreach",
    "nodes": [
        {"id": "start", "type": "sequence", "pack_hint": "lombards"},
        {"id": "wait_reply", "type": "wait_event", "events": ["message.received"]},
        {"id": "on_reply", "type": "stop_sequence", "reason": "journey:reply"},
        {"id": "manual", "type": "MANUAL_TASK", "approval_required": True},
    ],
    "guardrails": {
        "respect_consent": True,
        "respect_quiet_hours": True,
        "stop_on_reply": True,
    },
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


class OrchestratorStore:
    def __init__(self, db_path: Path | None = None, *, tenant_id: str = DEFAULT_TENANT) -> None:
        self.db_path = Path(db_path or MODULES_DB)
        self.tenant_id = (tenant_id or DEFAULT_TENANT).strip() or DEFAULT_TENANT
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()
        self.ensure_default_journey()

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
                CREATE TABLE IF NOT EXISTS journey_definitions (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    journey_key TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    definition_json TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(tenant_id, journey_key, version)
                );

                CREATE TABLE IF NOT EXISTS journey_enrollments (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    journey_def_id TEXT NOT NULL,
                    account_id TEXT,
                    email TEXT,
                    company_id TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    current_node TEXT NOT NULL DEFAULT 'start',
                    dry_run INTEGER NOT NULL DEFAULT 0,
                    meta_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_journey_enroll_email
                    ON journey_enrollments(tenant_id, email, status);
                """
            )

    def ensure_default_journey(self) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM journey_definitions
                WHERE tenant_id = ? AND journey_key = ? AND version = ?
                """,
                (self.tenant_id, DEFAULT_JOURNEY["id"], DEFAULT_JOURNEY["version"]),
            ).fetchone()
            if row:
                return dict(row)
            now = _utc_now()
            jid = _new_id()
            conn.execute(
                """
                INSERT INTO journey_definitions(
                    id, tenant_id, journey_key, version, name,
                    definition_json, active, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (
                    jid,
                    self.tenant_id,
                    DEFAULT_JOURNEY["id"],
                    DEFAULT_JOURNEY["version"],
                    DEFAULT_JOURNEY["name"],
                    json.dumps(DEFAULT_JOURNEY, ensure_ascii=False),
                    now,
                    now,
                ),
            )
        return self.get_journey(DEFAULT_JOURNEY["id"], version=1) or {}

    def get_journey(self, journey_key: str, *, version: int | None = None) -> dict[str, Any] | None:
        with self.connect() as conn:
            if version is not None:
                row = conn.execute(
                    """
                    SELECT * FROM journey_definitions
                    WHERE tenant_id = ? AND journey_key = ? AND version = ?
                    """,
                    (self.tenant_id, journey_key, version),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT * FROM journey_definitions
                    WHERE tenant_id = ? AND journey_key = ? AND active = 1
                    ORDER BY version DESC LIMIT 1
                    """,
                    (self.tenant_id, journey_key),
                ).fetchone()
        if not row:
            return None
        out = dict(row)
        try:
            out["definition"] = json.loads(out.get("definition_json") or "{}")
        except json.JSONDecodeError:
            out["definition"] = {}
        return out

    def list_journeys(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, journey_key, version, name, active, created_at
                FROM journey_definitions WHERE tenant_id = ?
                ORDER BY journey_key, version DESC
                """,
                (self.tenant_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def enroll(
        self,
        *,
        email: str | None = None,
        company_id: str | None = None,
        account_id: str | None = None,
        journey_key: str = DEFAULT_JOURNEY["id"],
        dry_run: bool = False,
    ) -> dict[str, Any]:
        journey = self.get_journey(journey_key)
        if not journey:
            raise ValueError("journey_not_found")
        em = (email or "").strip().lower() or None
        now = _utc_now()
        eid = _new_id()
        with self.connect() as conn:
            # stop duplicate active enrollments for same email
            if em:
                conn.execute(
                    """
                    UPDATE journey_enrollments
                    SET status = 'superseded', updated_at = ?
                    WHERE tenant_id = ? AND email = ? AND status = 'active'
                    """,
                    (now, self.tenant_id, em),
                )
            conn.execute(
                """
                INSERT INTO journey_enrollments(
                    id, tenant_id, journey_def_id, account_id, email, company_id,
                    status, current_node, dry_run, meta_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'active', 'start', ?, '{}', ?, ?)
                """,
                (
                    eid,
                    self.tenant_id,
                    journey["id"],
                    account_id,
                    em,
                    company_id,
                    1 if dry_run else 0,
                    now,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT * FROM journey_enrollments WHERE id = ?", (eid,)
            ).fetchone()
        return dict(row) if row else {"id": eid}

    def on_inbound_reply(
        self,
        *,
        email: str | None,
        company_id: str | None = None,
        account_id: str | None = None,
        classification: str | None = None,
        stop_sequences: bool = True,
    ) -> dict[str, Any]:
        """Stop active journey enrollments + optionally SequenceStore (atomic intent)."""
        em = (email or "").strip().lower()
        now = _utc_now()
        stopped_enrollments = 0
        with self.connect() as conn:
            q = """
                UPDATE journey_enrollments
                SET status = 'stopped', current_node = 'on_reply', updated_at = ?,
                    meta_json = ?
                WHERE tenant_id = ? AND status = 'active'
            """
            meta = json.dumps(
                {"stop_classification": classification or ""}, ensure_ascii=False
            )
            params: list[Any] = [now, meta, self.tenant_id]
            clauses = []
            if em:
                clauses.append("email = ?")
                params.append(em)
            if company_id:
                clauses.append("company_id = ?")
                params.append(company_id)
            if account_id:
                clauses.append("account_id = ?")
                params.append(account_id)
            if not clauses:
                return {"ok": True, "stopped_enrollments": 0, "stopped_sequences": 0}
            q += " AND (" + " OR ".join(clauses) + ")"
            cur = conn.execute(q, params)
            stopped_enrollments = cur.rowcount or 0

        stopped_seq = 0
        if stop_sequences and (em or company_id):
            try:
                from modules.sequences import SequenceStore

                stopped_seq = SequenceStore().stop(
                    email=em or None,
                    company_id=company_id,
                    reason=f"journey:reply:{classification or 'inbound'}",
                )
            except Exception:  # noqa: BLE001
                logger.debug("orchestrator sequence stop failed", exc_info=True)

        return {
            "ok": True,
            "stopped_enrollments": int(stopped_enrollments),
            "stopped_sequences": int(stopped_seq or 0),
            "classification": classification,
        }

    def dry_run_preview(
        self,
        *,
        email: str,
        company_id: str | None = None,
    ) -> dict[str, Any]:
        from send_guards import check_send_allowed

        ok, reason = check_send_allowed(email, company_id=company_id)
        journey = self.get_journey(DEFAULT_JOURNEY["id"])
        return {
            "ok": True,
            "dry_run": True,
            "send_allowed": ok,
            "block_reason": reason or None,
            "journey": {
                "key": (journey or {}).get("journey_key"),
                "version": (journey or {}).get("version"),
                "nodes": ((journey or {}).get("definition") or {}).get("nodes"),
            },
            "would_enroll": ok,
        }

    def list_enrollments(self, *, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM journey_enrollments WHERE tenant_id = ?
                ORDER BY updated_at DESC LIMIT ?
                """,
                (self.tenant_id, max(1, min(limit, 200))),
            ).fetchall()
        return [dict(r) for r in rows]


class OrchestratorModule:
    name = "orchestrator"
    version = "0.1.0"

    def __init__(self) -> None:
        self.store = OrchestratorStore()

    def init_db(self) -> None:
        self.store.init_db()
        self.store.ensure_default_journey()

    def on_startup(self, ctx: AppContext) -> None:
        ctx.extras["orchestrator"] = self.store
        logger.info("orchestrator ready tenant=%s", self.store.tenant_id)

    def on_shutdown(self) -> None:
        return None

    def health(self) -> dict[str, Any]:
        with self.store.connect() as conn:
            n_j = conn.execute(
                "SELECT COUNT(*) AS n FROM journey_definitions WHERE tenant_id = ?",
                (self.store.tenant_id,),
            ).fetchone()["n"]
            n_e = conn.execute(
                "SELECT COUNT(*) AS n FROM journey_enrollments WHERE tenant_id = ? AND status = 'active'",
                (self.store.tenant_id,),
            ).fetchone()["n"]
        return {"ok": True, "journeys": int(n_j), "active_enrollments": int(n_e)}

    def register_routes(self, router: Any) -> None:
        from fastapi import HTTPException, Query
        from pydantic import BaseModel, Field

        @router.get("/health")
        def health() -> dict[str, Any]:
            return self.health()

        @router.get("/journeys")
        def journeys() -> dict[str, Any]:
            return {"ok": True, "items": self.store.list_journeys()}

        class EnrollBody(BaseModel):
            email: str | None = None
            company_id: str | None = None
            account_id: str | None = None
            journey_key: str = DEFAULT_JOURNEY["id"]
            dry_run: bool = False

        @router.post("/enroll")
        def enroll(payload: EnrollBody) -> dict[str, Any]:
            try:
                row = self.store.enroll(
                    email=payload.email,
                    company_id=payload.company_id,
                    account_id=payload.account_id,
                    journey_key=payload.journey_key,
                    dry_run=payload.dry_run,
                )
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            return {"ok": True, "enrollment": row}

        class DryRunBody(BaseModel):
            email: str = Field(..., min_length=3)
            company_id: str | None = None

        @router.post("/dry-run")
        def dry_run(payload: DryRunBody) -> dict[str, Any]:
            return self.store.dry_run_preview(
                email=payload.email, company_id=payload.company_id
            )

        @router.get("/enrollments")
        def enrollments(limit: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
            return {"ok": True, "items": self.store.list_enrollments(limit=limit)}

        class InboundBody(BaseModel):
            email: str | None = None
            company_id: str | None = None
            account_id: str | None = None
            classification: str | None = None

        @router.post("/on-inbound")
        def on_inbound(payload: InboundBody) -> dict[str, Any]:
            return self.store.on_inbound_reply(
                email=payload.email,
                company_id=payload.company_id,
                account_id=payload.account_id,
                classification=payload.classification,
            )
