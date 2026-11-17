from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.scheduler import start_scheduler
from app.models import CancelReason, ElderStatus, RideBooking, RideStatus
from app.services.ride.provider import (
    ProviderBooking,
    RideProviderUnavailableError,
    RideRequestRefusedError,
)
from app.services.ride.sync import run_ride_sync_job
from tests.conftest import add_elder, same_session, start_call
from tests.fakes import FakeRideProvider
from tests.ride_helpers import BACH_MAI, CHO_HOM, LANG_HA, book_trip

pytestmark = pytest.mark.usefixtures("no_confirm_wait")


@pytest.fixture
async def two_rides(
    client: AsyncClient, session: AsyncSession, rides: FakeRideProvider
) -> list[str]:
    """Two open rides of an ACTIVE elder; their provider booking ids, oldest first."""
    await add_elder(session, status=ElderStatus.ACTIVE)
    await book_trip(client, rides, await start_call(client), LANG_HA, BACH_MAI)
    await book_trip(client, rides, await start_call(client), BACH_MAI, CHO_HOM, "bike")
    return list(rides.bookings)


async def _sync(session: AsyncSession, rides: FakeRideProvider, **kwargs: int) -> int:
    return await run_ride_sync_job(same_session(session), rides, **kwargs)


async def _stored(session: AsyncSession) -> dict[str, RideBooking]:
    bookings = await session.scalars(select(RideBooking).execution_options(populate_existing=True))
    return {booking.provider_booking_id: booking for booking in bookings}


async def test_open_rides_take_the_provider_status(
    session: AsyncSession, rides: FakeRideProvider, two_rides: list[str]
) -> None:
    first, second = two_rides
    rides.move(first, RideStatus.DRIVER_ASSIGNED, pickup_eta_s=148)
    rides.move(second, RideStatus.CANCELLED, driver=None, cancel_reason="driver")

    assert await _sync(session, rides) == 2

    stored = await _stored(session)
    assert stored[first].status is RideStatus.DRIVER_ASSIGNED
    assert (stored[first].driver_vehicle, stored[first].driver_plate) == (
        "Toyota Vios",
        "30H-575.35",
    )
    assert (stored[second].status, stored[second].cancel_reason) == (
        RideStatus.CANCELLED,
        CancelReason.DRIVER,
    )
    assert all(booking.synced_at is not None for booking in stored.values())


async def test_finished_rides_are_left_alone(
    session: AsyncSession, rides: FakeRideProvider, two_rides: list[str]
) -> None:
    first, second = two_rides
    rides.move(first, RideStatus.COMPLETED)
    await _sync(session, rides)
    rides.read.clear()

    assert await _sync(session, rides) == 1
    assert rides.read == [second]


async def test_each_open_ride_is_read_once_per_run(
    session: AsyncSession, rides: FakeRideProvider, two_rides: list[str]
) -> None:
    assert await _sync(session, rides) == 2
    assert await _sync(session, rides) == 2
    assert sorted(rides.read) == sorted(two_rides * 2)

    # The longest unread first, when a run can't read them all.
    rides.read.clear()
    assert await _sync(session, rides, batch_size=1) == 1
    assert await _sync(session, rides, batch_size=1) == 1
    assert sorted(rides.read) == sorted(two_rides)


async def test_the_run_stops_while_the_provider_is_down(
    session: AsyncSession, rides: FakeRideProvider, two_rides: list[str]
) -> None:
    rides.errors["get_booking"] = RideProviderUnavailableError("timeout")

    assert await _sync(session, rides) == 0

    # One ride asked, none changed; the other wasn't asked.
    assert len(rides.read) == 1
    stored = await _stored(session)
    assert {booking.status for booking in stored.values()} == {RideStatus.REQUESTED}
    assert [b.synced_at is None for b in stored.values()].count(True) == 1

    # The next run asks both again.
    del rides.errors["get_booking"]
    rides.read.clear()
    assert await _sync(session, rides) == 2
    assert sorted(rides.read) == sorted(two_rides)


async def test_a_tool_read_during_the_sync_wins(
    session: AsyncSession, rides: FakeRideProvider, two_rides: list[str]
) -> None:
    """The elder asked about the ride while the job waited for the provider: the job's
    answer, possibly older, isn't written over the tool's."""
    first, second = two_rides
    asked = rides.get_booking

    async def get_booking(booking_id: str) -> ProviderBooking:
        answer = await asked(booking_id)
        if booking_id == first:
            # What get_ride_status would have stored meanwhile.
            await session.execute(
                update(RideBooking)
                .where(RideBooking.provider_booking_id == first)
                .values(status=RideStatus.ARRIVING, synced_at=datetime.now(UTC)),
            )
        return answer

    rides.get_booking = get_booking

    assert await _sync(session, rides) == 2

    stored = await _stored(session)
    assert stored[first].status is RideStatus.ARRIVING
    assert stored[second].status is RideStatus.REQUESTED


async def test_a_ride_the_provider_forgot_is_lost(
    session: AsyncSession, rides: FakeRideProvider, two_rides: list[str]
) -> None:
    rides.forget(two_rides[0])

    await _sync(session, rides)

    stored = (await _stored(session))[two_rides[0]]
    assert (stored.status, stored.cancel_reason) == (RideStatus.CANCELLED, CancelReason.LOST)


async def test_a_refused_read_waits_for_the_next_run(
    session: AsyncSession, rides: FakeRideProvider, two_rides: list[str]
) -> None:
    rides.errors["get_booking"] = RideRequestRefusedError("validation_error")

    assert await _sync(session, rides) == 2

    stored = (await _stored(session)).values()
    assert {booking.status for booking in stored} == {RideStatus.REQUESTED}
    assert all(booking.synced_at is not None for booking in stored)


async def test_the_scheduler_runs_the_ride_sync() -> None:
    scheduler = start_scheduler(
        Settings(scheduler_enabled=True, gemini_api_key="", telegram_bot_token="")
    )
    try:
        assert scheduler is not None
        assert scheduler.get_job("ride_sync") is not None
    finally:
        if scheduler is not None:
            scheduler.shutdown(wait=False)
