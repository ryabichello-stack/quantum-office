"""RSS fetch + flywheel worker tests."""

from __future__ import annotations

import json
from unittest.mock import patch

from modules.content_flywheel.flywheel_worker import auto_cycle_enabled, cycle_interval_seconds
from modules.content_flywheel.ingest import poll_watch_sources
from modules.content_flywheel.rss_fetch import fetch_feed_items, parse_feed_xml

SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Industry News</title>
    <item>
      <title>SaaS market grows 12%</title>
      <description><![CDATA[Enterprise adoption accelerates across regions.]]></description>
      <link>https://example.com/saas-growth</link>
      <guid>saas-1</guid>
      <pubDate>Mon, 23 Aug 2026 10:00:00 +0000</pubDate>
    </item>
  </channel>
</rss>
"""


def test_parse_rss_feed():
    items = parse_feed_xml(SAMPLE_RSS, feed_url="https://example.com/feed.xml")
    assert len(items) == 1
    assert items[0]["title"] == "SaaS market grows 12%"
    assert "Enterprise" in items[0]["body"]
    assert items[0]["link"] == "https://example.com/saas-growth"


def test_fetch_feed_items_mocked():
    with patch("modules.content_flywheel.rss_fetch.urllib.request.urlopen") as mock_open:
        mock_open.return_value.__enter__.return_value.read.return_value = SAMPLE_RSS.encode()
        items = fetch_feed_items("https://example.com/feed.xml")
    assert len(items) == 1
    assert items[0]["external_id"] == "saas-1"


def test_poll_includes_rss_handles():
    with patch.dict(
        "os.environ",
        {"FLYWHEEL_ENABLED": "true", "FLYWHEEL_SOURCE_RSS": "https://example.com/feed.xml"},
        clear=False,
    ):
        with patch("modules.content_flywheel.ingest.fetch_feed_items") as mock_fetch:
            mock_fetch.return_value = [
                {
                    "title": "Trend",
                    "body": "Body",
                    "link": "https://x",
                    "external_id": "e1",
                    "published_at": None,
                    "image_url": "",
                    "raw": {},
                }
            ]
            items = poll_watch_sources()
    assert any(i["platform"] == "rss" for i in items)


def test_cycle_interval_defaults():
    with patch.dict("os.environ", {}, clear=False):
        assert cycle_interval_seconds() >= 300


def test_auto_cycle_env():
    with patch.dict("os.environ", {"FLYWHEEL_AUTO_CYCLE": "true"}, clear=False):
        assert auto_cycle_enabled() is True
