"""Process news → KB queue, dedup, proposals, social post + video brief."""

from __future__ import annotations

import json
import os
from typing import Any

from modules.content_flywheel.memory import angle_fingerprint, content_hash, find_similar
from modules.content_flywheel.slots import next_open_slot
from modules.social_publish.image_gen import write_social_card
from modules.social_publish.post_templates import variants_from_brief


def dedup_threshold() -> float:
    try:
        return float(os.getenv("FLYWHEEL_DEDUP_THRESHOLD") or "0.55")
    except ValueError:
        return 0.55


def auto_kb() -> bool:
    return (os.getenv("FLYWHEEL_AUTO_KB") or "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def use_product_kb() -> bool:
    """Optional second layer: product/company facts from Second Brain."""
    return (os.getenv("FLYWHEEL_USE_PRODUCT_KB") or "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def theme_min_score() -> float:
    try:
        return float(os.getenv("FLYWHEEL_THEME_MIN_SCORE") or "0.35")
    except ValueError:
        return 0.35


def avatar_profile() -> str:
    return (os.getenv("FLYWHEEL_AVATAR_PROFILE") or "quantum-host-v1").strip()


def build_image_options(
    store: Any,
    *,
    post_id: str,
    title: str,
    brief: str,
    original_url: str = "",
) -> list[dict[str, Any]]:
    options: list[dict[str, Any]] = []
    if original_url:
        options.append(
            {
                "kind": "original",
                "url": original_url,
                "selected": True,
                "note": "Оригинал из источника",
            }
        )
    out_dir = store._images_root() / store.tenant_id / "flywheel"
    gen = write_social_card(out_dir, post_id=post_id, title=title, subtitle=brief[:200], variant="square")
    options.append(
        {
            "kind": "generated",
            "path": gen.get("path"),
            "filename": gen.get("filename"),
            "mime": gen.get("mime"),
            "selected": not original_url,
            "note": "Сгенерированная карточка",
        }
    )
    return options


def talking_head_brief(
    *,
    title: str,
    body: str,
    news_id: str,
    thematic_hook: str = "",
    product_paragraph: str = "",
    citations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    profile = avatar_profile()
    angle = (thematic_hook or body)[:500]
    kb_line = ""
    if product_paragraph:
        kb_line = f"\n\nПо продуктам: {product_paragraph[:280]}"
    elif citations:
        kb_line = "\n\n" + " ".join((c.get("note") or "")[:80] for c in citations[:2])
    script = (
        f"Привет! Коротко о денежных потоках и рынке: {title}.\n\n"
        f"{angle}{kb_line}\n\n"
        f"Quantum Labs — платёжная инфраструктура. Подробности на сайте."
    )
    return {
        "format": "talking_head",
        "avatar_profile": profile,
        "duration_sec": 45,
        "visibility": "private",
        "approval_required": True,
        "script_text": script,
        "platforms": ["youtube", "instagram"],
        "series": "news-digest",
        "source_news_id": news_id,
        "kb_citations": citations or [],
        "note": "Рендер talking-head — провайдер подключается отдельно (HeyGen/Synthesia stub)",
    }


def process_news_item(
    store: Any,
    news_id: str,
    *,
    force: bool = False,
) -> dict[str, Any]:
    news = store.get_news(news_id)
    if not news:
        return {"ok": False, "error": "news_not_found"}
    if news.get("status") == "processed" and not force:
        return {"ok": True, "skipped": True, "news": news, "reason": "already_processed"}

    title = news.get("title") or ""
    body = news.get("body") or ""
    combined = f"{title}\n{body}"

    from modules.content_flywheel.thematic import analyze_news_themes, build_thematic_brief

    analysis = news.get("analysis") or {}
    if not analysis.get("theme_score") and hasattr(store, "analyze_news_item"):
        refreshed = store.analyze_news_item(news_id)
        if refreshed:
            news = refreshed
            analysis = news.get("analysis") or analyze_news_themes(title=title, body=body)
    elif not analysis:
        analysis = analyze_news_themes(title=title, body=body)

    theme_score = float(analysis.get("theme_score") or 0)
    if theme_score < theme_min_score() and not force:
        store.set_news_status(news_id, "skipped_theme")
        return {
            "ok": True,
            "skipped": True,
            "reason": "low_theme_relevance",
            "theme_score": theme_score,
            "theme_tier": analysis.get("theme_tier"),
            "analysis": analysis,
            "news_id": news_id,
        }

    memory = store.list_memory(limit=80)
    similar = find_similar(combined, memory, threshold=dedup_threshold())
    if similar and not force:
        store.set_news_status(news_id, "skipped_dup")
        return {
            "ok": True,
            "skipped": True,
            "reason": "duplicate_angle",
            "similar": similar[:3],
            "news_id": news_id,
        }

    kb_result: dict[str, Any] = {"ok": False, "skipped": True}
    if auto_kb():
        try:
            from knowledge_client import queue_flywheel_document

            kb_result = queue_flywheel_document(
                title=title,
                body=body,
                tags=["flywheel", "news", news.get("platform") or "source"],
                source_id=news_id,
            )
            store.set_news_kb_status(news_id, kb_result.get("status") or "queued")
        except Exception as exc:  # noqa: BLE001
            kb_result = {"ok": False, "error": str(exc)[:200]}

    fp = angle_fingerprint(title, body)
    occupied = store.occupied_slot_keys()
    slot = next_open_slot(occupied)
    if not slot:
        return {"ok": False, "error": "no_open_slot"}

    brief = build_thematic_brief(
        title=title,
        body=body,
        analysis=analysis,
        link=news.get("link") or "",
    )
    product_footer = ""
    kb_ctx: dict[str, Any] = {"enabled": False, "layer": "product_optional"}
    if use_product_kb():
        from knowledge_enrich import enrich_content_brief

        kb_ctx = enrich_content_brief(
            title=title,
            body=brief[:2000],
            link=news.get("link") or "",
            tenant_id=getattr(store, "tenant_id", "quantum-labs"),
        )
        kb_ctx["layer"] = "product_kb"
        brief = kb_ctx.get("brief_enriched") or brief
        product_footer = kb_ctx.get("product_paragraph") or ""

    variants = variants_from_brief(
        title=title,
        brief=brief,
        link=news.get("link") or "",
        product_footer=product_footer,
    )
    image_options = build_image_options(
        store,
        post_id=news_id,
        title=title,
        brief=brief[:200],
        original_url=news.get("image_url") or "",
    )
    video_brief = talking_head_brief(
        title=title,
        body=body,
        news_id=news_id,
        thematic_hook=analysis.get("editorial_hook") or "",
        product_paragraph=product_footer,
        citations=kb_ctx.get("citations") or [],
    )

    proposal = store.create_proposal(
        news_id=news_id,
        slot_key=slot["slot_key"],
        slot_at=slot["utc_time"],
        title=title,
        brief=brief,
        angle_fingerprint=fp,
        variants=variants,
        image_options=image_options,
        video_brief=video_brief,
        kb_context=kb_ctx,
        theme_context=analysis,
        dedup_score=0.0,
    )
    store.set_news_status(news_id, "processed")
    return {
        "ok": True,
        "news_id": news_id,
        "kb": kb_result,
        "slot": slot,
        "proposal": proposal,
        "similar_checked": len(memory),
        "theme_analysis": analysis,
        "kb_context": kb_ctx,
        "auto_outreach": False,
    }


def approve_proposal(store: Any, proposal_id: str) -> dict[str, Any]:
    prop = store.get_proposal(proposal_id)
    if not prop:
        return {"ok": False, "error": "proposal_not_found"}
    if prop.get("status") == "approved":
        return {"ok": True, "proposal": prop, "already": True}

    title = prop.get("title") or ""
    brief = prop.get("brief") or ""
    kb_ctx = prop.get("kb_context") or {}
    product_footer = kb_ctx.get("product_paragraph") or ""
    platforms = list((prop.get("variants") or {}).keys()) or [
        "telegram",
        "vk",
        "instagram",
        "youtube",
    ]

    from modules.social_publish import SocialPublishStore

    sp = SocialPublishStore(store.db_path, tenant_id=store.tenant_id)
    post = sp.create_post(
        title=title,
        brief=brief,
        platforms=platforms,
        link="",
        source=f"flywheel:{prop.get('news_id')}",
        generate_images=False,
        use_kb=False,
        kb_context=kb_ctx,
    )
    images = prop.get("image_options") or []
    selected = next((i for i in images if i.get("selected")), images[0] if images else None)
    if selected:
        post_images = [selected]
        sp_row = sp.get_post(post["id"])
        if sp_row:
            with sp.connect() as conn:
                conn.execute(
                    "UPDATE social_posts SET images_json = ? WHERE id = ?",
                    (json.dumps(post_images, ensure_ascii=False), post["id"]),
                )
        post = sp.get_post(post["id"]) or post

    sp.set_post_status(post["id"], "approved")

    video_draft_id = None
    vb = prop.get("video_brief") or {}
    if vb.get("script_text"):
        from modules.video_studio import VideoStudioStore

        vs = VideoStudioStore(store.db_path, tenant_id=store.tenant_id)
        draft = vs.create_draft(
            title=f"News: {title[:80]}",
            brief=brief[:500],
            script_text=vb.get("script_text") or "",
        )
        video_draft_id = draft.get("id")
        meta = {
            "talking_head": True,
            "avatar_profile": vb.get("avatar_profile"),
            "series": vb.get("series"),
            "flywheel_proposal_id": proposal_id,
            "approval_required": True,
        }
        with vs.connect() as conn:
            conn.execute(
                "UPDATE video_drafts SET meta_json = ? WHERE id = ?",
                (json.dumps(meta, ensure_ascii=False), video_draft_id),
            )

    store.remember_angle(
        topic=title,
        summary=brief[:500],
        fingerprint=prop.get("angle_fingerprint") or angle_fingerprint(title, brief),
        news_id=prop.get("news_id"),
        social_post_id=post.get("id"),
        video_draft_id=video_draft_id,
        slot_key=prop.get("slot_key"),
    )
    updated = store.set_proposal_status(
        proposal_id,
        "approved",
        social_post_id=post.get("id"),
        video_draft_id=video_draft_id,
    )
    return {
        "ok": True,
        "proposal": updated,
        "social_post": post,
        "video_draft_id": video_draft_id,
        "note": "Пост approved — репост вручную из вкладки Соцсети",
    }
