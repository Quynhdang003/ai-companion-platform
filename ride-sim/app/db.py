"""SQLite storage, separate from the backend's database.

The tables are created at startup (no Alembic here). The simulator's state is disposable:
a database made for other tables is emptied and rebuilt (`SCHEMA_VERSION`).
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import DateTime, inspect
from sqlalchemy.engine import Dialect
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import TypeDecorator

logger = logging.getLogger(__name__)

# Bump on any change to the tables. Kept in SQLite's `user_version`; a database with
# another version is emptied at startup.
SCHEMA_VERSION = 2


class UtcDateTime(TypeDecorator[datetime]):
    """SQLite keeps no time zone: store UTC, read back aware UTC datetimes."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime: pass a timezone-aware one")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        return None if value is None else value.replace(tzinfo=UTC)


class Base(DeclarativeBase):
    pass


async def prepare_database(engine: AsyncEngine) -> None:
    """Create the tables, after emptying a database made by another schema version."""
    async with engine.begin() as conn:
        version = (await conn.exec_driver_sql("PRAGMA user_version")).scalar_one()
        if version != SCHEMA_VERSION:
            if await conn.run_sync(lambda sync: bool(inspect(sync).get_table_names())):
                logger.warning(
                    "Database schema %s, expected %s: starting empty", version, SCHEMA_VERSION
                )
                await conn.run_sync(Base.metadata.drop_all)
            await conn.exec_driver_sql(f"PRAGMA user_version = {SCHEMA_VERSION}")
        await conn.run_sync(Base.metadata.create_all)
