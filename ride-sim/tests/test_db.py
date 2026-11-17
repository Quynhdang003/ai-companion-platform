import sqlite3
from contextlib import closing
from pathlib import Path

from app.db import SCHEMA_VERSION
from tests.conftest import ClientFactory, FakeClock
from tests.helpers import get_booking, make_booking, make_quote


def _sqlite(path: Path, sql: str) -> list[tuple]:
    with closing(sqlite3.connect(path)) as conn, conn:
        return conn.execute(sql).fetchall()


def test_database_of_another_schema_version_starts_empty(
    tmp_path: Path, make_client: ClientFactory
) -> None:
    path = tmp_path / "old.db"
    _sqlite(path, "CREATE TABLE quotes (id TEXT PRIMARY KEY, price INTEGER)")
    _sqlite(path, "INSERT INTO quotes VALUES ('old', 1)")

    client = make_client("old.db")

    assert make_quote(client)["id"]
    assert _sqlite(path, "PRAGMA user_version") == [(SCHEMA_VERSION,)]
    assert _sqlite(path, "SELECT count(*) FROM quotes WHERE id = 'old'") == [(0,)]


def test_database_of_this_version_is_kept(make_client: ClientFactory, clock: FakeClock) -> None:
    booking = make_booking(make_client("same.db"))
    clock.advance(20)

    assert get_booking(make_client("same.db"), booking["id"])["driver"] is not None
