"""First-party site analytics: hit ingest + summary aggregation."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.v1.public import PublicAnalyticsHit, public_analytics_hit
from app.models.site_analytics import SitePageview
from app.services import site_analytics as analytics


def test_normalize_path_strips_query():
    assert analytics.normalize_path("/blog/ai?utm_source=x") == "/blog/ai"
    assert analytics.normalize_path("v2") == "/v2"
    assert analytics.normalize_path("javascript:alert(1)") is None


def test_normalize_session_id():
    assert analytics.normalize_session_id("abcd1234") == "abcd1234"
    assert analytics.normalize_session_id("bad id") is None
    assert analytics.normalize_session_id("short") is None


def test_summarize_bounce_and_sessions():
    db = MagicMock()
    now = datetime.now(timezone.utc)
    sid_a = "sessionaaaa1111"
    sid_b = "sessionbbbb2222"

    rows = [
        SitePageview(
            id=uuid.uuid4(),
            site_key="dlno.ru",
            session_id=sid_a,
            path="/",
            event="pageview",
            engaged=False,
            created_at=now - timedelta(hours=2),
        ),
        SitePageview(
            id=uuid.uuid4(),
            site_key="dlno.ru",
            session_id=sid_b,
            path="/",
            event="pageview",
            engaged=False,
            created_at=now - timedelta(hours=1),
        ),
        SitePageview(
            id=uuid.uuid4(),
            site_key="dlno.ru",
            session_id=sid_b,
            path="/pricing",
            event="pageview",
            engaged=True,
            created_at=now - timedelta(minutes=50),
        ),
    ]

    query = MagicMock()
    query.filter.return_value = query
    query.order_by.return_value = query
    query.all.return_value = rows
    db.query.return_value = query

    summary = analytics.summarize(db, site_key="dlno.ru", days=7)
    assert summary["sessions"] == 2
    assert summary["pageviews"] == 3
    assert summary["bounce_rate"] == 50.0  # sid_a only, no engage
    assert summary["pages_per_session"] == 1.5


def test_public_analytics_hit_persists():
    db = MagicMock()
    request = MagicMock()
    request.headers = {"user-agent": "pytest"}
    request.client = MagicMock(host="1.2.3.4")

    body = PublicAnalyticsHit(
        site_key="dlno.ru",
        session_id="abcdef12",
        path="/blog",
        referrer="https://yandex.ru/search",
        event="pageview",
    )

    with patch("app.api.v1.public.site_analytics_svc.check_analytics_rate_limit", return_value=True):
        result = public_analytics_hit(body, request=request, db=db)

    assert result == {"ok": True}
    db.add.assert_called_once()
    db.commit.assert_called_once()
    row = db.add.call_args.args[0]
    assert isinstance(row, SitePageview)
    assert row.path == "/blog"
    assert row.session_id == "abcdef12"


def test_public_analytics_hit_rate_limited():
    db = MagicMock()
    request = MagicMock()
    request.headers = {}
    request.client = MagicMock(host="9.9.9.9")
    body = PublicAnalyticsHit(session_id="abcdef12", path="/")

    with patch("app.api.v1.public.site_analytics_svc.check_analytics_rate_limit", return_value=False):
        with pytest.raises(HTTPException) as exc:
            public_analytics_hit(body, request=request, db=db)
    assert exc.value.status_code == 429
