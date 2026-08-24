"""Telegram channel parser tests."""

from __future__ import annotations

from unittest.mock import patch

from modules.content_flywheel.ingest import poll_watch_sources
from modules.content_flywheel.tg_fetch import (
    fetch_channel_posts,
    normalize_channel_handle,
    parse_channel_html,
)

SAMPLE_HTML = """
<div class="tgme_widget_message_wrap js-widget_message_wrap">
<div class="tgme_widget_message" data-post="industry_news/42">
  <div class="tgme_widget_message_bubble">
    <div class="tgme_widget_message_text js-message_text" dir="auto">
      ЦБ поднял ключевую ставку. Ломбарды пересматривают выплаты.
    </div>
    <div class="tgme_widget_message_footer">
      <time datetime="2026-08-23T10:00:00+00:00">Aug 23</time>
    </div>
  </div>
</div>
</div>
<div class="tgme_widget_message_wrap js-widget_message_wrap">
<div class="tgme_widget_message" data-post="industry_news/43">
  <div class="tgme_widget_message_bubble">
    <div class="tgme_widget_message_text js-message_text" dir="auto">
      Новый тренд на рынке SaaS и B2B продуктов.
    </div>
    <time datetime="2026-08-23T12:00:00+00:00">Aug 23</time>
  </div>
</div>
</div>
"""


def test_normalize_channel_handle():
    assert normalize_channel_handle("@industry_news") == "industry_news"
    assert normalize_channel_handle("https://t.me/s/industry_news") == "industry_news"
    assert normalize_channel_handle("t.me/industry_news") == "industry_news"


def test_parse_channel_html():
    items = parse_channel_html(SAMPLE_HTML, channel="industry_news")
    assert len(items) == 2
    assert items[0]["message_id"] == 43
    assert "SaaS" in items[0]["body"]
    assert items[0]["link"] == "https://t.me/industry_news/43"
    assert items[0]["external_id"] == "industry_news/43"


def test_fetch_channel_posts_mocked():
    with patch("modules.content_flywheel.tg_fetch.urllib.request.urlopen") as mock_open:
        mock_open.return_value.__enter__.return_value.read.return_value = SAMPLE_HTML.encode()
        items = fetch_channel_posts("@industry_news", limit=5)
    assert len(items) == 2
    assert items[0]["title"]


def test_poll_ingests_telegram_posts():
    with patch.dict(
        "os.environ",
        {"FLYWHEEL_ENABLED": "true", "FLYWHEEL_SOURCE_TG": "@industry_news"},
        clear=False,
    ):
        with patch("modules.content_flywheel.ingest.fetch_channel_posts") as mock_tg:
            mock_tg.return_value = [
                {
                    "external_id": "industry_news/99",
                    "title": "Ставка ЦБ",
                    "body": "Рынок реагирует на решение регулятора.",
                    "link": "https://t.me/industry_news/99",
                    "image_url": "",
                    "published_at": "2026-08-23T10:00:00+00:00",
                    "raw": {"mode": "tg_public"},
                }
            ]
            items = poll_watch_sources()
    assert any(i["platform"] == "telegram" and i["external_id"] == "industry_news/99" for i in items)


def test_ingest_dedup_by_external_id():
    import tempfile
    from pathlib import Path

    from modules.content_flywheel import ContentFlywheelStore

    with tempfile.TemporaryDirectory() as tmp:
        store = ContentFlywheelStore(Path(tmp) / "m.db", tenant_id="default")
        first = store.ingest_news(
            platform="telegram",
            handle="@news",
            title="A",
            body="B",
            external_id="news/1",
        )
        dup = store.ingest_news(
            platform="telegram",
            handle="@news",
            title="A changed",
            body="B changed",
            external_id="news/1",
        )
        assert dup.get("duplicate") is True
        assert dup["id"] == first["id"]
