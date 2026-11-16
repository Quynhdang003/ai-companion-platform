from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from tests.conftest import START, ClientFactory, FakeClock
from tests.helpers import (
    BACH_MAI,
    HO_CHI_MINH_CITY,
    LANG_HA,
    NOI_BAI,
    error_code,
    make_quote,
    quote_body,
)


def test_quote_prices_the_trip(client: TestClient) -> None:
    quote = make_quote(client, ride_type="car4", pickup=LANG_HA, destination=BACH_MAI)

    assert quote["id"]
    assert quote["ride_type"] == "car4"
    assert quote["pickup"] == {"lat": LANG_HA.lat, "lng": LANG_HA.lng}
    assert quote["destination"] == {"lat": BACH_MAI.lat, "lng": BACH_MAI.lng}
    # Straight-line estimate: 3,393 m x 1.35 at 22 km/h.
    assert quote["distance_m"] == 4581
    assert quote["duration_s"] == 750
    assert quote["estimated"] is True
    # 20,000 + 4.581 km x 11,000 + 12.5 min x 500 = 76,641
    assert quote["price_vnd"] == 77_000
    assert quote["peak"] is False
    assert quote["surge"] is False
    # The nearest car4 of the test seed is 322 m away: 20 s to accept + 71 s to drive.
    assert quote["pickup_eta_s"] == 91
    assert datetime.fromisoformat(quote["expires_at"]) == START + timedelta(seconds=300)


def test_quote_at_peak_hours_costs_more(client: TestClient, clock: FakeClock) -> None:
    clock.now = datetime(2026, 11, 16, 1, 0, tzinfo=UTC)  # 08:00 in Vietnam

    quote = make_quote(client, ride_type="car4")

    assert quote["peak"] is True
    assert quote["price_vnd"] == 100_000  # 76,641 x 1.3 = 99,633


def test_bigger_vehicles_cost_more(client: TestClient) -> None:
    prices = [make_quote(client, ride_type=t)["price_vnd"] for t in ("bike", "car4", "car7")]

    assert prices == sorted(prices)
    assert len(set(prices)) == 3


def test_same_seed_and_time_give_the_same_quote(make_client: ClientFactory) -> None:
    first = make_quote(make_client("a.db"), ride_type="car7")
    second = make_quote(make_client("b.db"), ride_type="car7")

    assert first.pop("id") != second.pop("id")
    assert first == second


def test_quote_without_a_driver_nearby_has_no_pickup_eta(client: TestClient) -> None:
    quote = make_quote(client, pickup=NOI_BAI, destination=BACH_MAI)

    assert quote["pickup_eta_s"] is None
    assert quote["price_vnd"] > 0


@pytest.mark.parametrize(
    "body",
    [
        quote_body(ride_type="truck"),
        quote_body() | {"pickup": {"lat": 91, "lng": 105.8}},
        {"ride_type": "car4", "pickup": {"lat": 21.0, "lng": 105.8}},
    ],
)
def test_invalid_quote_request_is_rejected(client: TestClient, body: dict) -> None:
    response = client.post("/quotes", json=body)

    assert response.status_code == 422
    assert error_code(response) == "validation_error"


@pytest.mark.parametrize(
    "body",
    [
        quote_body(destination=HO_CHI_MINH_CITY),
        quote_body(pickup=HO_CHI_MINH_CITY),
    ],
)
def test_trip_outside_hanoi_is_rejected(client: TestClient, body: dict) -> None:
    response = client.post("/quotes", json=body)

    assert response.status_code == 422
    assert error_code(response) == "out_of_service_area"


def test_trip_to_the_same_place_is_rejected(client: TestClient) -> None:
    response = client.post("/quotes", json=quote_body(pickup=LANG_HA, destination=LANG_HA))

    assert response.status_code == 422
    assert error_code(response) == "trip_too_short"
