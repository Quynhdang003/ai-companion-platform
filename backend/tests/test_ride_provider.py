import json
from collections.abc import Callable
from datetime import UTC, datetime

import httpx
import pytest

from app.models import RideStatus, RideType
from app.services.ride.provider import (
    GeoPoint,
    ProviderDriver,
    ProviderPlace,
    RideProviderUnavailableError,
    RideRequestRefusedError,
)
from app.services.ride.simulator import SimRideProvider

Handler = Callable[[httpx.Request], httpx.Response]

LANG_HA = GeoPoint(21.0205, 105.817)
BACH_MAI = GeoPoint(21.00182, 105.83967)

QUOTE = {
    "id": "q1",
    "ride_type": "car4",
    "pickup": {"lat": 21.0205, "lng": 105.817},
    "destination": {"lat": 21.00182, "lng": 105.83967},
    "distance_m": 4132,
    "duration_s": 799,
    "price_vnd": 72000,
    "peak": False,
    "surge": False,
    "estimated": False,
    "pickup_eta_s": 283,
    "expires_at": "2026-11-16T14:58:01.245975Z",
}
BOOKING = {
    "id": "b1",
    "quote_id": "q1",
    "status": "DRIVER_ASSIGNED",
    "ride_type": "car4",
    "pickup": QUOTE["pickup"],
    "destination": QUOTE["destination"],
    "distance_m": 4132,
    "duration_s": 799,
    "price_vnd": 72000,
    "driver": {"name": "Trần Đức Việt", "vehicle": "Toyota Vios", "plate": "30H-575.35"},
    "pickup_eta_s": 148,
    "dropoff_eta_s": 947,
    "requested_at": "2026-11-16T14:53:01Z",
    "cancelled_at": None,
    "cancel_reason": None,
}


def _provider(handler: Handler) -> SimRideProvider:
    return SimRideProvider("http://sim.test/", 1, transport=httpx.MockTransport(handler))


def _recording(status: int, body: object, seen: list[httpx.Request]) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json=body)

    return handler


async def test_search_places() -> None:
    seen: list[httpx.Request] = []
    body = [
        {"name": "Bệnh viện Bạch Mai", "address": "78 Đường Giải Phóng", "lat": 21.00182,
         "lng": 105.83967, "source": "builtin"},
    ]  # fmt: skip

    places = await _provider(_recording(200, body, seen)).search_places("Bạch Mai", 3)

    assert places == [ProviderPlace("Bệnh viện Bạch Mai", "78 Đường Giải Phóng", BACH_MAI)]
    [request] = seen
    assert (request.method, request.url.path) == ("GET", "/places/search")
    assert dict(request.url.params) == {"q": "Bạch Mai", "limit": "3"}


async def test_quote() -> None:
    seen: list[httpx.Request] = []

    quote = await _provider(_recording(201, QUOTE, seen)).quote(RideType.CAR4, LANG_HA, BACH_MAI)

    assert (quote.id, quote.ride_type, quote.price_vnd) == ("q1", RideType.CAR4, 72_000)
    assert (quote.distance_m, quote.duration_s, quote.pickup_eta_s) == (4132, 799, 283)
    assert quote.surge is False
    assert quote.expires_at == datetime(2026, 11, 16, 14, 58, 1, 245975, tzinfo=UTC)
    [request] = seen
    assert (request.method, request.url.path) == ("POST", "/quotes")
    assert json.loads(request.content) == {
        "ride_type": "car4",
        "pickup": {"lat": 21.0205, "lng": 105.817},
        "destination": {"lat": 21.00182, "lng": 105.83967},
    }


async def test_quote_without_a_driver_nearby() -> None:
    quote = await _provider(_recording(201, QUOTE | {"pickup_eta_s": None}, [])).quote(
        RideType.CAR4, LANG_HA, BACH_MAI
    )

    assert quote.pickup_eta_s is None


@pytest.mark.parametrize("status", [201, 200], ids=["new", "booked-before"])
async def test_book(status: int) -> None:
    seen: list[httpx.Request] = []

    booking = await _provider(_recording(status, BOOKING, seen)).book("q1")

    assert (booking.id, booking.quote_id, booking.status) == (
        "b1",
        "q1",
        RideStatus.DRIVER_ASSIGNED,
    )
    assert booking.driver == ProviderDriver("Trần Đức Việt", "Toyota Vios", "30H-575.35")
    assert (booking.pickup_eta_s, booking.dropoff_eta_s) == (148, 947)
    [request] = seen
    assert (request.method, request.url.path) == ("POST", "/bookings")
    assert json.loads(request.content) == {"quote_id": "q1"}


async def test_booking_without_a_driver_yet() -> None:
    body = BOOKING | {"status": "REQUESTED", "driver": None}

    booking = await _provider(_recording(201, body, [])).book("q1")

    assert (booking.status, booking.driver) == (RideStatus.REQUESTED, None)


@pytest.mark.parametrize(
    ("status", "body", "code"),
    [
        (409, {"error": {"code": "no_driver_available", "message": "..."}}, "no_driver_available"),
        (409, {"error": {"code": "quote_expired", "message": "..."}}, "quote_expired"),
        (404, {"error": {"code": "quote_not_found", "message": "..."}}, "quote_not_found"),
        (422, {"error": {"code": "out_of_service_area", "message": "..."}}, "out_of_service_area"),
        (422, {"detail": "unexpected"}, "http_422"),
    ],
)
async def test_refusals_carry_the_simulator_code(status: int, body: object, code: str) -> None:
    with pytest.raises(RideRequestRefusedError) as raised:
        await _provider(_recording(status, body, [])).book("q1")

    assert raised.value.code == code


def _raise(error: Exception) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        raise error

    return handler


@pytest.mark.parametrize(
    "handler",
    [
        lambda _: httpx.Response(504, json={"error": {"code": "provider_timeout"}}),
        lambda _: httpx.Response(500, text="Internal Server Error"),
        lambda _: httpx.Response(200, text="<html>"),
        lambda _: httpx.Response(200, json={"unexpected": True}),
        _raise(httpx.ConnectError("refused")),
        _raise(httpx.ReadTimeout("slow")),
    ],
    ids=["timeout-fault", "server-error", "not-json", "wrong-shape", "unreachable", "timeout"],
)
async def test_no_usable_answer_is_unavailable(handler: Handler) -> None:
    provider = _provider(handler)

    for call in (
        provider.search_places("12 Láng Hạ", 3),
        provider.quote(RideType.BIKE, LANG_HA, BACH_MAI),
        provider.book("q1"),
    ):
        with pytest.raises(RideProviderUnavailableError) as raised:
            await call
        # Errors never carry what was searched or where.
        assert "Láng" not in str(raised.value)
        assert "21.0205" not in str(raised.value)
