from collections.abc import Callable, Iterator
from contextlib import ExitStack
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

# 10:00 in Vietnam: off-peak.
START = datetime(2026, 11, 16, 3, 0, tzinfo=UTC)
TEST_SEED = 7

ClientFactory = Callable[..., TestClient]


class FakeClock:
    """The simulator's clock in tests: time only moves when a test moves it."""

    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


def sim_settings(db_path: Path, **overrides: Any) -> Settings:
    values = {"seed": TEST_SEED, **overrides}
    return Settings(
        _env_file=None, database_url=f"sqlite+aiosqlite:///{db_path.as_posix()}", **values
    )


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(START)


@pytest.fixture
def make_client(tmp_path: Path, clock: FakeClock) -> Iterator[ClientFactory]:
    """Start a simulator on a database file in the test's temp folder.

    `make_client(time_scale=30)` overrides settings; the same `db_name` twice is a restart
    on the same data.
    """
    with ExitStack() as stack:

        def make(db_name: str = "sim.db", **overrides: Any) -> TestClient:
            app = create_app(sim_settings(tmp_path / db_name, **overrides), clock=clock)
            return stack.enter_context(TestClient(app))

        yield make


@pytest.fixture
def client(make_client: ClientFactory) -> TestClient:
    return make_client()
