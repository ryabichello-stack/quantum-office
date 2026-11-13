"""Normalized map: tenant → Hermes profile → worker (multi-tenant control plane).

One company (tenant) owns exactly one company_main profile in MVP.
Workers are pool members sized by load — not one container per tenant.
A profile may move between workers, but never be open on two workers at once.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class HermesWorker(Base):
    __tablename__ = "hermes_workers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    worker_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    base_url: Mapped[str] = mapped_column(String(500))
    api_server_key_env: Mapped[str] = mapped_column(String(128), default="HERMES_API_SERVER_KEY")
    image_digest: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="ready", index=True)
    # Soft capacity: how many company profiles this multiplex worker may host (None = unlimited).
    max_profiles: Mapped[int | None] = mapped_column(Integer, nullable=True, default=64)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class HermesProfile(Base):
    __tablename__ = "hermes_profiles"
    __table_args__ = (
        UniqueConstraint("tenant_id", "agent_id", name="uq_hermes_profiles_tenant_agent"),
        UniqueConstraint("profile_id", name="uq_hermes_profiles_profile_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    # Logical Hermes profile name (HERMES_HOME / profile id), never shared across tenants.
    profile_id: Mapped[str] = mapped_column(String(120), index=True)
    agent_id: Mapped[str] = mapped_column(String(64), default="company_main")
    # Exclusive: at most one open worker. NULL while provisioning / retired.
    worker_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("hermes_workers.worker_id"), nullable=True, index=True
    )
    # Path Hermes process actually reads (must be visible to the worker, not only API disk).
    state_location: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(32), default="provisioning", index=True)
    pin: Mapped[str] = mapped_column(String(64), default="v0.23.1")
    credential_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # MVP: single owner; keep actor for future employees without schema rewrite.
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class HermesRunBinding(Base):
    """Server-side bind: Hermes run ↔ scoped MCP token (no long-lived tenant key in the model)."""

    __tablename__ = "hermes_run_bindings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    profile_id: Mapped[str] = mapped_column(String(120), index=True)
    worker_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    run_id: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    session_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    agent_id: Mapped[str] = mapped_column(String(64), default="company_main")
    token_hash: Mapped[str] = mapped_column(String(64))
    tool_ids: Mapped[list] = mapped_column(JSONB, default=list)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
