"""Tenant-owned calendar appointments."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "008_appointments"
down_revision = "007_agent_tasks_runs_steps"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "appointments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("contact_phone", sa.String(32)),
        sa.Column("contact_email", sa.String(255)),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("external_user_id", sa.String(160)),
        sa.Column("conference_url", sa.Text()),
        sa.Column("external_event_id", sa.String(255)),
        sa.Column("external_provider", sa.String(32)),
        sa.Column("sync_status", sa.String(32), nullable=False),
        sa.Column("sync_version", sa.Integer(), nullable=False),
        sa.Column("sync_error", sa.Text()),
        sa.Column("meta", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_appointments_tenant_start", "appointments", ["tenant_id", "start_at"])
    op.create_index("ix_appointments_tenant_phone", "appointments", ["tenant_id", "contact_phone"])
    op.create_index("ix_appointments_tenant_channel", "appointments", ["tenant_id", "channel", "external_user_id"])


def downgrade() -> None:
    op.drop_table("appointments")
