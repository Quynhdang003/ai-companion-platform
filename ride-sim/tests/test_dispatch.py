import re

from app.dispatch import (
    DRIVER_AREA,
    MIN_PICKUP_DURATION_S,
    Driver,
    nearest_driver,
    pickup_duration_s,
    seed_drivers,
)
from app.geo import Point
from app.models import RideType
from app.routing import estimate_route
from tests.helpers import BACH_MAI, HOAN_KIEM, LANG_HA, NOI_BAI


def _driver(driver_id: str, ride_type: RideType, position: Point) -> Driver:
    return Driver(
        id=driver_id,
        name="Nguyễn Văn Nam",
        ride_type=ride_type,
        vehicle="Toyota Vios",
        plate="30H-123.45",
        position=position,
    )


def test_same_seed_gives_the_same_drivers() -> None:
    assert seed_drivers(7, 60) == seed_drivers(7, 60)
    assert seed_drivers(7, 60) != seed_drivers(8, 60)


def test_seeded_drivers_are_distinct_and_wait_in_inner_hanoi() -> None:
    drivers = seed_drivers(7, 60)

    assert len(drivers) == 60
    assert len({d.id for d in drivers}) == 60
    assert len({d.plate for d in drivers}) == 60
    assert all(DRIVER_AREA.contains(d.position) for d in drivers)


def test_every_ride_type_has_drivers_even_in_a_small_fleet() -> None:
    assert {d.ride_type for d in seed_drivers(7, 10)} == set(RideType)


def test_plates_look_like_hanoi_plates() -> None:
    for driver in seed_drivers(7, 60):
        pattern = (
            r"29[A-Z][1-9]-\d{3}\.\d{2}"
            if driver.ride_type is RideType.BIKE
            else r"30[A-Z]-\d{3}\.\d{2}"
        )
        assert re.fullmatch(pattern, driver.plate), driver.plate


def test_nearest_free_driver_of_the_ride_type_is_chosen() -> None:
    drivers = [
        _driver("far", RideType.CAR4, HOAN_KIEM),
        _driver("near", RideType.CAR4, LANG_HA),
        _driver("bike", RideType.BIKE, LANG_HA),
    ]

    assert nearest_driver(drivers, RideType.CAR4, LANG_HA, busy=set()).id == "near"
    assert nearest_driver(drivers, RideType.CAR4, LANG_HA, busy={"near"}).id == "far"
    assert nearest_driver(drivers, RideType.CAR4, LANG_HA, busy={"near", "far"}) is None
    assert nearest_driver(drivers, RideType.CAR7, LANG_HA, busy=set()) is None


def test_no_driver_when_the_closest_one_is_too_far() -> None:
    drivers = [_driver("inner", RideType.CAR4, HOAN_KIEM)]

    assert nearest_driver(drivers, RideType.CAR4, NOI_BAI, busy=set()) is None


def test_pickup_duration_is_the_estimate_with_a_minimum() -> None:
    driver = _driver("d", RideType.CAR4, HOAN_KIEM)

    assert pickup_duration_s(driver, BACH_MAI) == estimate_route(HOAN_KIEM, BACH_MAI).duration_s
    assert pickup_duration_s(driver, HOAN_KIEM) == MIN_PICKUP_DURATION_S
