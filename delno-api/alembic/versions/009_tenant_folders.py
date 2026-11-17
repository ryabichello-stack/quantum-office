"""Tenant-owned folders for cabinet files."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "009_tenant_folders"
down_revision = "008_appointments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_folders",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("parent_id", UUID(as_uuid=True), sa.ForeignKey("tenant_folders.id"), nullable=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_tenant_folders_tenant_id", "tenant_folders", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_tenant_folders_tenant_id", table_name="tenant_folders")
    op.drop_table("tenant_folders")
