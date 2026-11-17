""" "Same as last time": the last ride in the pre-call hook, earlier places in search."""

from datetime import UTC, datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Elder, ElderStatus, PlaceSource, RideBooking, RidePlaceOption, RideStatus
from app.services.ride.history import name_words
from app.services.ride.provider import GeoPoint, ProviderPlace
from tests.conftest import DOGRAH_HEADERS, add_elder, start_call
from tests.fakes import FakeRideProvider
from tests.ride_helpers import BACH_MAI, CHO_HOM, DONG_DA, LANG_HA, book_trip, search

pytestmark = pytest.mark.usefixtures("no_confirm_wait")

PHONE = "0912345678"


async def _initial_context(client: AsyncClient, number: str = PHONE) -> dict:
    body = {"event": "call_inbound", "call_inbound": {"from_number": number}}
    response = await client.post("/hooks/pre-call", json=body, headers=DOGRAH_HEADERS)
    assert response.status_code == 200
    return response.json()["initial_context"]


@pytest.fixture
async def elder(session: AsyncSession) -> Elder:
    return await add_elder(session, status=ElderStatus.ACTIVE)


def _today() -> str:
    return datetime.now(UTC).astimezone(timezone(timedelta(hours=7))).strftime("%d/%m")


async def test_no_last_ride_before_the_first(client: AsyncClient, elder: Elder) -> None:
    assert "last_ride" not in await _initial_context(client)


async def test_last_ride_is_told_in_the_next_call(
    client: AsyncClient, rides: FakeRideProvider, elder: Elder
) -> None:
    await book_trip(client, rides, await start_call(client), CHO_HOM, BACH_MAI, "bike")
    await book_trip(client, rides, await start_call(client), LANG_HA, BACH_MAI, "car4")

    context = await _initial_context(client)

    assert context["last_ride"] == (
        f"Từ Ngõ 12 Phố Láng Hạ đến Bệnh viện Bạch Mai, xe bốn chỗ, ngày {_today()}"
    )


async def test_a_cancelled_ride_is_not_the_last_ride(
    client: AsyncClient, session: AsyncSession, rides: FakeRideProvider, elder: Elder
) -> None:
    await book_trip(client, rides, await start_call(client), CHO_HOM, BACH_MAI, "bike")
    await book_trip(client, rides, await start_call(client), LANG_HA, BACH_MAI, "car4")
    newest = await session.scalar(select(RideBooking).order_by(RideBooking.created_at.desc()))
    await session.execute(
        update(RideBooking).where(RideBooking.id == newest.id).values(status=RideStatus.CANCELLED),
        execution_options={"synchronize_session": "fetch"},
    )

    context = await _initial_context(client)

    assert context["last_ride"].startswith("Từ Chợ Hôm đến Bệnh viện Bạch Mai, xe máy")


async def test_other_callers_get_no_last_ride(
    client: AsyncClient, session: AsyncSession, rides: FakeRideProvider, elder: Elder
) -> None:
    await book_trip(client, rides, await start_call(client), LANG_HA, BACH_MAI)
    await add_elder(session, status=ElderStatus.ACTIVE, phone_e164="+84912000002")

    assert "last_ride" not in await _initial_context(client, "0912000002")
    assert "last_ride" not in await _initial_context(client, "0912000009")


async def test_places_of_earlier_rides_are_offered_first_and_at_once(
    client: AsyncClient, session: AsyncSession, rides: FakeRideProvider, elder: Elder
) -> None:
    await book_trip(client, rides, await start_call(client), LANG_HA, BACH_MAI)
    rides.searches.clear()
    rides.places = [CHO_HOM]
    token = await start_call(client)

    for query in ["Bệnh viện Bạch Mai", "bach mai", "Bạch Mai Hà Nội", "12 Láng Hạ"]:
        found = await search(client, token, query)
        assert found["status"] == "found", query
        assert len(found["options"]) == 1, query

    assert rides.searches == []
    options = (await session.scalars(select(RidePlaceOption).where(
        RidePlaceOption.source == PlaceSource.PREVIOUS
    ))).all()  # fmt: skip
    assert {(o.name, o.address) for o in options} == {
        ("Bệnh viện Bạch Mai", "78 Đường Giải Phóng"),
        ("Ngõ 12 Phố Láng Hạ", ""),
    }


async def test_a_more_precise_request_goes_to_the_provider(
    client: AsyncClient, rides: FakeRideProvider, elder: Elder
) -> None:
    await book_trip(client, rides, await start_call(client), LANG_HA, BACH_MAI)
    rides.searches.clear()
    rides.places = [CHO_HOM]
    token = await start_call(client)

    # "phố" is in neither the name nor the address of the hospital.
    found = await search(client, token, "phố Bạch Mai")

    assert rides.searches == [("phố Bạch Mai", 3)]
    assert [o["name"] for o in found["options"]] == ["Chợ Hôm"]


async def test_ha_dong_is_not_dong_da(
    client: AsyncClient, rides: FakeRideProvider, elder: Elder
) -> None:
    await book_trip(client, rides, await start_call(client), LANG_HA, DONG_DA)
    rides.searches.clear()
    token = await start_call(client)

    await search(client, token, "Hà Đông")

    assert rides.searches == [("Hà Đông", 3)]


async def test_each_place_is_offered_once(
    client: AsyncClient, rides: FakeRideProvider, elder: Elder
) -> None:
    gate = ProviderPlace("Cổng bệnh viện Bạch Mai", "", GeoPoint(21.0025, 105.8401))  # 88 m
    await book_trip(client, rides, await start_call(client), LANG_HA, BACH_MAI)
    await book_trip(client, rides, await start_call(client), LANG_HA, gate)

    found = await search(client, await start_call(client), "bạch mai")

    # The newest of the two names for the same place.
    assert [o["name"] for o in found["options"]] == ["Cổng bệnh viện Bạch Mai"]


async def test_earlier_rides_of_another_elder_are_not_offered(
    client: AsyncClient, session: AsyncSession, rides: FakeRideProvider, elder: Elder
) -> None:
    await book_trip(client, rides, await start_call(client), LANG_HA, BACH_MAI)
    await add_elder(session, status=ElderStatus.ACTIVE, phone_e164="+84912000002")
    rides.searches.clear()

    await search(client, await start_call(client, "0912000002"), "Bạch Mai")

    assert rides.searches == [("Bạch Mai", 3)]


def test_name_words_ignore_ha_noi_only_as_a_phrase() -> None:
    assert name_words("Chợ Đồng Xuân, Hà Nội") == {"cho", "dong", "xuan"}
    assert name_words("Bến xe Hà Đông") == {"ben", "xe", "ha", "dong"}
    assert name_words("Hà Nội") == frozenset()
