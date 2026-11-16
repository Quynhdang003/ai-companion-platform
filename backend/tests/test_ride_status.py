"""get_ride_status and cancel_ride: the elder's current ride."""

from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CancelReason, ElderStatus, RideBooking, RideStatus
from app.services.ride import messages
from app.services.ride.provider import RideProviderUnavailableError
from tests.conftest import add_elder, start_call
from tests.fakes import FakeRideProvider
from tests.ride_helpers import BACH_MAI, LANG_HA, book_trip, ride_tool

pytestmark = pytest.mark.usefixtures("no_confirm_wait")

PLATE = "Toyota Vios biển số 30H-575.35"


@pytest.fixture
async def token(client: AsyncClient, session: AsyncSession) -> str:
    """A call from an ACTIVE elder."""
    await add_elder(session, status=ElderStatus.ACTIVE)
    return await start_call(client)


async def _booked(client: AsyncClient, rides: FakeRideProvider, token: str) -> str:
    """Book Lang Ha -> Bach Mai by car4; the provider's booking id."""
    await book_trip(client, rides, token, LANG_HA, BACH_MAI)
    [booking_id] = rides.bookings
    return booking_id


async def _status(client: AsyncClient, token: str) -> dict:
    response = await ride_tool(client, "get-ride-status", token)
    assert response.status_code == 200, response.text
    return response.json()


async def _cancel(client: AsyncClient, token: str) -> dict:
    response = await ride_tool(client, "cancel-ride", token)
    assert response.status_code == 200, response.text
    return response.json()


async def _stored(session: AsyncSession) -> RideBooking:
    return await session.scalar(select(RideBooking).execution_options(populate_existing=True))


# get_ride_status


async def test_status_right_after_booking(
    client: AsyncClient, rides: FakeRideProvider, token: str
) -> None:
    booking_id = await _booked(client, rides, token)

    assert await _status(client, token) == {
        "status": "found",
        "message": "Dạ, hệ thống đang tìm tài xế cho bác ạ. Xe dự kiến đến đón sau khoảng 5 phút.",
        "ride_status": "REQUESTED",
        "pickup_minutes": 5,
        "dropoff_minutes": 19,
    }
    assert rides.read == [booking_id]


@pytest.mark.parametrize(
    ("status", "etas", "reason", "message"),
    [
        (
            RideStatus.DRIVER_ASSIGNED,
            (148, 947),
            None,
            f"Dạ, tài xế Trần Đức Việt đã nhận chuyến, đi {PLATE}."
            " Xe sẽ đến đón ở Ngõ 12 Phố Láng Hạ sau khoảng 3 phút.",
        ),
        (
            RideStatus.ARRIVING,
            (60, 859),
            None,
            f"Dạ, xe sắp đến rồi ạ, {PLATE}. Còn khoảng 1 phút nữa."
            " Bác chuẩn bị ra Ngõ 12 Phố Láng Hạ nhé.",
        ),
        (
            RideStatus.IN_PROGRESS,
            (None, 400),
            None,
            "Dạ, bác đang trên đường đến Bệnh viện Bạch Mai, còn khoảng 7 phút nữa ạ.",
        ),
        (
            RideStatus.COMPLETED,
            (None, None),
            None,
            "Dạ, chuyến xe đến Bệnh viện Bạch Mai đã hoàn thành rồi ạ.",
        ),
        (
            RideStatus.CANCELLED,
            (None, None),
            "driver",
            "Dạ, tài xế đã hủy chuyến xe đi Bệnh viện Bạch Mai."
            " Bác có muốn con đặt xe khác không ạ?",
        ),
    ],
    ids=["driver-assigned", "arriving", "in-progress", "completed", "driver-cancelled"],
)
async def test_status_follows_the_ride(
    client: AsyncClient,
    session: AsyncSession,
    rides: FakeRideProvider,
    token: str,
    status: RideStatus,
    etas: tuple[int | None, int | None],
    reason: str | None,
    message: str,
) -> None:
    booking_id = await _booked(client, rides, token)
    rides.move(
        booking_id, status, pickup_eta_s=etas[0], dropoff_eta_s=etas[1], cancel_reason=reason
    )

    body = await _status(client, token)

    assert (body["status"], body["ride_status"], body["message"]) == ("found", status, message)
    stored = await _stored(session)
    assert stored.status is status
    assert (stored.driver_name, stored.driver_plate) == ("Trần Đức Việt", "30H-575.35")
    assert stored.synced_at is not None
    assert stored.cancel_reason == (CancelReason(reason) if reason else None)


async def test_a_finished_ride_is_not_asked_again(
    client: AsyncClient, rides: FakeRideProvider, token: str
) -> None:
    booking_id = await _booked(client, rides, token)
    rides.move(booking_id, RideStatus.COMPLETED)
    await _status(client, token)

    again = await _status(client, token)

    assert again["ride_status"] == "COMPLETED"
    assert rides.read == [booking_id]


async def test_status_while_the_provider_is_down(
    client: AsyncClient, session: AsyncSession, rides: FakeRideProvider, token: str
) -> None:
    await _booked(client, rides, token)
    rides.errors["get_booking"] = RideProviderUnavailableError("timeout")

    assert await _status(client, token) == {
        "status": "unavailable",
        "message": messages.STATUS_UNAVAILABLE,
        "ride_status": "REQUESTED",
        "pickup_minutes": None,
        "dropoff_minutes": None,
    }
    assert (await _stored(session)).synced_at is None


async def test_a_ride_the_provider_forgot(
    client: AsyncClient, session: AsyncSession, rides: FakeRideProvider, token: str
) -> None:
    rides.forget(await _booked(client, rides, token))

    body = await _status(client, token)

    assert (body["status"], body["ride_status"]) == ("found", "CANCELLED")
    assert body["message"] == (
        "Dạ, con không còn thấy chuyến xe đi Bệnh viện Bạch Mai trong hệ thống nữa."
        " Bác có muốn con đặt lại không ạ?"
    )
    stored = await _stored(session)
    assert (stored.status, stored.cancel_reason) == (RideStatus.CANCELLED, CancelReason.LOST)


async def test_no_ride(client: AsyncClient, rides: FakeRideProvider, token: str) -> None:
    assert await _status(client, token) == {
        "status": "no_ride",
        "message": messages.NO_RIDE,
        "ride_status": None,
        "pickup_minutes": None,
        "dropoff_minutes": None,
    }


async def test_a_ride_finished_long_ago_is_no_longer_current(
    client: AsyncClient, session: AsyncSession, rides: FakeRideProvider, token: str
) -> None:
    booking_id = await _booked(client, rides, token)
    await session.execute(
        update(RideBooking).values(created_at=RideBooking.created_at - timedelta(hours=7)),
        execution_options={"synchronize_session": "fetch"},
    )
    # Still open after 7 hours: still current.
    assert (await _status(client, token))["status"] == "found"

    rides.move(booking_id, RideStatus.COMPLETED)
    await _status(client, token)

    assert (await _status(client, token))["status"] == "no_ride"


async def test_the_ride_of_an_earlier_call_is_current(
    client: AsyncClient, rides: FakeRideProvider, token: str
) -> None:
    await _booked(client, rides, token)

    body = await _status(client, await start_call(client))

    assert (body["status"], body["ride_status"]) == ("found", "REQUESTED")


async def test_the_latest_ride_is_current(
    client: AsyncClient, rides: FakeRideProvider, token: str
) -> None:
    first = await _booked(client, rides, token)
    rides.move(first, RideStatus.COMPLETED)
    await book_trip(client, rides, token, BACH_MAI, LANG_HA)

    body = await _status(client, token)

    assert body["ride_status"] == "REQUESTED"
    assert "Ngõ 12 Phố Láng Hạ" not in body["message"]


# cancel_ride


async def test_cancel_the_current_ride(
    client: AsyncClient, session: AsyncSession, rides: FakeRideProvider, token: str
) -> None:
    booking_id = await _booked(client, rides, token)

    assert await _cancel(client, token) == {
        "status": "cancelled",
        "message": "Dạ, con đã hủy chuyến xe đi Bệnh viện Bạch Mai rồi ạ.",
    }
    assert rides.cancelled == [booking_id]
    stored = await _stored(session)
    assert (stored.status, stored.cancel_reason) == (RideStatus.CANCELLED, CancelReason.RIDER)
    assert (await _status(client, token))["message"] == (
        "Dạ, chuyến xe đi Bệnh viện Bạch Mai đã được hủy rồi ạ."
    )


async def test_cancelling_twice(client: AsyncClient, rides: FakeRideProvider, token: str) -> None:
    await _booked(client, rides, token)
    await _cancel(client, token)

    assert await _cancel(client, token) == {
        "status": "already_cancelled",
        "message": "Dạ, chuyến xe đi Bệnh viện Bạch Mai đã được hủy từ trước rồi ạ.",
    }
    assert len(rides.cancelled) == 1


@pytest.mark.parametrize(
    ("status", "reason", "outcome", "message"),
    [
        (
            RideStatus.IN_PROGRESS,
            None,
            "in_progress",
            messages.CANCEL_IN_PROGRESS,
        ),
        (
            RideStatus.COMPLETED,
            None,
            "completed",
            "Dạ, chuyến xe đi Bệnh viện Bạch Mai đã hoàn thành nên không hủy được nữa ạ.",
        ),
        (
            RideStatus.CANCELLED,
            "driver",
            "already_cancelled",
            "Dạ, tài xế đã hủy chuyến xe đi Bệnh viện Bạch Mai."
            " Bác có muốn con đặt xe khác không ạ?",
        ),
    ],
    ids=["on-board", "arrived", "driver-cancelled"],
)
async def test_cancel_when_the_provider_knows_better(
    client: AsyncClient,
    rides: FakeRideProvider,
    token: str,
    status: RideStatus,
    reason: str | None,
    outcome: str,
    message: str,
) -> None:
    # Stored as REQUESTED; the provider has moved on.
    booking_id = await _booked(client, rides, token)
    rides.move(booking_id, status, cancel_reason=reason)

    assert await _cancel(client, token) == {"status": outcome, "message": message}


async def test_a_stored_finished_ride_is_not_sent_to_the_provider(
    client: AsyncClient, rides: FakeRideProvider, token: str
) -> None:
    booking_id = await _booked(client, rides, token)
    rides.move(booking_id, RideStatus.COMPLETED)
    await _status(client, token)

    body = await _cancel(client, token)

    assert body["status"] == "completed"
    assert rides.cancelled == []


async def test_cancel_with_no_ride(
    client: AsyncClient, rides: FakeRideProvider, token: str
) -> None:
    assert await _cancel(client, token) == {
        "status": "no_ride",
        "message": messages.NO_RIDE_TO_CANCEL,
    }


async def test_cancel_while_the_provider_is_down(
    client: AsyncClient, session: AsyncSession, rides: FakeRideProvider, token: str
) -> None:
    await _booked(client, rides, token)
    rides.errors["cancel"] = RideProviderUnavailableError("timeout")

    assert await _cancel(client, token) == {
        "status": "unavailable",
        "message": messages.CANCEL_UNAVAILABLE,
    }
    assert (await _stored(session)).status is RideStatus.REQUESTED


async def test_cancel_a_ride_the_provider_forgot(
    client: AsyncClient, session: AsyncSession, rides: FakeRideProvider, token: str
) -> None:
    rides.forget(await _booked(client, rides, token))

    body = await _cancel(client, token)

    assert body["status"] == "already_cancelled"
    assert "không còn thấy chuyến xe" in body["message"]
    assert (await _stored(session)).cancel_reason is CancelReason.LOST
