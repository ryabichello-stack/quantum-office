"""Platform-specific post text templates (rules-first, no auto-publish)."""

from __future__ import annotations

from typing import Any

PLATFORMS = ("telegram", "vk", "instagram", "youtube")

_DEFAULT_HASHTAGS = ["#новости", "#отрасль", "#бизнес"]


def _clip(text: str, limit: int) -> str:
    t = (text or "").strip()
    if len(t) <= limit:
        return t
    return t[: limit - 1].rstrip() + "…"


def _format_hashtags(hashtags: list[str] | None) -> str:
    tags = [h.strip() for h in (hashtags or _DEFAULT_HASHTAGS) if h.strip()]
    return " ".join(tags)


def variant_for_platform(
    *,
    platform: str,
    title: str,
    brief: str,
    link: str = "",
    product_footer: str = "",
    hashtags: list[str] | None = None,
) -> dict[str, Any]:
    p = (platform or "telegram").strip().lower()
    title = (title or "Новость").strip()
    brief = (brief or "").strip()
    if product_footer and product_footer not in brief:
        brief = f"{brief}\n\n{product_footer}".strip()
    tags = _format_hashtags(hashtags)
    link_line = f"\n\n{link}" if link else ""

    if p == "telegram":
        body = _clip(
            f"**{title}**\n\n{brief}\n\n{tags}{link_line}",
            4000,
        )
        return {
            "platform": p,
            "format": "message",
            "text": body,
            "parse_mode": "markdown",
            "max_length": 4096,
        }
    if p == "vk":
        body = _clip(f"{title}\n\n{brief}\n\n{tags}{link_line}", 15000)
        return {
            "platform": p,
            "format": "wall_post",
            "text": body,
            "attachments": ["image"],
            "max_length": 16384,
        }
    if p == "instagram":
        body = _clip(f"{title}\n\n{brief}\n\n{tags}{link_line}", 2200)
        return {
            "platform": p,
            "format": "feed_post",
            "caption": body,
            "requires_image": True,
            "max_length": 2200,
        }
    if p == "youtube":
        body = _clip(
            f"{title}\n\n{brief}\n\nCommunity / description draft.{link_line}\n\n{tags}",
            5000,
        )
        return {
            "platform": p,
            "format": "community_post",
            "text": body,
            "visibility": "private",
            "max_length": 5000,
        }
    return {"platform": p, "format": "text", "text": _clip(f"{title}\n\n{brief}", 2000)}


def variants_from_brief(
    *,
    title: str,
    brief: str,
    platforms: list[str] | None = None,
    link: str = "",
    product_footer: str = "",
    hashtags: list[str] | None = None,
) -> dict[str, dict[str, Any]]:
    selected = [p.strip().lower() for p in (platforms or list(PLATFORMS)) if p.strip()]
    selected = [p for p in selected if p in PLATFORMS]
    if not selected:
        selected = list(PLATFORMS)
    return {
        p: variant_for_platform(
            platform=p,
            title=title,
            brief=brief,
            link=link,
            product_footer=product_footer,
            hashtags=hashtags,
        )
        for p in selected
    }
