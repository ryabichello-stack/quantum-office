"""leads conversation_id — E3.8 widget lead capture"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "004_leads_conversation"
down_revision = "003_leads_party"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "leads",
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_leads_conversation_id",
        "leads",
        "conversations",
        ["conversation_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_leads_conversation_id", "leads", ["conversation_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_leads_conversation_id", table_name="leads")
    op.drop_constraint("fk_leads_conversation_id", "leads", type_="foreignkey")
    op.drop_column("leads", "conversation_id")
