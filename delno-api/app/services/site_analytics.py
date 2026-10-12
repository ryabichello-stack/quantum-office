"""Record and aggregate first-party marketing site analytics."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.site_analytics import SitePageview
from app.services.rate_limit import InMemoryRateLimiter

_analytics_limiter = InMemoryRateLimiter()

_PATH_RE = re.compile(r"^/[A-Za-z0-9_\-./%~?=&#+]*$")
_SESSION_RE = re.compile(r"^[A-Za-z0-9_\-]{8,64}$")
_SITE_RE = re.compile(r"^[A-Za-z0-9._\-]{1,64}$")


def check_analytics_rate_limit(*, client_ip: str) -> bool:
    result = _analytics_limiter.check(f"analytics:{client_ip or 'unknown'}", limit=120, window_sec=60)
    return result.allowed


def hash_ip(ip: str | None, salt: str = "delno-analytics") -> str | None:
    if not ip:
        return None
    return hashlib.sha256(f"{salt}:{ip.strip()}".encode()).hexdigest()[:32]


def normalize_path(raw: str | None) -> str | None:
    if not raw or not isinstance(raw, str):
        return None
    path = raw.strip()[:512]
    if not path.startswith("/"):
        path = "/" + path
    # strip query for grouping (UTM kept separately)
    if "?" in path:
        path = path.split("?", 1)[0]
    if len(path) > 512 or not _PATH_RE.match(path):
        return None
    return path or "/"


def normalize_session_id(raw: str | None) -> str | None:
    if not raw or not isinstance(raw, str):
        return None
    sid = raw.strip()[:64]
    if not _SESSION_RE.match(sid):
        return None
    return sid


def normalize_site_key(raw: str | None) -> str:
    if not raw or not isinstance(raw, str):
        return "dlno.ru"
    key = raw.strip().lower()[:64]
    if not _SITE_RE.match(key):
        return "dlno.ru"
    return key


def truncate(raw: str | None, max_len: int) -> str | None:
    if not raw or not isinstance(raw, str):
        return None
    value = raw.strip()
    if not value:
        return None
    return value[:max_len]


def record_hit(
    db: Session,
    *,
    site_key: str,
    session_id: str,
    path: str,
    referrer: str | None = None,
    title: str | None = None,
    utm_source: str | None = None,
    utm_medium: str | None = None,
    utm_campaign: str | None = None,
    user_agent: str | None = None,
    ip_hash: str | None = None,
    event: str = "pageview",
    duration_ms: int | None = None,
    engaged: bool = False,
) -> SitePageview:
    event_name = (event or "pageview").strip().lower()[:32]
    if event_name not in {"pageview", "engage", "leave"}:
        event_name = "pageview"

    row = SitePageview(
        site_key=site_key,
        session_id=session_id,
        path=path,
        referrer=truncate(referrer, 1000),
        title=truncate(title, 255),
        utm_source=truncate(utm_source, 120),
        utm_medium=truncate(utm_medium, 120),
        utm_campaign=truncate(utm_campaign, 160),
        user_agent=truncate(user_agent, 512),
        ip_hash=ip_hash,
        event=event_name,
        duration_ms=max(0, min(duration_ms, 86_400_000)) if duration_ms is not None else None,
        engaged=bool(engaged) or event_name == "engage",
    )
    db.add(row)
    db.flush()
    return row


def _since(days: int) -> datetime:
    days = max(1, min(days, 90))
    return datetime.now(timezone.utc) - timedelta(days=days)


def _base_filter(db: Session, *, site_key: str, days: int):
    since = _since(days)
    return (
        db.query(SitePageview).filter(
            SitePageview.site_key == site_key,
            SitePageview.created_at >= since,
        ),
        since,
    )


def summarize(db: Session, *, site_key: str = "dlno.ru", days: int = 30) -> dict[str, Any]:
    q, since = _base_filter(db, site_key=site_key, days=days)
    rows = q.order_by(SitePageview.created_at.asc()).all()

    pageviews = [r for r in rows if r.event == "pageview"]
    sessions: dict[str, list[SitePageview]] = defaultdict(list)
    for r in pageviews:
        sessions[r.session_id].append(r)

    session_count = len(sessions)
    pageview_count = len(pageviews)

    bounced = 0
    engaged_sessions = 0
    for sid, hits in sessions.items():
        engaged = any(h.engaged for h in hits) or any(
            r.session_id == sid and (r.engaged or r.event == "engage") for r in rows
        )
        if engaged:
            engaged_sessions += 1
        if len(hits) <= 1 and not engaged:
            bounced += 1

    bounce_rate = round((bounced / session_count) * 100, 1) if session_count else 0.0
    pages_per_session = round(pageview_count / session_count, 2) if session_count else 0.0

    # Today / yesterday (UTC)
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - timedelta(days=1)
    sessions_today = {r.session_id for r in pageviews if r.created_at >= today_start}
    sessions_yesterday = {
        r.session_id for r in pageviews if yesterday_start <= r.created_at < today_start
    }
    pageviews_today = sum(1 for r in pageviews if r.created_at >= today_start)

    return {
        "site_key": site_key,
        "days": days,
        "since": since.isoformat(),
        "sessions": session_count,
        "pageviews": pageview_count,
        "bounce_rate": bounce_rate,
        "pages_per_session": pages_per_session,
        "engaged_sessions": engaged_sessions,
        "sessions_today": len(sessions_today),
        "sessions_yesterday": len(sessions_yesterday),
        "pageviews_today": pageviews_today,
    }


def timeseries(db: Session, *, site_key: str = "dlno.ru", days: int = 30) -> list[dict[str, Any]]:
    q, _since_dt = _base_filter(db, site_key=site_key, days=days)
    pageviews = q.filter(SitePageview.event == "pageview").all()

    by_day: dict[str, dict[str, Any]] = {}
    for r in pageviews:
        day = r.created_at.astimezone(timezone.utc).date().isoformat()
        bucket = by_day.setdefault(day, {"date": day, "pageviews": 0, "sessions": set()})
        bucket["pageviews"] += 1
        bucket["sessions"].add(r.session_id)

    out = []
    for day in sorted(by_day):
        bucket = by_day[day]
        out.append(
            {
                "date": day,
                "pageviews": bucket["pageviews"],
                "sessions": len(bucket["sessions"]),
            }
        )
    return out


def top_pages(db: Session, *, site_key: str = "dlno.ru", days: int = 30, limit: int = 20) -> list[dict[str, Any]]:
    since = _since(days)
    rows = (
        db.query(
            SitePageview.path,
            func.count(SitePageview.id).label("pageviews"),
            func.count(func.distinct(SitePageview.session_id)).label("sessions"),
        )
        .filter(
            SitePageview.site_key == site_key,
            SitePageview.created_at >= since,
            SitePageview.event == "pageview",
        )
        .group_by(SitePageview.path)
        .order_by(func.count(SitePageview.id).desc())
        .limit(min(limit, 100))
        .all()
    )
    return [
        {"path": path, "pageviews": int(pv), "sessions": int(sess)}
        for path, pv, sess in rows
    ]


def top_referrers(db: Session, *, site_key: str = "dlno.ru", days: int = 30, limit: int = 15) -> list[dict[str, Any]]:
    since = _since(days)
    rows = (
        db.query(SitePageview.referrer, SitePageview.session_id, SitePageview.utm_source)
        .filter(
            SitePageview.site_key == site_key,
            SitePageview.created_at >= since,
            SitePageview.event == "pageview",
        )
        .all()
    )

    # first hit per session
    first: dict[str, tuple[str | None, str | None]] = {}
    for referrer, session_id, utm_source in rows:
        if session_id not in first:
            first[session_id] = (referrer, utm_source)

    counts: dict[str, int] = defaultdict(int)
    for referrer, utm_source in first.values():
        label = "direct"
        if utm_source:
            label = f"utm:{utm_source}"
        elif referrer:
            # host only
            host = referrer
            if "://" in host:
                host = host.split("://", 1)[1]
            host = host.split("/", 1)[0].lower()
            if host.endswith("dlno.ru") or host.endswith("47z.ru"):
                label = "internal"
            else:
                label = host or "direct"
        counts[label] += 1

    ranked = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:limit]
    return [{"source": src, "sessions": n} for src, n in ranked]


def recent_hits(db: Session, *, site_key: str = "dlno.ru", limit: int = 50) -> list[dict[str, Any]]:
    rows = (
        db.query(SitePageview)
        .filter(SitePageview.site_key == site_key, SitePageview.event == "pageview")
        .order_by(SitePageview.created_at.desc())
        .limit(min(limit, 200))
        .all()
    )
    return [
        {
            "id": str(r.id),
            "path": r.path,
            "session_id": r.session_id[:8] + "…",
            "referrer": r.referrer,
            "utm_source": r.utm_source,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
