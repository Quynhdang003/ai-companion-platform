"""Fake drivers around Hanoi and the choice of one for a pickup.

Drivers are generated from a seed, not stored: the same seed always gives the same drivers,
and each waits at its own fixed spot between trips.
"""

import random
from collections.abc import Collection, Sequence
from dataclasses import dataclass

from app.geo import Area, Point, haversine_m
from app.models import RideType
from app.routing import estimate_route

# Inner Hanoi, where the drivers wait.
DRIVER_AREA = Area(south=20.96, west=105.77, north=21.08, east=105.89)
# A driver farther from the pickup than this (straight line) isn't offered the trip.
MAX_PICKUP_DISTANCE_M = 10_000
# A driver next to the pickup still needs this long to get there (simulated seconds).
MIN_PICKUP_DURATION_S = 60

# The mix of ride types, repeated over the drivers: from 10 drivers up, every type has some.
_TYPE_PATTERN = (RideType.BIKE,) * 5 + (RideType.CAR4,) * 3 + (RideType.BIKE, RideType.CAR7)
_VEHICLES: dict[RideType, tuple[str, ...]] = {
    RideType.BIKE: ("Honda Wave", "Honda Vision", "Honda Air Blade", "Yamaha Sirius"),
    RideType.CAR4: ("Toyota Vios", "Hyundai Accent", "Kia Soluto", "VinFast VF 5"),
    RideType.CAR7: ("Toyota Innova", "Mitsubishi Xpander", "Kia Carens"),
}
_FAMILY_NAMES = ("Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Vũ", "Đặng", "Bùi", "Đỗ", "Ngô")
_MIDDLE_NAMES = ("Văn", "Đức", "Minh", "Quang", "Hữu", "Xuân")
_GIVEN_NAMES = (
    "Anh", "Bình", "Cường", "Dũng", "Hải", "Hùng", "Khánh", "Long",
    "Nam", "Phong", "Quân", "Sơn", "Thắng", "Tuấn", "Việt",
)  # fmt: skip
_PLATE_LETTERS = "ABCDEFGHKLMNPSTUVXYZ"


@dataclass(frozen=True)
class Driver:
    id: str
    name: str
    ride_type: RideType
    vehicle: str
    plate: str
    # Where the driver waits between trips.
    position: Point


def seed_drivers(seed: int, count: int) -> list[Driver]:
    rng = random.Random(seed)
    plates: set[str] = set()
    drivers = []
    for index in range(count):
        ride_type = _TYPE_PATTERN[index % len(_TYPE_PATTERN)]
        plate = _plate(rng, ride_type)
        while plate in plates:
            plate = _plate(rng, ride_type)
        plates.add(plate)
        drivers.append(
            Driver(
                id=f"D{index + 1:03d}",
                name=" ".join(
                    (rng.choice(_FAMILY_NAMES), rng.choice(_MIDDLE_NAMES), rng.choice(_GIVEN_NAMES))
                ),
                ride_type=ride_type,
                vehicle=rng.choice(_VEHICLES[ride_type]),
                plate=plate,
                position=Point(
                    lat=round(rng.uniform(DRIVER_AREA.south, DRIVER_AREA.north), 6),
                    lng=round(rng.uniform(DRIVER_AREA.west, DRIVER_AREA.east), 6),
                ),
            )
        )
    return drivers


def _plate(rng: random.Random, ride_type: RideType) -> str:
    """Hanoi plates: `29B1-123.45` for motorbikes, `30H-123.45` for cars."""
    letter = rng.choice(_PLATE_LETTERS)
    number = f"{rng.randrange(1000):03d}.{rng.randrange(100):02d}"
    if ride_type is RideType.BIKE:
        return f"29{letter}{rng.randrange(1, 10)}-{number}"
    return f"30{letter}-{number}"


def nearest_driver(
    drivers: Sequence[Driver], ride_type: RideType, pickup: Point, *, busy: Collection[str]
) -> Driver | None:
    """The closest free driver of that ride type, or None when none is close enough."""
    free = [d for d in drivers if d.ride_type is ride_type and d.id not in busy]
    if not free:
        return None
    driver = min(free, key=lambda d: haversine_m(d.position, pickup))
    if haversine_m(driver.position, pickup) > MAX_PICKUP_DISTANCE_M:
        return None
    return driver


def pickup_duration_s(driver: Driver, pickup: Point) -> int:
    """Simulated seconds the driver needs to reach the pickup.

    Always the straight-line estimate, whatever router prices the trips: it only spaces
    out the simulation, and keeps one booking to one routed trip.
    """
    return max(MIN_PICKUP_DURATION_S, estimate_route(driver.position, pickup).duration_s)
