"""Distance and travel time between two points.

`Router` is the interface quotes are priced through. `StraightLineRouter` needs no road
network or network access: it is the simulator's router until a road router is added, and
its fallback after that.
"""

from dataclasses import dataclass
from typing import Protocol

from app.geo import Point, haversine_m

# Roads are longer than the straight line between two points in a city.
DETOUR_FACTOR = 1.35
# Average speed in Hanoi traffic, stops included.
CITY_SPEED_KMH = 22.0


@dataclass(frozen=True)
class Route:
    distance_m: int
    duration_s: int
    # True when it doesn't come from a road network.
    estimated: bool


class Router(Protocol):
    async def route(self, origin: Point, destination: Point) -> Route: ...


def estimate_route(origin: Point, destination: Point) -> Route:
    distance_m = haversine_m(origin, destination) * DETOUR_FACTOR
    duration_s = distance_m / (CITY_SPEED_KMH * 1000 / 3600)
    return Route(distance_m=round(distance_m), duration_s=round(duration_s), estimated=True)


class StraightLineRouter:
    async def route(self, origin: Point, destination: Point) -> Route:
        return estimate_route(origin, destination)
