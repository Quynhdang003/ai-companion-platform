"""The public map servers the simulator uses by default. Network needed: `pytest -m live`."""

import asyncio

import httpx
import pytest

from app.config import Settings
from app.geo import haversine_m
from app.geocoding import BuiltinPlaces, PhotonGeocoder, Place
from app.main import USER_AGENT
from app.routing import OsrmRouter, Route
from tests.helpers import BACH_MAI, LANG_HA

pytestmark = pytest.mark.live

DEFAULTS = Settings(_env_file=None)


def test_public_osrm_routes_a_hanoi_trip() -> None:
    async def run() -> Route:
        async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}) as client:
            return await OsrmRouter(client, DEFAULTS.osrm_base_url, timeout=10).route(
                LANG_HA, BACH_MAI
            )

    route = asyncio.run(run())

    assert route.estimated is False
    assert 3_000 < route.distance_m < 7_000


def test_public_photon_finds_a_hanoi_hospital() -> None:
    async def run() -> list[Place]:
        async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}) as client:
            return await PhotonGeocoder(client, DEFAULTS.photon_base_url, timeout=10).search(
                "Bệnh viện Bạch Mai", 5
            )

    places = asyncio.run(run())
    [builtin] = BuiltinPlaces.load().search("Bệnh viện Bạch Mai", 1)

    assert any(haversine_m(place.location, builtin.location) < 300 for place in places)
