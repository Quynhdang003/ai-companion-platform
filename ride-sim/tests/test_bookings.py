import re
from datetime import datetime

from fastapi.testclient import TestClient

from tests.conftest import ClientFactory, FakeClock
from tests.helpers import (
    BACH_MAI,
    LANG_HA,
    NOI_BAI,
    error_code,
    get_booking,
    make_booking,
    make_quote,
)

# A bike from Lang Ha to Bach Mai with the test seed: the driver accepts after 20 s and
# reaches the pickup 354 s after the booking; the trip takes 750 s.
PICKUP_AFTER = 354
DROPOFF_AFTER = 354 + 750


def _bike(client: TestClient) -> dict:
    return make_booking(client, ride_type="bike", pickup=LANG_HA, destination=BACH_MAI)


def test_new_booking_is_looking_for_a_driver(client: TestClient) -> None:
    quote = make_quote(client, ride_type="bike")

    response = client.post("/bookings", json={"quote_id": quote["id"]})

    assert response.status_code == 201
    booking = response.json()
    assert booking["id"]
    assert booking["quote_id"] == quote["id"]
    assert booking["status"] == "REQUESTED"
    assert booking["driver"] is None
    for key in ("ride_type", "pickup", "destination", "distance_m", "duration_s", "price_vnd"):
        assert booking[key] == quote[key]
    assert booking["pickup_eta_s"] == quote["pickup_eta_s"] == PICKUP_AFTER
    assert booking["dropoff_eta_s"] == DROPOFF_AFTER
    assert booking["cancelled_at"] is None
    assert booking["cancel_reason"] is None


def test_booking_follows_the_ride_to_the_end(client: TestClient, clock: FakeClock) -> None:
    booking_id = _bike(client)["id"]

    def at(seconds: int) -> dict:
        clock.advance(seconds - at.elapsed)
        at.elapsed = seconds
        return get_booking(client, booking_id)

    at.elapsed = 0

    assert at(19)["status"] == "REQUESTED"

    assigned = at(20)
    assert assigned["status"] == "DRIVER_ASSIGNED"
    assert assigned["driver"]["name"]
    assert assigned["driver"]["vehicle"]
    assert re.fullmatch(r"29[A-Z][1-9]-\d{3}\.\d{2}", assigned["driver"]["plate"])
    assert assigned["pickup_eta_s"] == PICKUP_AFTER - 20

    assert at(PICKUP_AFTER - 121)["status"] == "DRIVER_ASSIGNED"
    assert at(PICKUP_AFTER - 120)["status"] == "ARRIVING"
    almost_there = at(PICKUP_AFTER - 1)
    assert almost_there["status"] == "ARRIVING"
    assert almost_there["pickup_eta_s"] == 1

    on_board = at(PICKUP_AFTER)
    assert on_board["status"] == "IN_PROGRESS"
    assert on_board["pickup_eta_s"] is None
    assert on_board["dropoff_eta_s"] == 750
    assert at(DROPOFF_AFTER - 1)["status"] == "IN_PROGRESS"

    done = at(DROPOFF_AFTER)
    assert done["status"] == "COMPLETED"
    assert done["pickup_eta_s"] is None
    assert done["dropoff_eta_s"] is None
    assert done["driver"] == assigned["driver"]


def test_time_scale_speeds_the_ride_up(make_client: ClientFactory, clock: FakeClock) -> None:
    client = make_client(time_scale=30)
    booking = _bike(client)

    # ETAs stay in simulated seconds; real time runs 30 times faster.
    assert booking["pickup_eta_s"] == PICKUP_AFTER
    clock.advance(1)
    assert get_booking(client, booking["id"])["pickup_eta_s"] == PICKUP_AFTER - 30
    clock.advance(PICKUP_AFTER / 30 - 1)
    assert get_booking(client, booking["id"])["status"] == "IN_PROGRESS"
    clock.advance(750 / 30)
    assert get_booking(client, booking["id"])["status"] == "COMPLETED"


def test_booking_a_quote_again_returns_the_same_booking(
    client: TestClient, clock: FakeClock
) -> None:
    quote = make_quote(client)
    first = client.post("/bookings", json={"quote_id": quote["id"]})

    clock.advance(30)
    again = client.post("/bookings", json={"quote_id": quote["id"]})
    # Even once the quote itself has expired.
    clock.advance(600)
    much_later = client.post("/bookings", json={"quote_id": quote["id"]})

    assert first.status_code == 201
    assert again.status_code == 200
    assert much_later.status_code == 200
    assert again.json()["id"] == much_later.json()["id"] == first.json()["id"]
    assert again.json()["requested_at"] == first.json()["requested_at"]


def test_quote_can_be_booked_until_it_expires(client: TestClient, clock: FakeClock) -> None:
    in_time, too_late = make_quote(client), make_quote(client)

    clock.advance(299)
    assert client.post("/bookings", json={"quote_id": in_time["id"]}).status_code == 201

    clock.advance(1)
    response = client.post("/bookings", json={"quote_id": too_late["id"]})
    assert response.status_code == 409
    assert error_code(response) == "quote_expired"


def test_unknown_quote_cannot_be_booked(client: TestClient) -> None:
    response = client.post("/bookings", json={"quote_id": "nope"})

    assert response.status_code == 404
    assert error_code(response) == "quote_not_found"


def test_booking_request_needs_a_quote_id(client: TestClient) -> None:
    response = client.post("/bookings", json={})

    assert response.status_code == 422
    assert error_code(response) == "validation_error"


def test_no_driver_near_the_pickup(client: TestClient) -> None:
    quote = make_quote(client, pickup=NOI_BAI, destination=BACH_MAI)

    response = client.post("/bookings", json={"quote_id": quote["id"]})

    assert response.status_code == 409
    assert error_code(response) == "no_driver_available"


def test_a_driver_is_busy_until_the_ride_ends(client: TestClient, clock: FakeClock) -> None:
    first, second = _bike(client), _bike(client)
    clock.advance(20)
    first_driver = get_booking(client, first["id"])["driver"]
    second_driver = get_booking(client, second["id"])["driver"]

    # The same trip asked twice: the nearest driver is taken, the next one comes.
    assert first_driver != second_driver
    assert second["pickup_eta_s"] > first["pickup_eta_s"]

    # Once the first ride is over, its driver takes the next request.
    clock.advance(DROPOFF_AFTER)
    third = _bike(client)
    clock.advance(20)
    assert get_booking(client, third["id"])["driver"] == first_driver


def test_cancelling_frees_the_driver(client: TestClient, clock: FakeClock) -> None:
    first = _bike(client)
    clock.advance(20)
    first_driver = get_booking(client, first["id"])["driver"]

    assert client.post(f"/bookings/{first['id']}/cancel").status_code == 200
    second = _bike(client)
    clock.advance(20)

    assert get_booking(client, second["id"])["driver"] == first_driver


def test_cancel_on_the_way_to_the_pickup(client: TestClient, clock: FakeClock) -> None:
    booking = _bike(client)
    clock.advance(60)
    cancel_time = clock.now

    response = client.post(f"/bookings/{booking['id']}/cancel")

    assert response.status_code == 200
    cancelled = response.json()
    assert cancelled["status"] == "CANCELLED"
    assert cancelled["cancel_reason"] == "rider"
    assert datetime.fromisoformat(cancelled["cancelled_at"]) == cancel_time
    assert cancelled["pickup_eta_s"] is None
    assert cancelled["dropoff_eta_s"] is None
    assert cancelled["driver"] is not None

    # Cancelling again changes nothing, and it stays cancelled.
    clock.advance(5_000)
    again = client.post(f"/bookings/{booking['id']}/cancel")
    assert again.status_code == 200
    assert again.json() == cancelled
    assert get_booking(client, booking["id"]) == cancelled


def test_ride_cancelled_before_a_driver_accepted_has_no_driver(
    client: TestClient, clock: FakeClock
) -> None:
    booking = _bike(client)
    clock.advance(10)

    cancelled = client.post(f"/bookings/{booking['id']}/cancel").json()
    clock.advance(600)

    assert cancelled["status"] == "CANCELLED"
    assert cancelled["driver"] is None
    assert get_booking(client, booking["id"])["driver"] is None


def test_ride_in_progress_cannot_be_cancelled(client: TestClient, clock: FakeClock) -> None:
    booking = _bike(client)
    clock.advance(PICKUP_AFTER)

    response = client.post(f"/bookings/{booking['id']}/cancel")

    assert response.status_code == 409
    assert error_code(response) == "ride_in_progress"
    assert get_booking(client, booking["id"])["status"] == "IN_PROGRESS"


def test_completed_ride_cannot_be_cancelled(client: TestClient, clock: FakeClock) -> None:
    booking = _bike(client)
    clock.advance(DROPOFF_AFTER)

    response = client.post(f"/bookings/{booking['id']}/cancel")

    assert response.status_code == 409
    assert error_code(response) == "ride_completed"
    assert get_booking(client, booking["id"])["status"] == "COMPLETED"


def test_unknown_booking(client: TestClient) -> None:
    for response in (client.get("/bookings/nope"), client.post("/bookings/nope/cancel")):
        assert response.status_code == 404
        assert error_code(response) == "booking_not_found"


def test_bookings_survive_a_restart(make_client: ClientFactory, clock: FakeClock) -> None:
    before = make_client("same.db")
    booking = _bike(before)
    clock.advance(20)
    seen_before = get_booking(before, booking["id"])

    after = make_client("same.db")

    assert get_booking(after, booking["id"]) == seen_before
