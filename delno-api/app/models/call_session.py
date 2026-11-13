"""Telephony call sessions — Office Memory for inbound/outbound voice."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class CallSession(Base):
    __tablename__ = "call_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), index=True)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=True, index=True
    )
    call_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("call_jobs.id"), nullable=True, index=True
    )
    direction: Mapped[str] = mapped_column(String(16), default="inbound")  # inbound|outbound
    status: Mapped[str] = mapped_column(String(32), default="ringing")  # ringing|active|ended|failed
    from_e164: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    to_e164: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    did_e164: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    external_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)  # Asterisk uniqueid
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(64), nullable=True)
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
