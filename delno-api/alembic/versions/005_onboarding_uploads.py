"""onboarding_uploads — O3 file ingest"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "005_onboarding_uploads"
down_revision = "004_leads_conversation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "onboarding_uploads",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id"),
            nullable=True,
        ),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=True),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("parse_status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("extracted_document_id", sa.String(120), nullable=True),
        sa.Column("meta", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_onboarding_uploads_tenant_id", "onboarding_uploads", ["tenant_id"])
    op.create_index("ix_onboarding_uploads_conversation_id", "onboarding_uploads", ["conversation_id"])


def downgrade() -> None:
    op.drop_index("ix_onboarding_uploads_conversation_id", table_name="onboarding_uploads")
    op.drop_index("ix_onboarding_uploads_tenant_id", table_name="onboarding_uploads")
    op.drop_table("onboarding_uploads")
