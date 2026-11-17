import asyncio

import pytest

from app.geo import SERVICE_AREA, haversine_m
from app.routing import StraightLineRouter, estimate_route
from tests.helpers import BACH_MAI, HO_CHI_MINH_CITY, HOAN_KIEM, NOI_BAI


def test_haversine_distance_between_two_hanoi_places() -> None:
    # 0.0284 degrees of latitude (3,158 m) and 0.0113 of longitude (1,173 m at 21 N).
    assert haversine_m(HOAN_KIEM, BACH_MAI) == pytest.approx(3_369, abs=5)
    assert haversine_m(BACH_MAI, HOAN_KIEM) == pytest.approx(haversine_m(HOAN_KIEM, BACH_MAI))
    assert haversine_m(BACH_MAI, BACH_MAI) == 0


def test_service_area_is_greater_hanoi() -> None:
    assert SERVICE_AREA.contains(BACH_MAI)
    assert SERVICE_AREA.contains(NOI_BAI)
    assert not SERVICE_AREA.contains(HO_CHI_MINH_CITY)


def test_estimate_adds_a_detour_and_uses_city_speed() -> None:
    route = estimate_route(HOAN_KIEM, BACH_MAI)

    # 3,369 m x 1.35, driven at 22 km/h.
    assert route.distance_m == pytest.approx(4_548, abs=8)
    assert route.duration_s == pytest.approx(744, abs=2)
    assert route.estimated is True


def test_straight_line_router_returns_the_estimate() -> None:
    route = asyncio.run(StraightLineRouter().route(HOAN_KIEM, BACH_MAI))

    assert route == estimate_route(HOAN_KIEM, BACH_MAI)
