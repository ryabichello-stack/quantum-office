"""party_cache table — E1.12 DaData enrichment cache."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "002_party_cache"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "party_cache",
        sa.Column("inn", sa.String(length=12), nullable=False),
        sa.Column("ogrn", sa.String(length=20), nullable=True),
        sa.Column("company_name", sa.String(length=255), nullable=True),
        sa.Column("director_name", sa.String(length=255), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("okved", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=True),
        sa.Column("party_type", sa.String(length=32), nullable=True),
        sa.Column("raw_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("inn"),
    )


def downgrade() -> None:
    op.drop_table("party_cache")
