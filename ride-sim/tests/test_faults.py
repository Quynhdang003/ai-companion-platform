from datetime import datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.conftest import START, ClientFactory, FakeClock, FakeSleep
from tests.helpers import (
    BACH_MAI,
    LANG_HA,
    error_code,
    get_booking,
    make_booking,
    make_quote,
    quote_body,
)

# The bike trip of `test_bookings.py`: a driver accepts after 20 s, pickup after 354 s.
BIKE_TRIP: dict[str, Any] = {"ride_type": "bike", "pickup": LANG_HA, "destination": BACH_MAI}
DEFAULT_CONFIG = {"time_scale": 1.0, "fault": None}


def _configure(client: TestClient, **body: Any) -> dict:
    response = client.patch("/sim/config", json=body)
    assert response.status_code == 200, response.text
    return response.json()


# The configuration


def test_config_starts_from_the_settings(make_client: ClientFactory) -> None:
    assert make_client().get("/sim/config").json() == DEFAULT_CONFIG
    configured = make_client("other.db", time_scale=30, fault="price_surge")
    assert configured.get("/sim/config").json() == {"time_scale": 30.0, "fault": "price_surge"}


def test_config_changes_only_what_is_sent(client: TestClient) -> None:
    assert _configure(client, fault="no_driver") == {"time_scale": 1.0, "fault": "no_driver"}
    assert _configure(client, time_scale=60) == {"time_scale": 60.0, "fault": "no_driver"}
    assert _configure(client) == {"time_scale": 60.0, "fault": "no_driver"}
    assert _configure(client, fault=None) == {"time_scale": 60.0, "fault": None}
    assert client.get("/sim/config").json() == {"time_scale": 60.0, "fault": None}


@pytest.mark.parametrize("body", [{"time_scale": 0}, {"time_scale": None}, {"fault": "earthquake"}])
def test_invalid_config_is_rejected(client: TestClient, body: dict) -> None:
    response = client.patch("/sim/config", json=body)

    assert response.status_code == 422
    assert error_code(response) == "validation_error"
    assert client.get("/sim/config").json() == DEFAULT_CONFIG


def test_new_time_scale_applies_to_rides_booked_after(client: TestClient, clock: FakeClock) -> None:
    slow = make_booking(client, **BIKE_TRIP)
    _configure(client, time_scale=30)
    fast = make_booking(client, ride_type="car4", pickup=LANG_HA, destination=BACH_MAI)

    clock.advance(1)

    assert get_booking(client, slow["id"])["pickup_eta_s"] == slow["pickup_eta_s"] - 1
    assert get_booking(client, fast["id"])["pickup_eta_s"] == fast["pickup_eta_s"] - 30


# no_driver


def test_no_driver_fault_fails_the_booking(client: TestClient) -> None:
    _configure(client, fault="no_driver")
    quote = make_quote(client)

    response = client.post("/bookings", json={"quote_id": quote["id"]})

    assert response.status_code == 409
    assert error_code(response) == "no_driver_available"
    # Nothing was booked: the same quote can be booked once the fault is off.
    _configure(client, fault=None)
    assert client.post("/bookings", json={"quote_id": quote["id"]}).status_code == 201


# driver_cancels


def test_driver_cancels_after_accepting(client: TestClient, clock: FakeClock) -> None:
    _configure(client, fault="driver_cancels")
    booking = make_booking(client, **BIKE_TRIP)

    clock.advance(64)
    before = get_booking(client, booking["id"])
    clock.advance(1)
    cancelled = get_booking(client, booking["id"])

    # Nothing gives the cancellation away before it happens.
    assert before["status"] == "DRIVER_ASSIGNED"
    assert before["cancelled_at"] is None
    assert before["cancel_reason"] is None
    # 45 s after accepting.
    assert cancelled["status"] == "CANCELLED"
    assert cancelled["cancel_reason"] == "driver"
    assert datetime.fromisoformat(cancelled["cancelled_at"]) == START + timedelta(seconds=65)
    assert cancelled["driver"] == before["driver"]
    assert cancelled["pickup_eta_s"] is None

    # The driver is free again.
    _configure(client, fault=None)
    rebooked = make_booking(client, **BIKE_TRIP)
    clock.advance(20)
    assert get_booking(client, rebooked["id"])["driver"] == before["driver"]


def test_rider_cancelling_first_wins(client: TestClient, clock: FakeClock) -> None:
    _configure(client, fault="driver_cancels")
    booking = make_booking(client, **BIKE_TRIP)
    clock.advance(30)

    cancelled = client.post(f"/bookings/{booking['id']}/cancel").json()
    clock.advance(100)

    assert cancelled["cancel_reason"] == "rider"
    assert datetime.fromisoformat(cancelled["cancelled_at"]) == START + timedelta(seconds=30)
    assert get_booking(client, booking["id"]) == cancelled


def test_rides_booked_before_the_fault_go_on(client: TestClient, clock: FakeClock) -> None:
    booking = make_booking(client, **BIKE_TRIP)
    _configure(client, fault="driver_cancels")

    clock.advance(100)

    assert get_booking(client, booking["id"])["status"] == "DRIVER_ASSIGNED"


# price_surge


def test_price_surge_raises_new_quotes(client: TestClient) -> None:
    usual = make_quote(client)
    _configure(client, fault="price_surge")
    surged = make_quote(client)

    assert (usual["surge"], usual["price_vnd"]) == (False, 77_000)
    # 76,641 x 1.8 = 137,954
    assert (surged["surge"], surged["price_vnd"]) == (True, 138_000)

    # A quote keeps its price, whatever the fault is when it is booked.
    _configure(client, fault=None)
    booking = client.post("/bookings", json={"quote_id": surged["id"]}).json()
    assert booking["price_vnd"] == 138_000


def test_surge_multiplier_comes_from_the_settings(make_client: ClientFactory) -> None:
    client = make_client(fault="price_surge", surge_multiplier=1.5)

    # 76,641 x 1.5 = 114,962
    assert make_quote(client)["price_vnd"] == 115_000


# timeout


def test_timeout_fault_hangs_then_fails(client: TestClient, sleep: FakeSleep) -> None:
    _configure(client, fault="timeout")

    responses = [
        client.post("/quotes", json=quote_body()),
        client.post("/bookings", json={"quote_id": "any"}),
        client.get("/bookings/any"),
        client.post("/bookings/any/cancel"),
        client.get("/places/search", params={"q": "chợ hôm"}),
    ]

    for response in responses:
        assert response.status_code == 504
        assert error_code(response) == "provider_timeout"
    assert sleep.waits == [15.0] * 5

    # The simulation controls never hang.
    assert client.get("/sim/config").status_code == 200
    assert client.get("/health").status_code == 200
    assert len(sleep.waits) == 5

    _configure(client, fault=None)
    assert make_quote(client)["price_vnd"] > 0


def test_timeout_length_comes_from_the_settings(
    make_client: ClientFactory, sleep: FakeSleep
) -> None:
    client = make_client(fault="timeout", fault_timeout_seconds=12)

    assert client.post("/quotes", json=quote_body()).status_code == 504
    assert sleep.waits == [12.0]
