"""site_pageviews — first-party marketing analytics"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "006_site_pageviews"
down_revision = "005_onboarding_uploads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "site_pageviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("site_key", sa.String(64), nullable=False, server_default="dlno.ru"),
        sa.Column("session_id", sa.String(64), nullable=False),
        sa.Column("path", sa.String(512), nullable=False),
        sa.Column("referrer", sa.Text(), nullable=True),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("utm_source", sa.String(120), nullable=True),
        sa.Column("utm_medium", sa.String(120), nullable=True),
        sa.Column("utm_campaign", sa.String(160), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("ip_hash", sa.String(64), nullable=True),
        sa.Column("event", sa.String(32), nullable=False, server_default="pageview"),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("engaged", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_site_pageviews_site_key", "site_pageviews", ["site_key"])
    op.create_index("ix_site_pageviews_site_created", "site_pageviews", ["site_key", "created_at"])
    op.create_index("ix_site_pageviews_session", "site_pageviews", ["session_id"])
    op.create_index("ix_site_pageviews_path", "site_pageviews", ["path"])


def downgrade() -> None:
    op.drop_index("ix_site_pageviews_path", table_name="site_pageviews")
    op.drop_index("ix_site_pageviews_session", table_name="site_pageviews")
    op.drop_index("ix_site_pageviews_site_created", table_name="site_pageviews")
    op.drop_index("ix_site_pageviews_site_key", table_name="site_pageviews")
    op.drop_table("site_pageviews")
