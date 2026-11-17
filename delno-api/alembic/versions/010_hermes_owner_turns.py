"""Durable, actor-scoped Hermes owner dialogue history."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "010_hermes_owner_turns"
down_revision = "009_tenant_folders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hermes_owner_turns",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", sa.String(200), nullable=False),
        sa.Column("run_id", sa.String(120), nullable=False),
        sa.Column("request_text", sa.Text, nullable=False),
        sa.Column("response_text", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "run_id", name="uq_hermes_owner_turn_tenant_run"),
    )
    op.create_index("ix_hermes_owner_turn_scope_time", "hermes_owner_turns", ["tenant_id", "user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_hermes_owner_turn_scope_time", table_name="hermes_owner_turns")
    op.drop_table("hermes_owner_turns")
