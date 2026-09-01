import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), index=True)
    source: Mapped[str] = mapped_column(String(120), default="website")
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(60))
    email: Mapped[str | None] = mapped_column(String(160), nullable=True)
    company: Mapped[str | None] = mapped_column(String(160), nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    inn: Mapped[str | None] = mapped_column(String(12), nullable=True, index=True)
    party_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    party_enriched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="new")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
