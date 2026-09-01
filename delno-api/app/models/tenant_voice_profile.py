import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class TenantVoiceProfile(Base):
    __tablename__ = "tenant_voice_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), unique=True, index=True)
    mode: Mapped[str] = mapped_column(String(32), default="preset")  # preset|cloned
    provider: Mapped[str] = mapped_column(String(32), default="openai")
    preset_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    clone_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    language: Mapped[str] = mapped_column(String(16), default="ru")
    sample_status: Mapped[str] = mapped_column(String(32), default="none")
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
