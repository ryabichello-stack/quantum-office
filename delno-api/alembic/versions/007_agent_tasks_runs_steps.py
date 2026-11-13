"""agent_tasks / agent_runs / agent_steps — Hermes durable control plane"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "007_agent_tasks_runs_steps"
down_revision = "006_call_sessions_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("trigger_kind", sa.String(32), nullable=False, server_default="manual"),
        sa.Column("trigger_config", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("policy", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("hermes_cron_id", sa.String(120), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_agent_tasks_tenant_id", "agent_tasks", ["tenant_id"])
    op.create_index("ix_agent_tasks_status", "agent_tasks", ["status"])

    op.create_table(
        "agent_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agent_tasks.id"), nullable=True),
        sa.Column("hermes_run_id", sa.String(120), nullable=True),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("conversations.id"), nullable=True),
        sa.Column("trigger_event_id", sa.String(120), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("checkpoint", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("usage", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_agent_runs_tenant_id", "agent_runs", ["tenant_id"])
    op.create_index("ix_agent_runs_status", "agent_runs", ["status"])
    op.create_index("ix_agent_runs_hermes_run_id", "agent_runs", ["hermes_run_id"])

    op.create_table(
        "agent_steps",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agent_runs.id"), nullable=False),
        sa.Column("parent_step_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("kind", sa.String(32), nullable=False, server_default="tool"),
        sa.Column("tool_id", sa.String(120), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="running"),
        sa.Column("safe_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("result_ref", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_agent_steps_tenant_id", "agent_steps", ["tenant_id"])
    op.create_index("ix_agent_steps_run_id", "agent_steps", ["run_id"])


def downgrade() -> None:
    op.drop_table("agent_steps")
    op.drop_table("agent_runs")
    op.drop_table("agent_tasks")
