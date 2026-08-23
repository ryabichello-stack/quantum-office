"""Content Flywheel — news ingest, KB, dedup memory, editorial slots, video series."""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from core.paths import DATA_DIR, MODULES_DB
from core.registry import AppContext

from modules.content_flywheel.ingest import default_source_handles, flywheel_enabled, poll_watch_sources
from modules.content_flywheel.memory import content_hash
from modules.content_flywheel.processor import approve_proposal, process_news_item
from modules.content_flywheel.slots import slots_for_day

logger = logging.getLogger("ava-outreach.content_flywheel")

DEFAULT_TENANT = "quantum-labs"
BRAIN_INBOX = DATA_DIR / "flywheel" / "brain_inbox"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


class ContentFlywheelStore:
    def __init__(self, db_path: Path | None = None, *, tenant_id: str = DEFAULT_TENANT) -> None:
        self.db_path = Path(db_path or MODULES_DB)
        self.tenant_id = (tenant_id or DEFAULT_TENANT).strip() or DEFAULT_TENANT
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def _images_root(self) -> Path:
        return self.db_path.parent / "social_publish_images"

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
                CREATE TABLE IF NOT EXISTS flywheel_sources (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    handle TEXT NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_flywheel_sources
                    ON flywheel_sources(tenant_id, platform, enabled);

                CREATE TABLE IF NOT EXISTS flywheel_news (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    source_id TEXT,
                    platform TEXT NOT NULL DEFAULT '',
                    handle TEXT NOT NULL DEFAULT '',
                    external_id TEXT NOT NULL DEFAULT '',
                    content_hash TEXT NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    body TEXT NOT NULL DEFAULT '',
                    image_url TEXT NOT NULL DEFAULT '',
                    link TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'new',
                    kb_status TEXT NOT NULL DEFAULT 'pending',
                    raw_json TEXT NOT NULL DEFAULT '{}',
                    published_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS ux_flywheel_news_hash
                    ON flywheel_news(tenant_id, content_hash);
                CREATE INDEX IF NOT EXISTS ix_flywheel_news_status
                    ON flywheel_news(tenant_id, status, created_at);

                CREATE TABLE IF NOT EXISTS content_memory (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    topic TEXT NOT NULL DEFAULT '',
                    summary TEXT NOT NULL DEFAULT '',
                    news_id TEXT,
                    social_post_id TEXT,
                    video_draft_id TEXT,
                    slot_key TEXT,
                    published_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_content_memory_fp
                    ON content_memory(tenant_id, fingerprint);

                CREATE TABLE IF NOT EXISTS editorial_proposals (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    news_id TEXT NOT NULL,
                    slot_key TEXT NOT NULL,
                    slot_at TEXT NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    brief TEXT NOT NULL DEFAULT '',
                    angle_fingerprint TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'draft',
                    variants_json TEXT NOT NULL DEFAULT '{}',
                    image_options_json TEXT NOT NULL DEFAULT '[]',
                    video_brief_json TEXT NOT NULL DEFAULT '{}',
                    dedup_score REAL NOT NULL DEFAULT 0,
                    social_post_id TEXT,
                    video_draft_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_editorial_slot
                    ON editorial_proposals(tenant_id, slot_key, status);
                """
            )
            self._ensure_columns(
                conn,
                "flywheel_news",
                {
                    "theme_score": "REAL NOT NULL DEFAULT 0",
                    "theme_tags_json": "TEXT NOT NULL DEFAULT '[]'",
                    "analysis_json": "TEXT NOT NULL DEFAULT '{}'",
                },
            )
            self._ensure_columns(
                conn,
                "editorial_proposals",
                {
                    "kb_context_json": "TEXT NOT NULL DEFAULT '{}'",
                    "theme_context_json": "TEXT NOT NULL DEFAULT '{}'",
                },
            )

    def _ensure_columns(self, conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
        existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        for col, typedef in columns.items():
            if col not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typedef}")

    # --- sources ---

    def add_source(self, *, platform: str, handle: str, title: str = "") -> dict[str, Any]:
        now = _utc_now()
        sid = _new_id()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO flywheel_sources(id, tenant_id, platform, handle, title, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (
                    sid,
                    self.tenant_id,
                    platform.strip().lower(),
                    handle.strip()[:200],
                    (title or handle).strip()[:120],
                    now,
                    now,
                ),
            )
        return self.get_source(sid) or {"id": sid}

    def get_source(self, source_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM flywheel_sources WHERE id = ? AND tenant_id = ?",
                (source_id, self.tenant_id),
            ).fetchone()
        return dict(row) if row else None

    def list_sources(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM flywheel_sources WHERE tenant_id = ? ORDER BY platform, handle",
                (self.tenant_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def delete_source(self, source_id: str) -> bool:
        with self.connect() as conn:
            cur = conn.execute(
                "DELETE FROM flywheel_sources WHERE id = ? AND tenant_id = ?",
                (source_id, self.tenant_id),
            )
        return cur.rowcount > 0

    def source_handles_map(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {"telegram": [], "vk": []}
        for s in self.list_sources():
            if not s.get("enabled"):
                continue
            p = s.get("platform") or ""
            if p in out:
                out[p].append(s.get("handle") or "")
        env = default_source_handles()
        for p, handles in env.items():
            for h in handles:
                if h and h not in out.get(p, []):
                    out.setdefault(p, []).append(h)
        return out

    # --- news ---

    def ingest_news(
        self,
        *,
        platform: str,
        handle: str,
        title: str,
        body: str,
        external_id: str = "",
        image_url: str = "",
        link: str = "",
        source_id: str | None = None,
        raw: dict[str, Any] | None = None,
        published_at: str | None = None,
    ) -> dict[str, Any]:
        now = _utc_now()
        ch = content_hash(f"{title}\n{body}")
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT id FROM flywheel_news WHERE tenant_id = ? AND content_hash = ?",
                (self.tenant_id, ch),
            ).fetchone()
            if existing:
                out = self.get_news(existing["id"]) or {"id": existing["id"]}
                out["duplicate"] = True
                return out
            nid = _new_id()
            conn.execute(
                """
                INSERT INTO flywheel_news(
                    id, tenant_id, source_id, platform, handle, external_id, content_hash,
                    title, body, image_url, link, status, kb_status, raw_json,
                    published_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', 'pending', ?, ?, ?, ?)
                """,
                (
                    nid,
                    self.tenant_id,
                    source_id,
                    platform,
                    handle,
                    external_id or nid,
                    ch,
                    title[:300],
                    body[:8000],
                    image_url[:500],
                    link[:500],
                    json.dumps(raw or {}, ensure_ascii=False),
                    published_at or now,
                    now,
                    now,
                ),
            )
        row = self.get_news(nid) or {"id": nid}
        if not row.get("duplicate"):
            row = self.analyze_news_item(nid) or row
        return row

    def analyze_news_item(self, news_id: str) -> dict[str, Any] | None:
        from modules.content_flywheel.thematic import analyze_news_themes

        news = self.get_news(news_id)
        if not news:
            return None
        analysis = analyze_news_themes(title=news.get("title") or "", body=news.get("body") or "")
        now = _utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE flywheel_news
                SET theme_score = ?, theme_tags_json = ?, analysis_json = ?, updated_at = ?
                WHERE id = ? AND tenant_id = ?
                """,
                (
                    float(analysis.get("theme_score") or 0),
                    json.dumps(analysis.get("theme_tags") or [], ensure_ascii=False),
                    json.dumps(analysis, ensure_ascii=False),
                    now,
                    news_id,
                    self.tenant_id,
                ),
            )
        return self.get_news(news_id)

    def poll_and_ingest(self) -> dict[str, Any]:
        handles = self.source_handles_map()
        items = poll_watch_sources(handles=handles)
        ingested: list[dict[str, Any]] = []
        duplicates = 0
        for item in items:
            row = self.ingest_news(
                platform=item["platform"],
                handle=item["handle"],
                title=item["title"],
                body=item["body"],
                external_id=item.get("external_id") or "",
                image_url=item.get("image_url") or "",
                link=item.get("link") or "",
                raw=item.get("raw"),
                published_at=item.get("published_at"),
            )
            if row.get("duplicate"):
                duplicates += 1
            else:
                ingested.append(row)
        return {
            "ok": True,
            "enabled": flywheel_enabled(),
            "polled": len(items),
            "ingested": len(ingested),
            "duplicates": duplicates,
            "items": ingested,
        }

    def get_news(self, news_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM flywheel_news WHERE id = ? AND tenant_id = ?",
                (news_id, self.tenant_id),
            ).fetchone()
        if not row:
            return None
        out = dict(row)
        try:
            out["raw"] = json.loads(out.get("raw_json") or "{}")
        except json.JSONDecodeError:
            out["raw"] = {}
        try:
            out["theme_tags"] = json.loads(out.get("theme_tags_json") or "[]")
        except json.JSONDecodeError:
            out["theme_tags"] = []
        try:
            out["analysis"] = json.loads(out.get("analysis_json") or "{}")
        except json.JSONDecodeError:
            out["analysis"] = {}
        return out

    def list_news(self, *, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        q = "SELECT * FROM flywheel_news WHERE tenant_id = ?"
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
                item["raw"] = json.loads(item.get("raw_json") or "{}")
            except json.JSONDecodeError:
                item["raw"] = {}
            out.append(item)
        return out

    def set_news_status(self, news_id: str, status: str) -> None:
        now = _utc_now()
        with self.connect() as conn:
            conn.execute(
                "UPDATE flywheel_news SET status = ?, updated_at = ? WHERE id = ? AND tenant_id = ?",
                (status, now, news_id, self.tenant_id),
            )

    def set_news_kb_status(self, news_id: str, kb_status: str) -> None:
        now = _utc_now()
        with self.connect() as conn:
            conn.execute(
                "UPDATE flywheel_news SET kb_status = ?, updated_at = ? WHERE id = ? AND tenant_id = ?",
                (kb_status, now, news_id, self.tenant_id),
            )

    # --- memory ---

    def remember_angle(
        self,
        *,
        topic: str,
        summary: str,
        fingerprint: str,
        news_id: str | None = None,
        social_post_id: str | None = None,
        video_draft_id: str | None = None,
        slot_key: str | None = None,
    ) -> dict[str, Any]:
        now = _utc_now()
        mid = _new_id()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO content_memory(
                    id, tenant_id, fingerprint, topic, summary, news_id,
                    social_post_id, video_draft_id, slot_key, published_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mid,
                    self.tenant_id,
                    fingerprint,
                    topic[:200],
                    summary[:2000],
                    news_id,
                    social_post_id,
                    video_draft_id,
                    slot_key,
                    now,
                    now,
                ),
            )
        return {"id": mid, "fingerprint": fingerprint, "topic": topic}

    def list_memory(self, *, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM content_memory WHERE tenant_id = ?
                ORDER BY published_at DESC LIMIT ?
                """,
                (self.tenant_id, max(1, min(limit, 200))),
            ).fetchall()
        return [dict(r) for r in rows]

    # --- proposals ---

    def occupied_slot_keys(self) -> set[str]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT slot_key FROM editorial_proposals
                WHERE tenant_id = ? AND status NOT IN ('skipped', 'rejected')
                """,
                (self.tenant_id,),
            ).fetchall()
        return {r["slot_key"] for r in rows}

    def create_proposal(
        self,
        *,
        news_id: str,
        slot_key: str,
        slot_at: str,
        title: str,
        brief: str,
        angle_fingerprint: str,
        variants: dict[str, Any],
        image_options: list[dict[str, Any]],
        video_brief: dict[str, Any],
        kb_context: dict[str, Any] | None = None,
        theme_context: dict[str, Any] | None = None,
        dedup_score: float = 0.0,
    ) -> dict[str, Any]:
        now = _utc_now()
        pid = _new_id()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO editorial_proposals(
                    id, tenant_id, news_id, slot_key, slot_at, title, brief,
                    angle_fingerprint, status, variants_json, image_options_json,
                    video_brief_json, kb_context_json, theme_context_json,
                    dedup_score, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pid,
                    self.tenant_id,
                    news_id,
                    slot_key,
                    slot_at,
                    title[:200],
                    brief[:4000],
                    angle_fingerprint,
                    json.dumps(variants, ensure_ascii=False),
                    json.dumps(image_options, ensure_ascii=False),
                    json.dumps(video_brief, ensure_ascii=False),
                    json.dumps(kb_context or {}, ensure_ascii=False),
                    json.dumps(theme_context or {}, ensure_ascii=False),
                    float(dedup_score),
                    now,
                    now,
                ),
            )
        return self.get_proposal(pid) or {"id": pid}

    def _row_proposal(self, row: dict[str, Any]) -> dict[str, Any]:
        out = dict(row)
        for key, default in (
            ("variants_json", {}),
            ("image_options_json", []),
            ("video_brief_json", {}),
            ("kb_context_json", {}),
            ("theme_context_json", {}),
        ):
            field = key.replace("_json", "")
            try:
                out[field] = json.loads(out.get(key) or json.dumps(default))
            except json.JSONDecodeError:
                out[field] = default
        return out

    def get_proposal(self, proposal_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM editorial_proposals WHERE id = ? AND tenant_id = ?",
                (proposal_id, self.tenant_id),
            ).fetchone()
        return self._row_proposal(dict(row)) if row else None

    def list_proposals(self, *, status: str | None = None, limit: int = 40) -> list[dict[str, Any]]:
        q = "SELECT * FROM editorial_proposals WHERE tenant_id = ?"
        params: list[Any] = [self.tenant_id]
        if status:
            q += " AND status = ?"
            params.append(status)
        q += " ORDER BY slot_at ASC LIMIT ?"
        params.append(max(1, min(limit, 200)))
        with self.connect() as conn:
            rows = conn.execute(q, params).fetchall()
        return [self._row_proposal(dict(r)) for r in rows]

    def set_proposal_status(
        self,
        proposal_id: str,
        status: str,
        *,
        social_post_id: str | None = None,
        video_draft_id: str | None = None,
    ) -> dict[str, Any] | None:
        now = _utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE editorial_proposals
                SET status = ?, updated_at = ?,
                    social_post_id = COALESCE(?, social_post_id),
                    video_draft_id = COALESCE(?, video_draft_id)
                WHERE id = ? AND tenant_id = ?
                """,
                (status, now, social_post_id, video_draft_id, proposal_id, self.tenant_id),
            )
        return self.get_proposal(proposal_id)

    def run_cycle(self) -> dict[str, Any]:
        poll = self.poll_and_ingest()
        processed: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        for item in poll.get("items") or []:
            out = process_news_item(self, item["id"])
            if out.get("skipped"):
                skipped.append(out)
            elif out.get("ok"):
                processed.append(out)
        for row in self.list_news(status="new", limit=20):
            out = process_news_item(self, row["id"])
            if out.get("skipped"):
                skipped.append(out)
            elif out.get("ok") and out.get("proposal"):
                processed.append(out)
        return {
            "ok": True,
            "poll": poll,
            "processed": len(processed),
            "skipped": len(skipped),
            "proposals_today": self.list_proposals(limit=20),
            "slots": slots_for_day(),
        }


class ContentFlywheelModule:
    name = "content_flywheel"
    version = "0.1.0"

    def __init__(self) -> None:
        self.store = ContentFlywheelStore()

    def init_db(self) -> None:
        self.store.init_db()
        BRAIN_INBOX.mkdir(parents=True, exist_ok=True)

    def on_startup(self, ctx: AppContext) -> None:
        ctx.extras["content_flywheel"] = self.store
        BRAIN_INBOX.mkdir(parents=True, exist_ok=True)
        logger.info("content_flywheel ready enabled=%s", flywheel_enabled())

    def on_shutdown(self) -> None:
        return None

    def health(self) -> dict[str, Any]:
        with self.store.connect() as conn:
            news = conn.execute(
                "SELECT COUNT(*) AS n FROM flywheel_news WHERE tenant_id = ?",
                (self.store.tenant_id,),
            ).fetchone()["n"]
            prop = conn.execute(
                "SELECT COUNT(*) AS n FROM editorial_proposals WHERE tenant_id = ? AND status = 'draft'",
                (self.store.tenant_id,),
            ).fetchone()["n"]
            mem = conn.execute(
                "SELECT COUNT(*) AS n FROM content_memory WHERE tenant_id = ?",
                (self.store.tenant_id,),
            ).fetchone()["n"]
        return {
            "ok": True,
            "enabled": flywheel_enabled(),
            "news": int(news),
            "draft_proposals": int(prop),
            "memory": int(mem),
            "slots_today": slots_for_day(),
        }

    def register_routes(self, router: Any) -> None:
        from fastapi import HTTPException, Query
        from pydantic import BaseModel, Field

        @router.get("/health")
        def health() -> dict[str, Any]:
            return self.health()

        @router.get("/slots")
        def slots() -> dict[str, Any]:
            return {"ok": True, "items": slots_for_day()}

        class SourceBody(BaseModel):
            platform: str = Field(..., min_length=2)
            handle: str = Field(..., min_length=1)
            title: str = ""

        @router.post("/sources")
        def add_source(payload: SourceBody) -> dict[str, Any]:
            return {"ok": True, "source": self.store.add_source(**payload.model_dump())}

        @router.get("/sources")
        def list_sources() -> dict[str, Any]:
            return {"ok": True, "items": self.store.list_sources()}

        @router.delete("/sources/{source_id}")
        def del_source(source_id: str) -> dict[str, Any]:
            if not self.store.delete_source(source_id):
                raise HTTPException(404, "not_found")
            return {"ok": True}

        class NewsBody(BaseModel):
            platform: str = "manual"
            handle: str = ""
            title: str = Field(..., min_length=2)
            body: str = Field(..., min_length=2)
            image_url: str = ""
            link: str = ""

        @router.post("/news")
        def ingest_manual(payload: NewsBody) -> dict[str, Any]:
            row = self.store.ingest_news(**payload.model_dump())
            return {"ok": True, "news": row}

        @router.post("/poll")
        def poll() -> dict[str, Any]:
            return self.store.poll_and_ingest()

        @router.get("/news")
        def list_news(status: str | None = None, limit: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
            return {"ok": True, "items": self.store.list_news(status=status, limit=limit)}

        @router.post("/news/{news_id}/process")
        def process_one(news_id: str, force: bool = False) -> dict[str, Any]:
            out = process_news_item(self.store, news_id, force=force)
            if not out.get("ok") and out.get("error"):
                raise HTTPException(400, out.get("error"))
            return out

        @router.get("/proposals")
        def list_proposals(status: str | None = None) -> dict[str, Any]:
            return {"ok": True, "items": self.store.list_proposals(status=status)}

        @router.post("/proposals/{proposal_id}/approve")
        def approve(proposal_id: str) -> dict[str, Any]:
            out = approve_proposal(self.store, proposal_id)
            if not out.get("ok"):
                raise HTTPException(400, out.get("error") or "failed")
            return out

        @router.get("/memory")
        def memory(limit: int = Query(40, ge=1, le=200)) -> dict[str, Any]:
            return {"ok": True, "items": self.store.list_memory(limit=limit)}

        @router.get("/themes")
        def themes() -> dict[str, Any]:
            from modules.content_flywheel.thematic import THEME_TAXONOMY, theme_min_score

            return {
                "ok": True,
                "lens": "macro_financial_money_flows",
                "min_score": theme_min_score(),
                "taxonomy": THEME_TAXONOMY,
            }

        @router.post("/news/{news_id}/analyze")
        def analyze_news(news_id: str) -> dict[str, Any]:
            row = self.store.analyze_news_item(news_id)
            if not row:
                raise HTTPException(404, "not_found")
            return {"ok": True, "news": row, "analysis": row.get("analysis")}

        @router.get("/kb/enrich")
        def kb_enrich(title: str = "", body: str = "") -> dict[str, Any]:
            from knowledge_enrich import enrich_content_brief

            if not (title.strip() or body.strip()):
                raise HTTPException(400, "title_or_body_required")
            return {"ok": True, **enrich_content_brief(title=title, body=body, tenant_id=self.store.tenant_id)}

        @router.get("/kb/products")
        def kb_products() -> dict[str, Any]:
            from knowledge_enrich import load_tenant_products

            return {"ok": True, "items": load_tenant_products(self.store.tenant_id)}

        @router.post("/run-cycle")
        def run_cycle() -> dict[str, Any]:
            return self.store.run_cycle()
