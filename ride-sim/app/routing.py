"""Distance and travel time between two points.

`Router` is the interface quotes are priced through. `OsrmRouter` asks an OSRM server for
the road route; `StraightLineRouter` needs no road network or network access, and its
estimate is also what `OsrmRouter` answers when the server fails.
"""

import logging
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.geo import Point, haversine_m

logger = logging.getLogger(__name__)

# Roads are longer than the straight line between two points in a city.
DETOUR_FACTOR = 1.35
# Average speed in Hanoi traffic, stops included.
CITY_SPEED_KMH = 22.0
# OSRM's durations assume empty roads; Hanoi traffic takes about this much longer.
TRAFFIC_FACTOR = 1.8


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


class OsrmRouter:
    """Driving routes from an OSRM server (`/route/v1/driving`).

    Never fails: a slow, unreachable or confused server gives the straight-line estimate,
    marked `estimated`.
    """

    def __init__(self, client: httpx.AsyncClient, base_url: str, timeout: float) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def route(self, origin: Point, destination: Point) -> Route:
        # OSRM takes longitude first.
        coordinates = f"{origin.lng},{origin.lat};{destination.lng},{destination.lat}"
        try:
            response = await self._client.get(
                f"{self._base_url}/route/v1/driving/{coordinates}",
                params={"overview": "false"},
                timeout=self._timeout,
            )
            response.raise_for_status()
            body = response.json()
            if body["code"] != "Ok":
                raise ValueError(f"OSRM answered {body['code']}")
            best = body["routes"][0]
            return Route(
                distance_m=round(best["distance"]),
                duration_s=round(best["duration"] * TRAFFIC_FACTOR),
                estimated=False,
            )
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
            # No URL in the log: it holds the coordinates of someone's pickup.
            logger.warning("OSRM route failed (%s): using the estimate", type(exc).__name__)
            return estimate_route(origin, destination)
