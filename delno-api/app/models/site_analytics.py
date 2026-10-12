"""First-party marketing site pageviews (independent of Yandex Metrika)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class SitePageview(Base):
    __tablename__ = "site_pageviews"
    __table_args__ = (
        Index("ix_site_pageviews_site_created", "site_key", "created_at"),
        Index("ix_site_pageviews_session", "session_id"),
        Index("ix_site_pageviews_path", "path"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    site_key: Mapped[str] = mapped_column(String(64), default="dlno.ru", index=True)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False)
    path: Mapped[str] = mapped_column(String(512), nullable=False)
    referrer: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    utm_source: Mapped[str | None] = mapped_column(String(120), nullable=True)
    utm_medium: Mapped[str | None] = mapped_column(String(120), nullable=True)
    utm_campaign: Mapped[str | None] = mapped_column(String(160), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # pageview | engage | leave
    event: Mapped[str] = mapped_column(String(32), default="pageview", nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    engaged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
