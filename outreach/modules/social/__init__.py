"""Social Intelligence / LPR search — Slice B (in outreach, Accept R5).

Capability registry + source adapters. No browser automation.
Stubs for VK/OK/TenChat/LinkedIn return import_only/manual only.
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
from modules.social.adapters import (
    ADAPTERS,
    Capability,
    list_capabilities,
    run_adapters,
)
from modules.social.search import (
    build_coverage,
    cluster_candidates,
    reject_candidate,
    score_candidate,
)

logger = logging.getLogger("ava-outreach.social")

DEFAULT_TENANT = "quantum-labs"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


class SocialStore:
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
                CREATE TABLE IF NOT EXISTS lpr_search_runs (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    account_id TEXT,
                    bitrix_company_id TEXT,
                    company_title TEXT NOT NULL DEFAULT '',
                    role_template_json TEXT NOT NULL DEFAULT '[]',
                    status TEXT NOT NULL DEFAULT 'done',
                    cost_estimate REAL NOT NULL DEFAULT 0,
                    sources_json TEXT NOT NULL DEFAULT '[]',
                    meta_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_lpr_runs_tenant
                    ON lpr_search_runs(tenant_id, created_at);

                CREATE TABLE IF NOT EXISTS lpr_candidates (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    full_name TEXT NOT NULL DEFAULT '',
                    role_guess TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL,
                    profile_url TEXT,
                    email TEXT,
                    phone TEXT,
                    score REAL NOT NULL DEFAULT 0,
                    score_breakdown_json TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL DEFAULT 'proposed',
                    cluster_id TEXT,
                    evidence_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES lpr_search_runs(id)
                );
                CREATE INDEX IF NOT EXISTS ix_lpr_cand_run
                    ON lpr_candidates(run_id, status);

                CREATE TABLE IF NOT EXISTS social_action_tasks (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    candidate_id TEXT,
                    account_id TEXT,
                    action_type TEXT NOT NULL DEFAULT 'open_profile',
                    profile_url TEXT,
                    draft_text TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'open',
                    result_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )

    def run_search(
        self,
        *,
        bitrix_company_id: str | None = None,
        company_title: str = "",
        account_id: str | None = None,
        inn: str | None = None,
        roles: list[dict[str, Any]] | None = None,
        sources: list[str] | None = None,
        imports: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Execute LPR search across selected adapters (rules-first scoring)."""
        now = _utc_now()
        run_id = _new_id()
        role_list = roles or self._default_roles()
        source_ids = sources or [a.source_id for a in ADAPTERS if a.capabilities.search]
        caps = {c["source_id"]: c for c in list_capabilities()}

        raw_hits, cost = run_adapters(
            source_ids=source_ids,
            bitrix_company_id=bitrix_company_id,
            company_title=company_title,
            inn=inn,
            roles=role_list,
            imports=imports or [],
        )

        candidates: list[dict[str, Any]] = []
        for hit in raw_hits:
            scored = score_candidate(hit, roles=role_list)
            candidates.append(scored)

        clustered = cluster_candidates(candidates)

        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO lpr_search_runs(
                    id, tenant_id, account_id, bitrix_company_id, company_title,
                    role_template_json, status, cost_estimate, sources_json,
                    meta_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'done', ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    self.tenant_id,
                    account_id,
                    bitrix_company_id,
                    company_title,
                    json.dumps(role_list, ensure_ascii=False),
                    float(cost),
                    json.dumps(source_ids, ensure_ascii=False),
                    json.dumps({"capabilities_used": list(source_ids)}, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            for c in clustered:
                conn.execute(
                    """
                    INSERT INTO lpr_candidates(
                        id, tenant_id, run_id, full_name, role_guess, source,
                        profile_url, email, phone, score, score_breakdown_json,
                        status, cluster_id, evidence_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        c["id"],
                        self.tenant_id,
                        run_id,
                        c.get("full_name") or "",
                        c.get("role_guess") or "",
                        c.get("source") or "",
                        c.get("profile_url"),
                        c.get("email"),
                        c.get("phone"),
                        float(c.get("score") or 0),
                        json.dumps(c.get("score_breakdown") or {}, ensure_ascii=False),
                        c.get("status") or "proposed",
                        c.get("cluster_id"),
                        json.dumps(c.get("evidence") or {}, ensure_ascii=False),
                        now,
                        now,
                    ),
                )

        coverage = build_coverage(clustered, role_list)
        return {
            "ok": True,
            "run": self.get_run(run_id),
            "candidates": self.list_candidates(run_id=run_id),
            "coverage": coverage,
            "capabilities": [caps[s] for s in source_ids if s in caps],
        }

    def _default_roles(self) -> list[dict[str, Any]]:
        path = (
            Path(__file__).resolve().parents[2]
            / "config"
            / "tenants"
            / "quantum-labs"
            / "decision_role_template.json"
        )
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return list(data.get("roles") or [])
            except (OSError, json.JSONDecodeError):
                pass
        return [
            {
                "id": "economic_buyer",
                "labels": ["директор", "CEO", "собственник"],
                "primary": True,
            }
        ]

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM lpr_search_runs WHERE id = ? AND tenant_id = ?",
                (run_id, self.tenant_id),
            ).fetchone()
        if not row:
            return None
        out = dict(row)
        for key in ("role_template_json", "sources_json", "meta_json"):
            try:
                out[key.replace("_json", "")] = json.loads(out.get(key) or "{}")
            except json.JSONDecodeError:
                out[key.replace("_json", "")] = {}
        return out

    def list_candidates(
        self, *, run_id: str | None = None, status: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        q = "SELECT * FROM lpr_candidates WHERE tenant_id = ?"
        params: list[Any] = [self.tenant_id]
        if run_id:
            q += " AND run_id = ?"
            params.append(run_id)
        if status:
            q += " AND status = ?"
            params.append(status)
        q += " ORDER BY score DESC, created_at DESC LIMIT ?"
        params.append(max(1, min(limit, 500)))
        with self.connect() as conn:
            rows = conn.execute(q, params).fetchall()
        out = []
        for r in rows:
            item = dict(r)
            for key in ("score_breakdown_json", "evidence_json"):
                try:
                    item[key.replace("_json", "")] = json.loads(item.get(key) or "{}")
                except json.JSONDecodeError:
                    item[key.replace("_json", "")] = {}
            out.append(item)
        return out

    def set_candidate_status(self, candidate_id: str, status: str) -> dict[str, Any] | None:
        allowed = {"proposed", "approved", "rejected", "merged", "cluster_pending"}
        if status not in allowed:
            raise ValueError(f"invalid status: {status}")
        now = _utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE lpr_candidates SET status = ?, updated_at = ?
                WHERE id = ? AND tenant_id = ?
                """,
                (status, now, candidate_id, self.tenant_id),
            )
            row = conn.execute(
                "SELECT * FROM lpr_candidates WHERE id = ?", (candidate_id,)
            ).fetchone()
        return dict(row) if row else None

    def create_action_task(
        self,
        *,
        candidate_id: str | None,
        profile_url: str | None = None,
        draft_text: str = "",
        action_type: str = "open_profile",
        account_id: str | None = None,
    ) -> dict[str, Any]:
        """Manual social task — never auto-DM (B5)."""
        now = _utc_now()
        tid = _new_id()
        url = profile_url
        if candidate_id and not url:
            cands = self.list_candidates(limit=500)
            match = next((c for c in cands if c["id"] == candidate_id), None)
            if match:
                url = match.get("profile_url")
                if match.get("status") == "rejected":
                    raise ValueError("rejected_candidate_not_usable")
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO social_action_tasks(
                    id, tenant_id, candidate_id, account_id, action_type,
                    profile_url, draft_text, status, result_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'open', '{}', ?, ?)
                """,
                (
                    tid,
                    self.tenant_id,
                    candidate_id,
                    account_id,
                    action_type,
                    url,
                    draft_text,
                    now,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT * FROM social_action_tasks WHERE id = ?", (tid,)
            ).fetchone()
        return dict(row) if row else {"id": tid}

    def complete_action_task(
        self, task_id: str, *, result: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        now = _utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE social_action_tasks
                SET status = 'done', result_json = ?, updated_at = ?
                WHERE id = ? AND tenant_id = ?
                """,
                (json.dumps(result or {}, ensure_ascii=False), now, task_id, self.tenant_id),
            )
            row = conn.execute(
                "SELECT * FROM social_action_tasks WHERE id = ?", (task_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_tasks(self, *, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM social_action_tasks WHERE tenant_id = ?
                ORDER BY created_at DESC LIMIT ?
                """,
                (self.tenant_id, max(1, min(limit, 200))),
            ).fetchall()
        return [dict(r) for r in rows]


class SocialModule:
    name = "social"
    version = "0.1.0"

    def __init__(self) -> None:
        self.store = SocialStore()

    def init_db(self) -> None:
        self.store.init_db()

    def on_startup(self, ctx: AppContext) -> None:
        ctx.extras["social"] = self.store
        logger.info("social module ready tenant=%s adapters=%s", self.store.tenant_id, len(ADAPTERS))

    def on_shutdown(self) -> None:
        return None

    def health(self) -> dict[str, Any]:
        with self.store.connect() as conn:
            n_runs = conn.execute(
                "SELECT COUNT(*) AS n FROM lpr_search_runs WHERE tenant_id = ?",
                (self.store.tenant_id,),
            ).fetchone()["n"]
            n_cands = conn.execute(
                "SELECT COUNT(*) AS n FROM lpr_candidates WHERE tenant_id = ?",
                (self.store.tenant_id,),
            ).fetchone()["n"]
        return {
            "ok": True,
            "tenant_id": self.store.tenant_id,
            "adapters": len(ADAPTERS),
            "capabilities": list_capabilities(),
            "runs": int(n_runs),
            "candidates": int(n_cands),
        }

    def register_routes(self, router: Any) -> None:
        from fastapi import HTTPException, Query
        from pydantic import BaseModel, Field

        @router.get("/health")
        def health() -> dict[str, Any]:
            return self.health()

        @router.get("/capabilities")
        def capabilities() -> dict[str, Any]:
            return {"ok": True, "items": list_capabilities()}

        class SearchBody(BaseModel):
            bitrix_company_id: str | None = None
            company_title: str = ""
            account_id: str | None = None
            inn: str | None = None
            roles: list[dict[str, Any]] | None = None
            sources: list[str] | None = None
            imports: list[dict[str, Any]] | None = Field(
                default=None,
                description="Manual imports: {source, profile_url|username, full_name?, role?}",
            )

        @router.post("/search")
        def search(body: SearchBody) -> dict[str, Any]:
            return self.store.run_search(
                bitrix_company_id=body.bitrix_company_id,
                company_title=body.company_title,
                account_id=body.account_id,
                inn=body.inn,
                roles=body.roles,
                sources=body.sources,
                imports=body.imports,
            )

        @router.get("/runs/{run_id}")
        def get_run(run_id: str) -> dict[str, Any]:
            run = self.store.get_run(run_id)
            if not run:
                raise HTTPException(404, "run_not_found")
            cands = self.store.list_candidates(run_id=run_id)
            roles = run.get("role_template") or []
            if isinstance(roles, dict):
                roles = []
            return {
                "ok": True,
                "run": run,
                "candidates": cands,
                "coverage": build_coverage(cands, roles if isinstance(roles, list) else []),
            }

        class StatusBody(BaseModel):
            status: str = Field(..., min_length=2, max_length=40)

        @router.post("/candidates/{candidate_id}/status")
        def set_status(candidate_id: str, body: StatusBody) -> dict[str, Any]:
            try:
                row = self.store.set_candidate_status(candidate_id, body.status)
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            if not row:
                raise HTTPException(404, "candidate_not_found")
            return {"ok": True, "candidate": row}

        class TaskBody(BaseModel):
            candidate_id: str | None = None
            profile_url: str | None = None
            draft_text: str = ""
            action_type: str = "open_profile"
            account_id: str | None = None

        @router.post("/tasks")
        def create_task(body: TaskBody) -> dict[str, Any]:
            try:
                task = self.store.create_action_task(
                    candidate_id=body.candidate_id,
                    profile_url=body.profile_url,
                    draft_text=body.draft_text,
                    action_type=body.action_type,
                    account_id=body.account_id,
                )
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            return {"ok": True, "task": task}

        @router.get("/tasks")
        def tasks(limit: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
            return {"ok": True, "items": self.store.list_tasks(limit=limit)}

        class CompleteBody(BaseModel):
            result: dict[str, Any] | None = None

        @router.post("/tasks/{task_id}/complete")
        def complete_task(task_id: str, body: CompleteBody) -> dict[str, Any]:
            row = self.store.complete_action_task(task_id, result=body.result)
            if not row:
                raise HTTPException(404, "task_not_found")
            return {"ok": True, "task": row}


# re-export helpers for tests
__all__ = [
    "SocialModule",
    "SocialStore",
    "Capability",
    "list_capabilities",
    "reject_candidate",
]
