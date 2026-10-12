"""Platform admin: first-party marketing site analytics."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import require_platform_admin
from app.core.db import get_db
from app.models.user import User
from app.services import site_analytics as analytics

router = APIRouter(prefix="/admin/analytics", tags=["admin-analytics"])


@router.get("/summary")
def analytics_summary(
    days: int = Query(default=30, ge=1, le=90),
    site: str = Query(default="dlno.ru", max_length=64),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_platform_admin),
) -> dict:
    site_key = analytics.normalize_site_key(site)
    return analytics.summarize(db, site_key=site_key, days=days)


@router.get("/timeseries")
def analytics_timeseries(
    days: int = Query(default=30, ge=1, le=90),
    site: str = Query(default="dlno.ru", max_length=64),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_platform_admin),
) -> dict:
    site_key = analytics.normalize_site_key(site)
    return {"site_key": site_key, "days": days, "points": analytics.timeseries(db, site_key=site_key, days=days)}


@router.get("/pages")
def analytics_pages(
    days: int = Query(default=30, ge=1, le=90),
    site: str = Query(default="dlno.ru", max_length=64),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_platform_admin),
) -> dict:
    site_key = analytics.normalize_site_key(site)
    return {
        "site_key": site_key,
        "days": days,
        "pages": analytics.top_pages(db, site_key=site_key, days=days, limit=limit),
    }


@router.get("/referrers")
def analytics_referrers(
    days: int = Query(default=30, ge=1, le=90),
    site: str = Query(default="dlno.ru", max_length=64),
    limit: int = Query(default=15, ge=1, le=50),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_platform_admin),
) -> dict:
    site_key = analytics.normalize_site_key(site)
    return {
        "site_key": site_key,
        "days": days,
        "referrers": analytics.top_referrers(db, site_key=site_key, days=days, limit=limit),
    }


@router.get("/recent")
def analytics_recent(
    site: str = Query(default="dlno.ru", max_length=64),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_platform_admin),
) -> dict:
    site_key = analytics.normalize_site_key(site)
    return {"site_key": site_key, "hits": analytics.recent_hits(db, site_key=site_key, limit=limit)}
