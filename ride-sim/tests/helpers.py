"""Places and request helpers shared by the API tests."""

from typing import Any

from fastapi.testclient import TestClient

from app.geo import Point

LANG_HA = Point(21.0168, 105.8136)
BACH_MAI = Point(21.0003, 105.8411)
HOAN_KIEM = Point(21.0287, 105.8524)
# Inside the service area, but over 10 km from where the drivers wait.
NOI_BAI = Point(21.2187, 105.8042)
HO_CHI_MINH_CITY = Point(10.7769, 106.7009)


def quote_body(
    ride_type: str = "car4", pickup: Point = LANG_HA, destination: Point = BACH_MAI
) -> dict[str, Any]:
    return {
        "ride_type": ride_type,
        "pickup": {"lat": pickup.lat, "lng": pickup.lng},
        "destination": {"lat": destination.lat, "lng": destination.lng},
    }


def make_quote(client: TestClient, **kwargs: Any) -> dict[str, Any]:
    response = client.post("/quotes", json=quote_body(**kwargs))
    assert response.status_code == 201, response.text
    return response.json()


def make_booking(client: TestClient, **kwargs: Any) -> dict[str, Any]:
    """Quote a trip and book it."""
    response = client.post("/bookings", json={"quote_id": make_quote(client, **kwargs)["id"]})
    assert response.status_code == 201, response.text
    return response.json()


def get_booking(client: TestClient, booking_id: str) -> dict[str, Any]:
    response = client.get(f"/bookings/{booking_id}")
    assert response.status_code == 200, response.text
    return response.json()


def error_code(response: Any) -> str:
    return response.json()["error"]["code"]
