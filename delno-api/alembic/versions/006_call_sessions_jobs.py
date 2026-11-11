"""call_sessions + call_jobs — Office OS telephony memory"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "006_call_sessions_jobs"
down_revision = "005_onboarding_uploads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "call_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("leads.id"), nullable=True),
        sa.Column("to_e164", sa.String(20), nullable=False),
        sa.Column("from_did", sa.String(20), nullable=True),
        sa.Column("script", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("created_by", sa.String(64), nullable=False, server_default="hermes"),
        sa.Column("result_session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("meta", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_call_jobs_tenant_id", "call_jobs", ["tenant_id"])
    op.create_index("ix_call_jobs_to_e164", "call_jobs", ["to_e164"])
    op.create_index("ix_call_jobs_status", "call_jobs", ["status"])

    op.create_table(
        "call_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id"),
            nullable=True,
        ),
        sa.Column("call_job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("call_jobs.id"), nullable=True),
        sa.Column("direction", sa.String(16), nullable=False, server_default="inbound"),
        sa.Column("status", sa.String(32), nullable=False, server_default="ringing"),
        sa.Column("from_e164", sa.String(20), nullable=True),
        sa.Column("to_e164", sa.String(20), nullable=True),
        sa.Column("did_e164", sa.String(20), nullable=True),
        sa.Column("external_id", sa.String(120), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_sec", sa.Integer(), nullable=True),
        sa.Column("outcome", sa.String(64), nullable=True),
        sa.Column("transcript", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("meta", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_call_sessions_tenant_id", "call_sessions", ["tenant_id"])
    op.create_index("ix_call_sessions_conversation_id", "call_sessions", ["conversation_id"])
    op.create_index("ix_call_sessions_call_job_id", "call_sessions", ["call_job_id"])
    op.create_index("ix_call_sessions_from_e164", "call_sessions", ["from_e164"])
    op.create_index("ix_call_sessions_to_e164", "call_sessions", ["to_e164"])
    op.create_index("ix_call_sessions_did_e164", "call_sessions", ["did_e164"])
    op.create_index("ix_call_sessions_external_id", "call_sessions", ["external_id"])

def downgrade() -> None:
    op.drop_index("ix_call_sessions_external_id", table_name="call_sessions")
    op.drop_index("ix_call_sessions_did_e164", table_name="call_sessions")
    op.drop_index("ix_call_sessions_to_e164", table_name="call_sessions")
    op.drop_index("ix_call_sessions_from_e164", table_name="call_sessions")
    op.drop_index("ix_call_sessions_call_job_id", table_name="call_sessions")
    op.drop_index("ix_call_sessions_conversation_id", table_name="call_sessions")
    op.drop_index("ix_call_sessions_tenant_id", table_name="call_sessions")
    op.drop_table("call_sessions")
    op.drop_index("ix_call_jobs_status", table_name="call_jobs")
    op.drop_index("ix_call_jobs_to_e164", table_name="call_jobs")
    op.drop_index("ix_call_jobs_tenant_id", table_name="call_jobs")
    op.drop_table("call_jobs")
