"""Apply additive schema changes on existing prod DB."""

from sqlalchemy import text

from app.core.db import engine


def migrate() -> None:
    stmts = [
        "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS public_key VARCHAR(64)",
        "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS plan VARCHAR(32) DEFAULT 'trial'",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255)",
        "UPDATE tenants SET public_key = encode(gen_random_bytes(18), 'base64') WHERE public_key IS NULL",
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_tenants_public_key ON tenants (public_key)",
    ]
    with engine.begin() as conn:
        for sql in stmts:
            conn.execute(text(sql))


if __name__ == "__main__":
    migrate()
    print("migrate_ok")
