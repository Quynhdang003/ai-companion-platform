import math
from dataclasses import dataclass

EARTH_RADIUS_M = 6_371_000


@dataclass(frozen=True)
class Point:
    lat: float
    lng: float


@dataclass(frozen=True)
class Area:
    """A latitude/longitude box."""

    south: float
    west: float
    north: float
    east: float

    def contains(self, point: Point) -> bool:
        return self.south <= point.lat <= self.north and self.west <= point.lng <= self.east


# Greater Hanoi, Noi Bai airport included: trips must start and end inside it.
SERVICE_AREA = Area(south=20.80, west=105.55, north=21.25, east=106.05)


def haversine_m(a: Point, b: Point) -> float:
    """Straight-line distance over the Earth's surface, in metres."""
    lat_a, lat_b = math.radians(a.lat), math.radians(b.lat)
    d_lat = lat_b - lat_a
    d_lng = math.radians(b.lng - a.lng)
    h = math.sin(d_lat / 2) ** 2 + math.cos(lat_a) * math.cos(lat_b) * math.sin(d_lng / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))
