import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class OnboardingUpload(Base):
    __tablename__ = "onboarding_uploads"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), index=True)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=True, index=True
    )
    file_name: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    storage_path: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    parse_status: Mapped[str] = mapped_column(String(32), default="pending")
    extracted_document_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
