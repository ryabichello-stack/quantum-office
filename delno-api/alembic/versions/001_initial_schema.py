"""Initial DELNO schema

Revision ID: 001_initial
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # create_all equivalent — idempotent via alembic version table
    bind = op.get_bind()
    from app.core.db import Base
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    from app.core.db import Base
    import app.models  # noqa: F401

    Base.metadata.drop_all(bind=bind)
