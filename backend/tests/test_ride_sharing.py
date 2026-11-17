"""set_ride_sharing, the question after the first booking, and the updates queued for family."""

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Elder, ElderStatus, RideEvent, RideNotification, RideShareScope, RideStatus
from app.services.ride import messages
from tests.conftest import add_elder, start_call
from tests.fakes import FakeRideProvider
from tests.ride_helpers import BACH_MAI, CHO_HOM, LANG_HA, book_trip, ride_tool

pytestmark = pytest.mark.usefixtures("no_confirm_wait")


@pytest.fixture
async def elder(session: AsyncSession) -> Elder:
    return await add_elder(session, status=ElderStatus.ACTIVE)


@pytest.fixture
async def token(client: AsyncClient, elder: Elder) -> str:
    return await start_call(client)


async def share(client: AsyncClient, token: str, scope: str) -> Response:
    return await ride_tool(client, "set-ride-sharing", token, scope=scope)


async def queued(session: AsyncSession) -> list[RideEvent]:
    rows = await session.scalars(
        select(RideNotification.event).order_by(RideNotification.created_at)
    )
    return list(rows)


async def read_status(client: AsyncClient, token: str) -> None:
    assert (await ride_tool(client, "get-ride-status", token)).status_code == 200


# The choice


@pytest.mark.parametrize("scope", list(RideShareScope))
async def test_the_choice_is_stored_with_its_time(
    client: AsyncClient, session: AsyncSession, elder: Elder, token: str, scope: RideShareScope
) -> None:
    response = await share(client, token, scope.value)

    assert response.status_code == 200
    assert response.json() == {"scope": scope.value, "message": messages.SHARING_SET[scope]}
    await session.refresh(elder)
    assert elder.ride_share_scope is scope
    assert elder.ride_share_decided_at is not None


async def test_the_choice_can_be_changed_or_withdrawn_in_any_call(
    client: AsyncClient, session: AsyncSession, elder: Elder, token: str
) -> None:
    await share(client, token, "status")
    await share(client, await start_call(client), "details")
    await share(client, await start_call(client), "none")

    await session.refresh(elder)
    assert elder.ride_share_scope is RideShareScope.NONE


async def test_an_unknown_choice_is_rejected(client: AsyncClient, token: str) -> None:
    assert (await share(client, token, "everything")).status_code == 422


# The question


async def test_the_first_booking_asks_and_later_ones_dont(
    client: AsyncClient, rides: FakeRideProvider, token: str
) -> None:
    first = await book_trip(client, rides, token, LANG_HA, BACH_MAI)
    again = (await ride_tool(client, "book-ride", token, ride_type="car4")).json()

    assert first["ask_sharing"] is True
    assert first["message"].endswith(messages.ASK_SHARING)
    # The same ride again: not a new booking, no question.
    assert again["ask_sharing"] is False

    await share(client, token, "status")
    later = await book_trip(client, rides, token, BACH_MAI, CHO_HOM)

    assert later["ask_sharing"] is False
    assert not later["message"].endswith(messages.ASK_SHARING)


async def test_saying_no_also_ends_the_question(
    client: AsyncClient, rides: FakeRideProvider, token: str
) -> None:
    await share(client, token, "none")

    assert (await book_trip(client, rides, token, LANG_HA, BACH_MAI))["ask_sharing"] is False


# What is queued for the family


async def test_family_updates_for_booking_boarding_and_arriving(
    client: AsyncClient, session: AsyncSession, rides: FakeRideProvider, token: str
) -> None:
    await book_trip(client, rides, token, LANG_HA, BACH_MAI)
    [ride] = rides.bookings

    # The driver's moves aren't news for the family.
    for status in (RideStatus.DRIVER_ASSIGNED, RideStatus.ARRIVING):
        rides.move(ride, status)
        await read_status(client, token)
    rides.move(ride, RideStatus.IN_PROGRESS)
    await read_status(client, token)
    await read_status(client, token)
    rides.move(ride, RideStatus.COMPLETED)
    await read_status(client, token)

    assert await queued(session) == [RideEvent.BOOKED, RideEvent.ON_THE_WAY, RideEvent.ARRIVED]


async def test_cancelling_queues_one_update(
    client: AsyncClient, session: AsyncSession, rides: FakeRideProvider, token: str
) -> None:
    await book_trip(client, rides, token, LANG_HA, BACH_MAI)

    await ride_tool(client, "cancel-ride", token)
    await ride_tool(client, "cancel-ride", token)

    assert await queued(session) == [RideEvent.BOOKED, RideEvent.CANCELLED]


async def test_a_lost_ride_queues_nothing(
    client: AsyncClient, session: AsyncSession, rides: FakeRideProvider, token: str
) -> None:
    await book_trip(client, rides, token, LANG_HA, BACH_MAI)
    [ride] = rides.bookings
    rides.forget(ride)

    await read_status(client, token)

    assert await queued(session) == [RideEvent.BOOKED]


async def test_updates_are_queued_whatever_the_choice(
    client: AsyncClient, session: AsyncSession, rides: FakeRideProvider, token: str
) -> None:
    # The alert job reads the choice when it sends: changing it applies at once.
    await share(client, token, "none")

    await book_trip(client, rides, token, LANG_HA, BACH_MAI)

    assert await queued(session) == [RideEvent.BOOKED]
