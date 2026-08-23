"""Social Publish — multi-platform posts, images, channels, reposts (APPROVAL_REQUIRED).

Platforms: telegram, vk, instagram, youtube.
Does not auto-publish or cold-DM. Real API wiring via SOCIAL_PUBLISH_ENABLED + per-platform secrets later.
"""

from __future__ import annotations

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

from modules.social_publish.adapters import publish_to_channel
from modules.social_publish.image_gen import write_social_card
from modules.social_publish.post_templates import PLATFORMS, variants_from_brief

logger = logging.getLogger("ava-outreach.social_publish")

DEFAULT_TENANT = "quantum-labs"


def _images_root(db_path: Path) -> Path:
    return db_path.parent / "social_publish_images"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


class SocialPublishStore:
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
                CREATE TABLE IF NOT EXISTS publish_channels (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    handle TEXT NOT NULL DEFAULT '',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    meta_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_publish_channels_tenant
                    ON publish_channels(tenant_id, platform, enabled);

                CREATE TABLE IF NOT EXISTS social_posts (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    brief TEXT NOT NULL DEFAULT '',
                    link TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'draft',
                    platforms_json TEXT NOT NULL DEFAULT '[]',
                    variants_json TEXT NOT NULL DEFAULT '{}',
                    images_json TEXT NOT NULL DEFAULT '[]',
                    source TEXT NOT NULL DEFAULT 'manual',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    approved_at TEXT
                );
                CREATE INDEX IF NOT EXISTS ix_social_posts_status
                    ON social_posts(tenant_id, status, updated_at);

                CREATE TABLE IF NOT EXISTS publish_jobs (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    post_id TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'queued',
                    result_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    published_at TEXT
                );
                CREATE INDEX IF NOT EXISTS ix_publish_jobs_post
                    ON publish_jobs(tenant_id, post_id, status);
                """
            )
            self._ensure_columns(
                conn,
                "social_posts",
                {"kb_context_json": "TEXT NOT NULL DEFAULT '{}'"},
            )

    def _ensure_columns(self, conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
        existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        for col, typedef in columns.items():
            if col not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typedef}")

    # --- channels ---

    def add_channel(
        self,
        *,
        platform: str,
        title: str,
        handle: str,
        enabled: bool = True,
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        p = (platform or "").strip().lower()
        if p not in PLATFORMS:
            raise ValueError(f"unsupported platform: {p}")
        now = _utc_now()
        cid = _new_id()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO publish_channels(
                    id, tenant_id, platform, title, handle, enabled,
                    meta_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cid,
                    self.tenant_id,
                    p,
                    (title or handle or p).strip()[:120],
                    (handle or "").strip()[:200],
                    1 if enabled else 0,
                    json.dumps(meta or {}, ensure_ascii=False),
                    now,
                    now,
                ),
            )
        return self.get_channel(cid) or {"id": cid}

    def get_channel(self, channel_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM publish_channels WHERE id = ? AND tenant_id = ?",
                (channel_id, self.tenant_id),
            ).fetchone()
        if not row:
            return None
        out = dict(row)
        out["enabled"] = bool(out.get("enabled"))
        try:
            out["meta"] = json.loads(out.get("meta_json") or "{}")
        except json.JSONDecodeError:
            out["meta"] = {}
        return out

    def list_channels(self, *, platform: str | None = None) -> list[dict[str, Any]]:
        q = "SELECT * FROM publish_channels WHERE tenant_id = ?"
        params: list[Any] = [self.tenant_id]
        if platform:
            q += " AND platform = ?"
            params.append(platform.strip().lower())
        q += " ORDER BY platform ASC, title ASC"
        with self.connect() as conn:
            rows = conn.execute(q, params).fetchall()
        out = []
        for r in rows:
            item = dict(r)
            item["enabled"] = bool(item.get("enabled"))
            try:
                item["meta"] = json.loads(item.get("meta_json") or "{}")
            except json.JSONDecodeError:
                item["meta"] = {}
            out.append(item)
        return out

    def delete_channel(self, channel_id: str) -> bool:
        with self.connect() as conn:
            cur = conn.execute(
                "DELETE FROM publish_channels WHERE id = ? AND tenant_id = ?",
                (channel_id, self.tenant_id),
            )
        return cur.rowcount > 0

    # --- posts ---

    def create_post(
        self,
        *,
        title: str,
        brief: str,
        platforms: list[str] | None = None,
        link: str = "",
        source: str = "studio",
        generate_images: bool = True,
        use_kb: bool = True,
        kb_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = _utc_now()
        pid = _new_id()
        title = (title or "Пост Quantum Labs").strip()[:200]
        brief_raw = (brief or "").strip()[:4000]
        kb_ctx: dict[str, Any] = kb_context or {}
        if use_kb and not kb_ctx:
            try:
                from knowledge_enrich import enrich_content_brief

                kb_ctx = enrich_content_brief(
                    title=title,
                    body=brief_raw,
                    link=link,
                    tenant_id=self.tenant_id,
                )
            except Exception:  # noqa: BLE001
                kb_ctx = {}
        brief = kb_ctx.get("brief_enriched") or brief_raw
        product_footer = kb_ctx.get("product_paragraph") or ""
        selected = [p.strip().lower() for p in (platforms or list(PLATFORMS)) if p.strip()]
        selected = [p for p in selected if p in PLATFORMS] or list(PLATFORMS)
        variants = variants_from_brief(
            title=title,
            brief=brief,
            platforms=selected,
            link=link,
            product_footer=product_footer,
        )
        images: list[dict[str, Any]] = []
        if generate_images:
            images = self._generate_images(pid, title=title, brief=brief)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO social_posts(
                    id, tenant_id, title, brief, link, status, platforms_json,
                    variants_json, images_json, kb_context_json, source, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'draft', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pid,
                    self.tenant_id,
                    title,
                    brief,
                    (link or "").strip()[:500],
                    json.dumps(selected, ensure_ascii=False),
                    json.dumps(variants, ensure_ascii=False),
                    json.dumps(images, ensure_ascii=False),
                    json.dumps(kb_ctx, ensure_ascii=False),
                    source,
                    now,
                    now,
                ),
            )
        try:
            from usage_meter import UsageMeter

            UsageMeter(self.db_path, tenant_id=self.tenant_id).incr("social_posts")
        except Exception:
            pass
        return self.get_post(pid) or {"id": pid}

    def _generate_images(self, post_id: str, *, title: str, brief: str) -> list[dict[str, Any]]:
        out_dir = _images_root(self.db_path) / self.tenant_id
        square = write_social_card(out_dir, post_id=post_id, title=title, subtitle=brief, variant="square")
        story = write_social_card(out_dir, post_id=post_id, title=title, subtitle=brief[:120], variant="story")
        return [square, story]

    def get_post(self, post_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM social_posts WHERE id = ? AND tenant_id = ?",
                (post_id, self.tenant_id),
            ).fetchone()
        if not row:
            return None
        return self._row_post(dict(row))

    def _row_post(self, row: dict[str, Any]) -> dict[str, Any]:
        out = dict(row)
        for key, default in (
            ("platforms_json", []),
            ("variants_json", {}),
            ("images_json", []),
            ("kb_context_json", {}),
        ):
            field = key.replace("_json", "")
            try:
                out[field] = json.loads(out.get(key) or json.dumps(default))
            except json.JSONDecodeError:
                out[field] = default
        return out

    def list_posts(self, *, status: str | None = None, limit: int = 40) -> list[dict[str, Any]]:
        q = "SELECT * FROM social_posts WHERE tenant_id = ?"
        params: list[Any] = [self.tenant_id]
        if status:
            q += " AND status = ?"
            params.append(status)
        q += " ORDER BY updated_at DESC LIMIT ?"
        params.append(max(1, min(limit, 200)))
        with self.connect() as conn:
            rows = conn.execute(q, params).fetchall()
        return [self._row_post(dict(r)) for r in rows]

    def set_post_status(self, post_id: str, status: str) -> dict[str, Any] | None:
        allowed = {"draft", "pending_approval", "approved", "rejected", "published"}
        if status not in allowed:
            raise ValueError(f"invalid status: {status}")
        now = _utc_now()
        approved_at = now if status == "approved" else None
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE social_posts
                SET status = ?, updated_at = ?,
                    approved_at = COALESCE(?, approved_at)
                WHERE id = ? AND tenant_id = ?
                """,
                (status, now, approved_at, post_id, self.tenant_id),
            )
        return self.get_post(post_id)

    def regenerate_images(self, post_id: str) -> dict[str, Any] | None:
        post = self.get_post(post_id)
        if not post:
            return None
        images = self._generate_images(post_id, title=post.get("title") or "", brief=post.get("brief") or "")
        now = _utc_now()
        with self.connect() as conn:
            conn.execute(
                "UPDATE social_posts SET images_json = ?, updated_at = ? WHERE id = ? AND tenant_id = ?",
                (json.dumps(images, ensure_ascii=False), now, post_id, self.tenant_id),
            )
        return self.get_post(post_id)

    # --- repost / publish jobs ---

    def queue_repost(self, post_id: str, channel_ids: list[str]) -> dict[str, Any]:
        post = self.get_post(post_id)
        if not post:
            return {"ok": False, "error": "post_not_found"}
        if post.get("status") != "approved":
            return {
                "ok": False,
                "error": "approval_required",
                "message": "Сначала утвердите пост (APPROVAL_REQUIRED)",
            }
        if not channel_ids:
            return {"ok": False, "error": "no_channels"}

        jobs: list[dict[str, Any]] = []
        image_path = None
        imgs = post.get("images") or []
        if imgs:
            image_path = imgs[0].get("path")

        for cid in channel_ids:
            ch = self.get_channel(cid)
            if not ch or not ch.get("enabled"):
                continue
            platform = ch.get("platform") or ""
            variants = post.get("variants") or {}
            variant = variants.get(platform) or {}
            text = variant.get("text") or variant.get("caption") or post.get("brief") or ""
            result = publish_to_channel(
                platform=platform,
                channel_handle=ch.get("handle") or "",
                text=text,
                image_path=image_path,
                meta={"post_id": post_id, "channel_id": cid},
            )
            now = _utc_now()
            jid = _new_id()
            status = "published" if result.get("ok") else "failed"
            published_at = now if status == "published" else None
            with self.connect() as conn:
                conn.execute(
                    """
                    INSERT INTO publish_jobs(
                        id, tenant_id, post_id, channel_id, platform, status,
                        result_json, created_at, updated_at, published_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        jid,
                        self.tenant_id,
                        post_id,
                        cid,
                        platform,
                        status,
                        json.dumps(result, ensure_ascii=False),
                        now,
                        now,
                        published_at,
                    ),
                )
            jobs.append(
                {
                    "id": jid,
                    "channel_id": cid,
                    "platform": platform,
                    "status": status,
                    "result": result,
                }
            )

        if jobs and all(j["status"] == "published" for j in jobs):
            self.set_post_status(post_id, "published")

        try:
            from usage_meter import UsageMeter

            UsageMeter(self.db_path, tenant_id=self.tenant_id).incr("social_reposts", len(jobs))
        except Exception:
            pass

        return {
            "ok": bool(jobs),
            "post_id": post_id,
            "jobs": jobs,
            "auto_publish": False,
        }

    def list_jobs(self, post_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM publish_jobs
                WHERE post_id = ? AND tenant_id = ?
                ORDER BY created_at DESC
                """,
                (post_id, self.tenant_id),
            ).fetchall()
        out = []
        for r in rows:
            item = dict(r)
            try:
                item["result"] = json.loads(item.get("result_json") or "{}")
            except json.JSONDecodeError:
                item["result"] = {}
            out.append(item)
        return out


class SocialPublishModule:
    name = "social_publish"
    version = "0.1.0"

    def __init__(self) -> None:
        self.store = SocialPublishStore()

    def init_db(self) -> None:
        self.store.init_db()

    def on_startup(self, ctx: AppContext) -> None:
        ctx.extras["social_publish"] = self.store
        _images_root(self.store.db_path).mkdir(parents=True, exist_ok=True)
        logger.info("social_publish ready platforms=%s", ",".join(PLATFORMS))

    def on_shutdown(self) -> None:
        return None

    def health(self) -> dict[str, Any]:
        with self.store.connect() as conn:
            ch = conn.execute(
                "SELECT COUNT(*) AS n FROM publish_channels WHERE tenant_id = ?",
                (self.store.tenant_id,),
            ).fetchone()["n"]
            posts = conn.execute(
                "SELECT COUNT(*) AS n FROM social_posts WHERE tenant_id = ?",
                (self.store.tenant_id,),
            ).fetchone()["n"]
        return {
            "ok": True,
            "channels": int(ch),
            "posts": int(posts),
            "platforms": list(PLATFORMS),
        }

    def register_routes(self, router: Any) -> None:
        from fastapi import HTTPException, Query
        from fastapi.responses import FileResponse
        from pydantic import BaseModel, Field

        @router.get("/health")
        def health() -> dict[str, Any]:
            return self.health()

        @router.get("/platforms")
        def platforms() -> dict[str, Any]:
            return {"ok": True, "items": list(PLATFORMS)}

        class ChannelBody(BaseModel):
            platform: str = Field(..., min_length=2, max_length=40)
            title: str = Field("", max_length=120)
            handle: str = Field(..., min_length=1, max_length=200)
            enabled: bool = True
            meta: dict[str, Any] | None = None

        @router.post("/channels")
        def add_channel(payload: ChannelBody) -> dict[str, Any]:
            try:
                row = self.store.add_channel(
                    platform=payload.platform,
                    title=payload.title,
                    handle=payload.handle,
                    enabled=payload.enabled,
                    meta=payload.meta,
                )
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            return {"ok": True, "channel": row}

        @router.get("/channels")
        def list_channels(platform: str | None = None) -> dict[str, Any]:
            return {"ok": True, "items": self.store.list_channels(platform=platform)}

        @router.delete("/channels/{channel_id}")
        def delete_channel(channel_id: str) -> dict[str, Any]:
            if not self.store.delete_channel(channel_id):
                raise HTTPException(404, "channel_not_found")
            return {"ok": True}

        class PostBody(BaseModel):
            title: str = Field(..., min_length=2, max_length=200)
            brief: str = Field(..., min_length=2)
            platforms: list[str] | None = None
            link: str = ""
            source: str = "studio"
            generate_images: bool = True
            use_kb: bool = True

        @router.post("/posts")
        def create_post(payload: PostBody) -> dict[str, Any]:
            row = self.store.create_post(
                title=payload.title,
                brief=payload.brief,
                platforms=payload.platforms,
                link=payload.link,
                source=payload.source,
                generate_images=payload.generate_images,
                use_kb=payload.use_kb,
            )
            return {"ok": True, "post": row}

        @router.get("/kb/enrich")
        def kb_enrich(title: str = "", body: str = "") -> dict[str, Any]:
            from knowledge_enrich import enrich_content_brief

            if not (title.strip() or body.strip()):
                raise HTTPException(400, "title_or_body_required")
            return {"ok": True, **enrich_content_brief(title=title, body=body, tenant_id=self.store.tenant_id)}

        @router.get("/posts")
        def list_posts(
            status: str | None = None, limit: int = Query(40, ge=1, le=200)
        ) -> dict[str, Any]:
            return {"ok": True, "items": self.store.list_posts(status=status, limit=limit)}

        @router.get("/posts/{post_id}")
        def get_post(post_id: str) -> dict[str, Any]:
            row = self.store.get_post(post_id)
            if not row:
                raise HTTPException(404, "post_not_found")
            return {"ok": True, "post": row, "jobs": self.store.list_jobs(post_id)}

        class StatusBody(BaseModel):
            status: str = Field(..., min_length=2, max_length=40)

        @router.post("/posts/{post_id}/status")
        def set_status(post_id: str, payload: StatusBody) -> dict[str, Any]:
            try:
                row = self.store.set_post_status(post_id, payload.status)
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            if not row:
                raise HTTPException(404, "post_not_found")
            return {"ok": True, "post": row}

        @router.post("/posts/{post_id}/generate-images")
        def regen_images(post_id: str) -> dict[str, Any]:
            row = self.store.regenerate_images(post_id)
            if not row:
                raise HTTPException(404, "post_not_found")
            return {"ok": True, "post": row}

        class RepostBody(BaseModel):
            channel_ids: list[str] = Field(..., min_length=1)

        @router.post("/posts/{post_id}/repost")
        def repost(post_id: str, payload: RepostBody) -> dict[str, Any]:
            out = self.store.queue_repost(post_id, payload.channel_ids)
            if not out.get("ok"):
                raise HTTPException(400, out.get("error") or "repost_failed")
            return out

        @router.get("/images/{tenant_id}/{filename}")
        def serve_image(tenant_id: str, filename: str) -> FileResponse:
            if tenant_id != self.store.tenant_id or ".." in filename or "/" in filename:
                raise HTTPException(400, "invalid_path")
            path = _images_root(self.store.db_path) / tenant_id / filename
            if not path.is_file():
                raise HTTPException(404, "not_found")
            return FileResponse(path, media_type="image/svg+xml")
