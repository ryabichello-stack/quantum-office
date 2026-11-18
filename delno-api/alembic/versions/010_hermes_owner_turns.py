"""Curated, actor-scoped Hermes memory and bounded dialogue summaries."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "010_hermes_owner_turns"
down_revision = "009_tenant_folders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Claim legacy Owner transcripts only when the tenant has exactly one
    # account. Multi-user transcripts have no reliable owner and stay hidden.
    op.execute("""
        UPDATE conversations AS c
        SET meta = jsonb_set(COALESCE(c.meta, '{}'::jsonb), '{owner_user_id}', to_jsonb(u.id::text), true)
        FROM (
            SELECT tenant_id, MIN(id::text)::uuid AS id
            FROM users GROUP BY tenant_id HAVING COUNT(*) = 1
        ) AS u
        WHERE c.tenant_id = u.tenant_id AND c.channel = 'hermes'
          AND NOT COALESCE(c.meta, '{}'::jsonb) ? 'owner_user_id'
    """)
    op.create_table(
        "hermes_owner_turns",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", sa.String(200), nullable=False),
        sa.Column("run_id", sa.String(120), nullable=False),
        sa.Column("summary", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "run_id", name="uq_hermes_owner_turn_tenant_run"),
    )
    op.create_index("ix_hermes_owner_turn_scope_time", "hermes_owner_turns", ["tenant_id", "user_id", "created_at"])
    op.create_table(
        "hermes_memories",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("memory_key", sa.String(120), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column("history", JSONB, nullable=False),
        sa.Column("source_run_id", sa.String(120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "user_id", "memory_key", name="uq_hermes_memory_scope_key"),
    )
    op.create_index("ix_hermes_memories_tenant_id", "hermes_memories", ["tenant_id"])
    op.create_index("ix_hermes_memories_user_id", "hermes_memories", ["user_id"])
    op.create_table(
        "hermes_memory_blocks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("memory_key", sa.String(120), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "user_id", "key_hash", name="uq_hermes_memory_block_scope_hash"),
    )
    op.create_table(
        "hermes_memory_states",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("epoch", sa.Integer, nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_hermes_memory_state_scope"),
    )


def downgrade() -> None:
    op.drop_table("hermes_memory_states")
    op.drop_table("hermes_memory_blocks")
    op.drop_index("ix_hermes_memories_user_id", table_name="hermes_memories")
    op.drop_index("ix_hermes_memories_tenant_id", table_name="hermes_memories")
    op.drop_table("hermes_memories")
    op.drop_index("ix_hermes_owner_turn_scope_time", table_name="hermes_owner_turns")
    op.drop_table("hermes_owner_turns")
