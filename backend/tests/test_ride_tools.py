from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    CallSession,
    ElderStatus,
    PlaceSource,
    RideBooking,
    RidePlaceOption,
    RideQuote,
    RideStatus,
    RideType,
)
from app.services.ride import messages
from app.services.ride.provider import (
    GeoPoint,
    RideProviderUnavailableError,
    RideRequestRefusedError,
)
from tests.conftest import add_elder, start_call
from tests.fakes import FakeRideProvider
from tests.ride_helpers import BACH_MAI, CHO_HOM, LANG_HA, find, ride_tool, search

TOOLS = [
    ("search-location", {"query": "Bạch Mai"}),
    ("get-ride-quote", {"pickup_ref": 1, "destination_ref": 2, "ride_type": "car4"}),
    ("book-ride", {"ride_type": "car4"}),
    ("get-ride-status", {}),
    ("cancel-ride", {}),
]


async def _count(session: AsyncSession, model: type) -> int:
    return await session.scalar(select(func.count()).select_from(model))


async def _quote(client: AsyncClient, token: str, pickup: int, destination: int, ride_type="car4"):
    return await ride_tool(
        client,
        "get-ride-quote",
        token,
        pickup_ref=pickup,
        destination_ref=destination,
        ride_type=ride_type,
    )


async def _quoted_trip(client: AsyncClient, rides: FakeRideProvider, token: str) -> None:
    """Lang Ha -> Bach Mai by car4, quoted."""
    pickup, destination = (
        await find(client, rides, token, LANG_HA),
        await find(client, rides, token, BACH_MAI),
    )
    assert (await _quote(client, token, pickup, destination)).json()["status"] == "quoted"


# Who may book


@pytest.mark.parametrize(
    ("status", "number"),
    [
        (ElderStatus.PENDING_VERIFICATION, "0912345678"),
        (ElderStatus.BLOCKED, "0912345678"),
        (None, "0912000009"),
    ],
    ids=["pending consent", "blocked", "unknown"],
)
async def test_rides_are_for_active_elders_only(
    client: AsyncClient,
    session: AsyncSession,
    rides: FakeRideProvider,
    status: ElderStatus | None,
    number: str,
) -> None:
    if status is not None:
        await add_elder(session, status=status)
    token = await start_call(client, number)
    rides.places = [BACH_MAI]

    for name, body in TOOLS:
        response = await ride_tool(client, name, token, **body)
        assert response.status_code == 403, name
        assert response.json()["error"] == {"code": "not_active", "message": messages.NOT_ACTIVE}

    assert (rides.searches, rides.quotes, rides.booked) == ([], [], [])
    assert await _count(session, RidePlaceOption) == 0


async def test_ride_tools_need_a_live_session(client: AsyncClient, session: AsyncSession) -> None:
    await add_elder(session, status=ElderStatus.ACTIVE)
    token = await start_call(client)
    await session.execute(update(CallSession).values(expires_at=datetime.now(UTC)))

    for name, body in TOOLS:
        for used in (token, "not-a-token"):
            response = await ride_tool(client, name, used, **body)
            assert response.status_code == 401, name
            assert response.json()["error"]["code"] == "invalid_session"


async def test_ride_tools_need_the_dograh_key(client: AsyncClient) -> None:
    for name, body in TOOLS:
        response = await client.post(
            f"/tools/{name}",
            json={"session_token": "x", **body},
            headers={"Authorization": "Bearer wrong"},
        )
        assert response.status_code == 401


# search_location


@pytest.fixture
async def token(client: AsyncClient, session: AsyncSession) -> str:
    """A call from an ACTIVE elder."""
    await add_elder(session, status=ElderStatus.ACTIVE)
    return await start_call(client)


async def test_places_are_numbered_within_the_call(
    client: AsyncClient, session: AsyncSession, rides: FakeRideProvider, token: str
) -> None:
    rides.places = [BACH_MAI, CHO_HOM]

    first = await search(client, token, "bệnh viện")
    rides.places = [LANG_HA]
    second = await search(client, token, "12 Láng Hạ")

    assert first == {
        "status": "found",
        "message": "Dạ, con tìm được mấy chỗ: Bệnh viện Bạch Mai, 78 Đường Giải Phóng;"
        " Chợ Hôm, 79 Phố Huế. Bác muốn chỗ nào ạ?",
        "options": [
            {"ref": 1, "name": "Bệnh viện Bạch Mai", "address": "78 Đường Giải Phóng"},
            {"ref": 2, "name": "Chợ Hôm", "address": "79 Phố Huế"},
        ],
    }
    # Later searches go on counting: earlier numbers stay valid.
    assert second["options"] == [{"ref": 3, "name": "Ngõ 12 Phố Láng Hạ", "address": ""}]
    assert second["message"] == "Dạ, con tìm được Ngõ 12 Phố Láng Hạ. Có phải chỗ này không ạ?"
    assert rides.searches == [("bệnh viện", 3), ("12 Láng Hạ", 3)]

    stored = (await session.scalars(select(RidePlaceOption).order_by(RidePlaceOption.ref))).all()
    assert [(o.ref, o.name, o.source) for o in stored] == [
        (1, "Bệnh viện Bạch Mai", PlaceSource.PROVIDER),
        (2, "Chợ Hôm", PlaceSource.PROVIDER),
        (3, "Ngõ 12 Phố Láng Hạ", PlaceSource.PROVIDER),
    ]
    assert (stored[0].lat, stored[0].lng) == (21.00182, 105.83967)


async def test_at_most_three_places_are_offered(
    client: AsyncClient, rides: FakeRideProvider, token: str
) -> None:
    rides.places = [BACH_MAI, CHO_HOM, LANG_HA, BACH_MAI]
    rides.search_places = _ignoring_limit(rides)

    assert [o["ref"] for o in (await search(client, token, "chợ"))["options"]] == [1, 2, 3]


def _ignoring_limit(rides: FakeRideProvider):
    async def search_places(query: str, limit: int):
        rides.searches.append((query, limit))
        return rides.places

    return search_places


async def test_nothing_found(
    client: AsyncClient, session: AsyncSession, rides: FakeRideProvider, token: str
) -> None:
    assert await search(client, token, "phố không có thật") == {
        "status": "not_found",
        "message": messages.PLACE_NOT_FOUND,
        "options": [],
    }
    assert await _count(session, RidePlaceOption) == 0


@pytest.mark.parametrize(
    "error", [RideProviderUnavailableError("timeout"), RideRequestRefusedError("validation_error")]
)
async def test_search_while_the_provider_fails(
    client: AsyncClient, rides: FakeRideProvider, token: str, error: Exception
) -> None:
    rides.places = [BACH_MAI]
    rides.errors["search_places"] = error

    assert await search(client, token, "Bạch Mai") == {
        "status": "unavailable",
        "message": messages.PLACES_UNAVAILABLE,
        "options": [],
    }


@pytest.mark.parametrize("query", ["", "   ", "x" * 201])
async def test_invalid_search_is_rejected(client: AsyncClient, token: str, query: str) -> None:
    response = await ride_tool(client, "search-location", token, query=query)

    assert response.status_code == 422


# get_ride_quote


async def test_quote_a_trip_between_two_places(
    client: AsyncClient, session: AsyncSession, rides: FakeRideProvider, token: str
) -> None:
    pickup = await find(client, rides, token, LANG_HA)
    destination = await find(client, rides, token, BACH_MAI)

    response = await _quote(client, token, pickup, destination)

    assert response.status_code == 200
    assert response.json() == {
        "status": "quoted",
        "message": "Dạ, xe bốn chỗ từ Ngõ 12 Phố Láng Hạ đến Bệnh viện Bạch Mai hết khoảng"
        " 72 nghìn đồng, đi mất khoảng 14 phút. Xe đến đón sau khoảng 5 phút."
        " Bác có đồng ý đặt xe không ạ?",
        "ride_type": "car4",
        "price_vnd": 72_000,
        "pickup_minutes": 5,
        "trip_minutes": 14,
        "surge": False,
    }
    # The provider gets the options' coordinates; the LLM never sees them.
    assert rides.quotes == [(RideType.CAR4, GeoPoint(21.0205, 105.817), BACH_MAI.location)]
    quote = await session.scalar(select(RideQuote))
    assert (quote.pickup.name, quote.destination.name) == (LANG_HA.name, BACH_MAI.name)
    assert (quote.price_vnd, quote.pickup_eta_s, quote.duration_s) == (72_000, 283, 799)


async def test_a_surge_price_is_said(
    client: AsyncClient, rides: FakeRideProvider, token: str
) -> None:
    rides.surge, rides.price_vnd = True, 130_000
    pickup, destination = (
        await find(client, rides, token, LANG_HA),
        await find(client, rides, token, BACH_MAI),
    )

    body = (await _quote(client, token, pickup, destination, "bike")).json()

    assert body["surge"] is True
    assert "hết khoảng 130 nghìn đồng" in body["message"]
    assert body["message"].endswith(
        "Giá lúc này đang cao hơn bình thường. Bác có đồng ý đặt xe không ạ?"
    )


async def test_no_driver_near_the_pickup(
    client: AsyncClient, session: AsyncSession, rides: FakeRideProvider, token: str
) -> None:
    rides.pickup_eta_s = None
    pickup, destination = (
        await find(client, rides, token, LANG_HA),
        await find(client, rides, token, BACH_MAI),
    )

    body = (await _quote(client, token, pickup, destination, "car7")).json()

    assert body == {
        "status": "no_driver",
        "message": "Dạ, lúc này không có xe bảy chỗ nào ở gần điểm đón."
        " Bác muốn thử loại xe khác hay đợi một lát ạ?",
        "ride_type": "car7",
        "price_vnd": None,
        "pickup_minutes": None,
        "trip_minutes": None,
        "surge": None,
    }
    assert await _count(session, RideQuote) == 0


@pytest.mark.parametrize(
    ("error", "status", "message"),
    [
        (RideRequestRefusedError("out_of_service_area"), "out_of_area", messages.OUT_OF_AREA),
        (RideRequestRefusedError("trip_too_short"), "too_short", messages.TOO_SHORT),
        (RideRequestRefusedError("validation_error"), "unavailable", messages.QUOTE_UNAVAILABLE),
        (RideProviderUnavailableError("timeout"), "unavailable", messages.QUOTE_UNAVAILABLE),
    ],
)
async def test_quote_refused_or_failed(
    client: AsyncClient,
    session: AsyncSession,
    rides: FakeRideProvider,
    token: str,
    error: Exception,
    status: str,
    message: str,
) -> None:
    pickup, destination = (
        await find(client, rides, token, LANG_HA),
        await find(client, rides, token, BACH_MAI),
    )
    rides.errors["quote"] = error

    body = (await _quote(client, token, pickup, destination)).json()

    assert (body["status"], body["message"], body["price_vnd"]) == (status, message, None)
    assert await _count(session, RideQuote) == 0


async def test_places_of_another_call_cannot_be_quoted(
    client: AsyncClient, rides: FakeRideProvider, token: str
) -> None:
    other_call = await start_call(client)
    await find(client, rides, other_call, LANG_HA)
    await find(client, rides, other_call, BACH_MAI)
    # This call has option 1 only; 2 belongs to the other call.
    assert await find(client, rides, token, CHO_HOM) == 1

    for pickup, destination in [(1, 2), (2, 1), (1, 9)]:
        response = await _quote(client, token, pickup, destination)
        assert response.status_code == 404
        assert response.json()["error"] == {
            "code": "unknown_place",
            "message": messages.UNKNOWN_PLACE,
        }
    assert rides.quotes == []


@pytest.mark.parametrize(
    "body",
    [
        {"pickup_ref": 1, "destination_ref": 2, "ride_type": "truck"},
        {"pickup_ref": 0, "destination_ref": 2, "ride_type": "car4"},
        {"pickup_ref": 1, "ride_type": "car4"},
    ],
)
async def test_invalid_quote_request_is_rejected(
    client: AsyncClient, token: str, body: dict
) -> None:
    assert (await ride_tool(client, "get-ride-quote", token, **body)).status_code == 422


# book_ride


async def test_booking_needs_the_price_read_out_first(
    client: AsyncClient, session: AsyncSession, rides: FakeRideProvider, token: str
) -> None:
    await _quoted_trip(client, rides, token)

    # Booked in the same breath as the quote: refused.
    refused = await ride_tool(client, "book-ride", token, ride_type="car4")

    assert refused.status_code == 409
    assert refused.json()["error"] == {
        "code": "confirmation_required",
        "message": messages.CONFIRMATION_REQUIRED,
    }
    assert rides.booked == []

    # Once the price has had time to be read out and agreed to: booked.
    await session.execute(
        update(RideQuote).values(created_at=RideQuote.created_at - timedelta(seconds=4)),
        execution_options={"synchronize_session": "fetch"},
    )
    booked = await ride_tool(client, "book-ride", token, ride_type="car4")

    assert booked.status_code == 200
    assert booked.json() == {
        "status": "booked",
        "message": "Dạ, con đã đặt xe bốn chỗ cho bác rồi ạ."
        " Xe sẽ đến đón ở Ngõ 12 Phố Láng Hạ sau khoảng 5 phút.",
        "ride_type": "car4",
        "pickup_minutes": 5,
    }
    ride = await session.scalar(select(RideBooking))
    call = await session.scalar(select(CallSession))
    quote = await session.scalar(select(RideQuote))
    assert (ride.elder_id, ride.call_session_id, ride.quote_id) == (
        call.elder_id,
        call.id,
        quote.id,
    )
    assert rides.booked == [quote.provider_quote_id]
    assert ride.provider_booking_id.startswith("booking-")
    assert (ride.status, ride.driver_plate) == (RideStatus.REQUESTED, None)


@pytest.mark.usefixtures("no_confirm_wait")
async def test_booking_again_returns_the_same_ride(
    client: AsyncClient, session: AsyncSession, rides: FakeRideProvider, token: str
) -> None:
    await _quoted_trip(client, rides, token)

    first = await ride_tool(client, "book-ride", token, ride_type="car4")
    again = await ride_tool(client, "book-ride", token, ride_type="car4")

    assert first.json()["status"] == again.json()["status"] == "booked"
    assert again.json()["message"] == "Dạ, con đã đặt xe bốn chỗ cho bác rồi ạ."
    assert len(rides.booked) == 1
    assert await _count(session, RideBooking) == 1


@pytest.mark.usefixtures("no_confirm_wait")
async def test_the_latest_quote_of_the_agreed_ride_type_is_booked(
    client: AsyncClient, session: AsyncSession, rides: FakeRideProvider, token: str
) -> None:
    pickup = await find(client, rides, token, LANG_HA)
    hospital = await find(client, rides, token, BACH_MAI)
    market = await find(client, rides, token, CHO_HOM)
    await _quote(client, token, pickup, hospital, "bike")
    await _quote(client, token, pickup, hospital, "car4")
    await _quote(client, token, pickup, market, "bike")

    # Car4 and bike were both read out; the caller chose the bike to the market.
    booked = await ride_tool(client, "book-ride", token, ride_type="bike")
    missing = await ride_tool(client, "book-ride", token, ride_type="car7")

    assert booked.json()["status"] == "booked"
    ride = await session.scalar(select(RideBooking))
    assert (ride.quote.ride_type, ride.quote.destination.name) == (RideType.BIKE, CHO_HOM.name)
    assert missing.json() == {
        "status": "no_quote",
        "message": messages.NO_QUOTE,
        "ride_type": "car7",
        "pickup_minutes": None,
    }


async def test_nothing_quoted_nothing_booked(
    client: AsyncClient, rides: FakeRideProvider, token: str
) -> None:
    body = (await ride_tool(client, "book-ride", token, ride_type="car4")).json()

    assert (body["status"], body["message"]) == ("no_quote", messages.NO_QUOTE)
    assert rides.booked == []


@pytest.mark.usefixtures("no_confirm_wait")
async def test_an_expired_quote_is_not_booked(
    client: AsyncClient, session: AsyncSession, rides: FakeRideProvider, token: str
) -> None:
    await _quoted_trip(client, rides, token)
    await session.execute(
        update(RideQuote).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)),
        execution_options={"synchronize_session": "fetch"},
    )

    body = (await ride_tool(client, "book-ride", token, ride_type="car4")).json()

    assert (body["status"], body["message"]) == ("quote_expired", messages.QUOTE_EXPIRED)
    assert rides.booked == []


@pytest.mark.usefixtures("no_confirm_wait")
@pytest.mark.parametrize(
    ("error", "status", "message"),
    [
        (RideRequestRefusedError("quote_expired"), "quote_expired", messages.QUOTE_EXPIRED),
        (RideRequestRefusedError("quote_not_found"), "quote_expired", messages.QUOTE_EXPIRED),
        (
            RideRequestRefusedError("no_driver_available"),
            "no_driver",
            messages.no_driver(RideType.CAR4),
        ),
        (RideProviderUnavailableError("timeout"), "unavailable", messages.BOOK_UNAVAILABLE),
    ],
)
async def test_booking_refused_or_failed(
    client: AsyncClient,
    session: AsyncSession,
    rides: FakeRideProvider,
    token: str,
    error: Exception,
    status: str,
    message: str,
) -> None:
    await _quoted_trip(client, rides, token)
    rides.errors["book"] = error

    body = (await ride_tool(client, "book-ride", token, ride_type="car4")).json()

    assert (body["status"], body["message"], body["pickup_minutes"]) == (status, message, None)
    assert await _count(session, RideBooking) == 0


@pytest.mark.usefixtures("no_confirm_wait")
async def test_booking_again_after_no_answer_is_safe(
    client: AsyncClient, session: AsyncSession, rides: FakeRideProvider, token: str
) -> None:
    await _quoted_trip(client, rides, token)
    rides.errors["book"] = RideProviderUnavailableError("timeout")
    assert (await ride_tool(client, "book-ride", token, ride_type="car4")).json()[
        "status"
    ] == "unavailable"

    del rides.errors["book"]
    body = (await ride_tool(client, "book-ride", token, ride_type="car4")).json()

    assert body["status"] == "booked"
    # The same quote both times: a provider that did book the first time answers with it.
    assert len(rides.booked) == 2
    assert len(set(rides.booked)) == 1
    assert await _count(session, RideBooking) == 1
