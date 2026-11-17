"""Places and tool calls shared by the ride tests."""

from typing import Any

from httpx import AsyncClient, Response

from app.services.ride.provider import GeoPoint, ProviderPlace
from tests.conftest import DOGRAH_HEADERS
from tests.fakes import FakeRideProvider

BACH_MAI = ProviderPlace("Bệnh viện Bạch Mai", "78 Đường Giải Phóng", GeoPoint(21.00182, 105.83967))
LANG_HA = ProviderPlace("Ngõ 12 Phố Láng Hạ", "", GeoPoint(21.0205, 105.817))
CHO_HOM = ProviderPlace("Chợ Hôm", "79 Phố Huế", GeoPoint(21.01717, 105.85197))
DONG_DA = ProviderPlace("Bệnh viện Đa khoa Đống Đa", "", GeoPoint(21.01568, 105.82694))


async def ride_tool(client: AsyncClient, name: str, token: str, **body: Any) -> Response:
    """POST /tools/<name> as Dograh would, with the call's token."""
    return await client.post(
        f"/tools/{name}", json={"session_token": token, **body}, headers=DOGRAH_HEADERS
    )


async def search(client: AsyncClient, token: str, query: str) -> dict[str, Any]:
    response = await ride_tool(client, "search-location", token, query=query)
    assert response.status_code == 200, response.text
    return response.json()


async def find(
    client: AsyncClient, rides: FakeRideProvider, token: str, place: ProviderPlace
) -> int:
    """Have the provider find `place` and return its option number in the call."""
    rides.places = [place]
    options = (await search(client, token, place.name))["options"]
    return options[0]["ref"]


async def book_trip(
    client: AsyncClient,
    rides: FakeRideProvider,
    token: str,
    pickup: ProviderPlace,
    destination: ProviderPlace,
    ride_type: str = "car4",
) -> dict[str, Any]:
    """Search both places, quote and book (needs `no_confirm_wait`)."""
    pickup_ref = await find(client, rides, token, pickup)
    destination_ref = await find(client, rides, token, destination)
    quoted = await ride_tool(
        client,
        "get-ride-quote",
        token,
        pickup_ref=pickup_ref,
        destination_ref=destination_ref,
        ride_type=ride_type,
    )
    assert quoted.json()["status"] == "quoted", quoted.text
    booked = await ride_tool(client, "book-ride", token, ride_type=ride_type)
    assert booked.json()["status"] == "booked", booked.text
    return booked.json()
