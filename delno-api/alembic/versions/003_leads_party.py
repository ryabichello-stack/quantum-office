"""leads party fields — E1.13"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "003_leads_party"
down_revision = "002_party_cache"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("inn", sa.String(length=12), nullable=True))
    op.add_column("leads", sa.Column("party_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("leads", sa.Column("party_enriched_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_leads_inn", "leads", ["inn"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_leads_inn", table_name="leads")
    op.drop_column("leads", "party_enriched_at")
    op.drop_column("leads", "party_json")
    op.drop_column("leads", "inn")
