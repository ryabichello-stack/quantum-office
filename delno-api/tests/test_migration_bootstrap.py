"""PostgreSQL regression for the historical create_all Alembic baseline.

Run only in an isolated nonproduction database with
DELNO_MIGRATION_TEST=1 pytest tests/test_migration_bootstrap.py.
"""

import os
import subprocess
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


@pytest.mark.parametrize("existing_schema", [False, True])
def test_upgrade_head_on_fresh_and_existing_database(existing_schema):
    if os.getenv("DELNO_MIGRATION_TEST") != "1":
        pytest.skip("requires explicit nonproduction PostgreSQL opt-in")

    source_url = make_url(os.environ["DATABASE_URL"])
    assert source_url.database.startswith("delno_uat"), "nonproduction UAT only"
    test_name = "delno_uat_migration_" + uuid.uuid4().hex[:12]
    admin_url = source_url.set(database="postgres")
    test_url = source_url.set(database=test_name)
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")

    try:
        with admin_engine.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{test_name}"'))
        if existing_schema:
            from app.core.db import Base
            import app.models  # noqa: F401

            engine = create_engine(test_url)
            try:
                Base.metadata.create_all(engine)
            finally:
                engine.dispose()

        env = os.environ.copy()
        env["DATABASE_URL"] = test_url.render_as_string(hide_password=False)
        subprocess.run(["alembic", "upgrade", "head"], env=env, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

        engine = create_engine(test_url)
        try:
            with engine.connect() as connection:
                version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                assert version == "010_hermes_owner_turns"
                count = connection.execute(text(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = 'party_cache'"
                )).scalar_one()
                assert count == 1
        finally:
            engine.dispose()
    finally:
        with admin_engine.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{test_name}" WITH (FORCE)'))
        admin_engine.dispose()
