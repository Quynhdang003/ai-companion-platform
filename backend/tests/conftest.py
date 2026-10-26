import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import asyncpg
import pytest
from alembic.config import Config
from sqlalchemy import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from alembic import command
from app.core.config import get_settings

BACKEND_DIR = Path(__file__).resolve().parents[1]


def alembic_config(db_url: str) -> Config:
    config = Config(BACKEND_DIR / "alembic.ini")
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", db_url.replace("%", "%%"))
    return config


async def _recreate_database(db_url: str) -> None:
    url = make_url(db_url)
    # Guard against pointing the suite at the dev database: it gets dropped.
    if url.database is None or not url.database.endswith("_test"):
        raise RuntimeError(f"Refusing to recreate non-test database {url.database!r}")
    admin_url = url.set(drivername="postgresql", database="postgres")
    conn = await asyncpg.connect(admin_url.render_as_string(hide_password=False))
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)')
        await conn.execute(f'CREATE DATABASE "{url.database}"')
    finally:
        await conn.close()


@pytest.fixture(scope="session")
def migrated_db() -> str:
    """Fresh test database at Alembic head; returns its URL."""
    db_url = get_settings().test_database_url
    asyncio.run(_recreate_database(db_url))
    command.upgrade(alembic_config(db_url), "head")
    return db_url


@pytest.fixture
async def session(migrated_db: str) -> AsyncIterator[AsyncSession]:
    """Session inside an outer transaction that is rolled back after each test."""
    engine = create_async_engine(migrated_db, poolclass=NullPool)
    async with engine.connect() as conn:
        trans = await conn.begin()
        async with AsyncSession(bind=conn, join_transaction_mode="create_savepoint") as s:
            yield s
        await trans.rollback()
    await engine.dispose()
