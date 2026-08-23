"""Social Publish — multi-platform posts, channels, images, reposts."""

from __future__ import annotations

import tempfile
from pathlib import Path

from modules.social_publish import SocialPublishStore
from modules.social_publish.image_gen import render_social_card_svg, write_social_card
from modules.social_publish.post_templates import variants_from_brief


def test_variants_for_all_platforms():
    v = variants_from_brief(
        title="Выплаты",
        brief="Инфраструктура для ломбардов",
        platforms=["telegram", "vk", "instagram", "youtube"],
    )
    assert set(v.keys()) == {"telegram", "vk", "instagram", "youtube"}
    assert v["instagram"].get("requires_image") is True
    assert v["youtube"].get("visibility") == "private"


def test_svg_image_generation(tmp_path: Path):
    svg = render_social_card_svg(title="Test", subtitle="Brief line")
    assert "svg" in svg and "Test" in svg
    out = write_social_card(tmp_path, post_id="abc-123", title="Hello", subtitle="World")
    assert Path(out["path"]).is_file()


def test_channel_post_approve_repost_flow():
    with tempfile.TemporaryDirectory() as tmp:
        store = SocialPublishStore(Path(tmp) / "m.db")
        ch_tg = store.add_channel(platform="telegram", title="News", handle="@ql_news")
        ch_vk = store.add_channel(platform="vk", title="VK", handle="club123")
        post = store.create_post(
            title="Оффер",
            brief="Quantum Labs — выплаты для ломбардов",
            platforms=["telegram", "vk"],
            generate_images=True,
        )
        assert post["status"] == "draft"
        assert post["images"]
        assert "telegram" in post["variants"]
        out = store.queue_repost(post["id"], [ch_tg["id"], ch_vk["id"]])
        assert out["ok"] is False
        assert out["error"] == "approval_required"
        store.set_post_status(post["id"], "approved")
        out2 = store.queue_repost(post["id"], [ch_tg["id"], ch_vk["id"]])
        assert out2["ok"] is True
        assert len(out2["jobs"]) == 2
        jobs = store.list_jobs(post["id"])
        assert len(jobs) == 2
        updated = store.get_post(post["id"])
        assert updated and updated["status"] == "published"
