"""Place search: from a few words to places with coordinates.

`PlaceSearch` answers from the built-in list of well-known Hanoi places (fixed results, no
network), and asks a `Geocoder` (Photon) only for what isn't on it.
"""

import json
import logging
import re
import unicodedata
from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, Self

import httpx

from app.geo import SERVICE_AREA, Point, haversine_m

logger = logging.getLogger(__name__)

_PLACES_FILE = Path(__file__).parent / "data" / "hanoi_places.json"
# Photon is biased towards results near the centre of Hanoi (Hoan Kiem lake).
_HANOI_CENTRE = Point(21.0285, 105.8542)
# Two results closer than this are the same place for a rider (a building and its gate).
SAME_PLACE_M = 150
# Words a caller may add to any place in Hanoi: they needn't be in its name.
_CITY_WORDS = frozenset({"ha", "noi"})
# OpenStreetMap objects that aren't somewhere to be picked up or dropped off.
_SKIPPED_KEYS = frozenset({"boundary"})
_SKIPPED_TAGS = frozenset({("highway", "bus_stop"), ("highway", "motorway"), ("highway", "trunk")})
_RAIL_STOPS = frozenset({"station", "halt"})


@dataclass(frozen=True)
class Place:
    name: str
    # Street address when known, else "".
    address: str
    location: Point
    # Where it came from: "builtin" or "photon".
    source: str


class GeocodingError(Exception):
    """The geocoder couldn't answer (unreachable, slow, or an unexpected body)."""


class Geocoder(Protocol):
    async def search(self, query: str, limit: int) -> list[Place]:
        """Places matching `query`, best first. Raises `GeocodingError`."""
        ...


def fold(text: str) -> str:
    """Lower case without Vietnamese diacritics: "Bệnh viện Đống Đa" -> "benh vien dong da"."""
    decomposed = unicodedata.normalize("NFD", text.lower().replace("đ", "d"))
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", fold(text))


@dataclass(frozen=True)
class _KnownPlace:
    place: Place
    # The words of its name and of each alias.
    variants: tuple[frozenset[str], ...]


class BuiltinPlaces:
    """Well-known Hanoi places shipped with the simulator (`data/hanoi_places.json`)."""

    def __init__(self, entries: Sequence[dict[str, Any]]) -> None:
        self._known = [
            _KnownPlace(
                place=Place(
                    name=entry["name"],
                    address=entry.get("address", ""),
                    location=Point(entry["lat"], entry["lng"]),
                    source="builtin",
                ),
                variants=tuple(
                    frozenset(words(name)) for name in (entry["name"], *entry.get("aliases", ()))
                ),
            )
            for entry in entries
        ]

    @classmethod
    def load(cls) -> Self:
        return cls(json.loads(_PLACES_FILE.read_text(encoding="utf-8"))["places"])

    @property
    def places(self) -> list[Place]:
        return [known.place for known in self._known]

    def search(self, query: str, limit: int) -> list[Place]:
        """Places whose name (or an alias) has every word of the query, closest name first.

        Diacritics and word order don't matter; "hà nội" added to a name is ignored.
        """
        asked = set(words(query))
        scored = []
        for index, known in enumerate(self._known):
            extra = min(
                (
                    len(variant - asked)
                    for variant in known.variants
                    if asked & variant and asked - variant <= _CITY_WORDS
                ),
                default=None,
            )
            if extra is not None:
                scored.append((extra, index, known.place))
        return [place for _, _, place in sorted(scored)[:limit]]


class PhotonGeocoder:
    """Photon (OpenStreetMap search, `/api`), limited to the service area.

    Only the query text is sent: no caller data.
    """

    def __init__(self, client: httpx.AsyncClient, base_url: str, timeout: float) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def search(self, query: str, limit: int) -> list[Place]:
        area = SERVICE_AREA
        try:
            response = await self._client.get(
                f"{self._base_url}/api",
                params={
                    "q": query,
                    "limit": limit,
                    "lat": _HANOI_CENTRE.lat,
                    "lon": _HANOI_CENTRE.lng,
                    "bbox": f"{area.west},{area.south},{area.east},{area.north}",
                },
                timeout=self._timeout,
            )
            response.raise_for_status()
            features = response.json()["features"]
            places = [place for feature in features if (place := _photon_place(feature))]
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError) as exc:
            raise GeocodingError(type(exc).__name__) from None
        return places


def _photon_place(feature: dict[str, Any]) -> Place | None:
    """A GeoJSON feature as a place; None for what a rider can't be taken to."""
    properties = feature["properties"]
    key, value = properties.get("osm_key"), properties.get("osm_value")
    if (
        key in _SKIPPED_KEYS
        or (key, value) in _SKIPPED_TAGS
        or (key == "railway" and value not in _RAIL_STOPS)
    ):
        return None
    lng, lat = feature["geometry"]["coordinates"][:2]
    location = Point(float(lat), float(lng))
    if not SERVICE_AREA.contains(location):
        return None

    street = " ".join(
        part for part in (properties.get("housenumber"), properties.get("street")) if part
    )
    name = properties.get("name") or street
    if not name:
        return None
    return Place(
        name=name, address=street if street != name else "", location=location, source="photon"
    )


class PlaceSearch:
    """What `/places/search` answers with.

    A query matching built-in places gets only those, at once: well-known places don't wait
    for the geocoder (public Photon takes seconds). Anything else goes to the geocoder, whose
    answers are kept in memory, so asking again is instant. A geocoder failure is an empty
    answer, never an error.
    """

    # Geocoder answers kept, oldest dropped first.
    CACHE_SIZE = 512

    def __init__(self, builtin: BuiltinPlaces, geocoder: Geocoder | None) -> None:
        self._builtin = builtin
        self._geocoder = geocoder
        self._cache: OrderedDict[tuple[str, int], list[Place]] = OrderedDict()

    async def search(self, query: str, limit: int) -> list[Place]:
        places = self._builtin.search(query, limit)
        if places or self._geocoder is None:
            return places
        try:
            found = await self._geocode(query, limit)
        except GeocodingError as exc:
            # The query isn't logged: it may be someone's home address.
            logger.warning("Place search failed (%s): no places", exc)
            return []
        for place in found:
            if len(places) == limit:
                break
            if all(haversine_m(place.location, kept.location) > SAME_PLACE_M for kept in places):
                places.append(place)
        return places

    async def _geocode(self, query: str, limit: int) -> list[Place]:
        assert self._geocoder is not None
        key = (" ".join(query.lower().split()), limit)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        # More than needed: the same place often comes back several times.
        found = await self._geocoder.search(query, limit * 3)
        self._cache[key] = found
        if len(self._cache) > self.CACHE_SIZE:
            self._cache.popitem(last=False)
        return found
