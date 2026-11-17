import asyncio
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from app.geo import SERVICE_AREA, Point
from app.geocoding import (
    BuiltinPlaces,
    GeocodingError,
    PhotonGeocoder,
    Place,
    PlaceSearch,
    fold,
    words,
)
from tests.helpers import HO_CHI_MINH_CITY, FakeGeocoder, photon_place

Handler = Callable[[httpx.Request], httpx.Response]


def test_fold_drops_vietnamese_diacritics() -> None:
    assert fold("Bệnh viện Đống Đa") == "benh vien dong da"
    assert words("Chợ  Hôm, Hà Nội!") == ["cho", "hom", "ha", "noi"]


# Built-in places


def _builtin(*entries: dict[str, Any]) -> BuiltinPlaces:
    return BuiltinPlaces([{"lat": 21.0, "lng": 105.8, **entry} for entry in entries])


def _names(places: list[Place]) -> list[str]:
    return [place.name for place in places]


def test_built_in_list_is_valid() -> None:
    places = BuiltinPlaces.load().places

    assert len(places) >= 40
    assert len({place.name for place in places}) == len(places)
    assert all(SERVICE_AREA.contains(place.location) for place in places)
    assert {place.source for place in places} == {"builtin"}


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("Bệnh viện Bạch Mai", "Bệnh viện Bạch Mai"),
        ("benh vien bach mai", "Bệnh viện Bạch Mai"),
        ("bạch mai", "Bệnh viện Bạch Mai"),
        ("bệnh viện Việt Đức", "Bệnh viện Hữu nghị Việt Đức"),
        ("Hồ Gươm", "Hồ Hoàn Kiếm"),
        ("lăng Bác", "Lăng Chủ tịch Hồ Chí Minh"),
        ("ga Hà Nội", "Ga Hà Nội"),
        ("chợ Đồng Xuân Hà Nội", "Chợ Đồng Xuân"),
        ("bến xe mỹ đình", "Bến xe Mỹ Đình"),
    ],
)
def test_well_known_places_are_built_in(query: str, expected: str) -> None:
    assert BuiltinPlaces.load().search(query, 5)[0].name == expected


def test_built_in_search_needs_every_word_of_the_query() -> None:
    places = _builtin({"name": "Chợ Hôm"}, {"name": "Chợ Đồng Xuân"})

    assert _names(places.search("chợ hôm", 5)) == ["Chợ Hôm"]
    assert places.search("chợ Hôm Đồng", 5) == []
    assert places.search("phố Huế", 5) == []
    assert places.search("Hà Nội", 5) == []


def test_ha_noi_is_ignored_only_as_a_phrase() -> None:
    places = _builtin(
        {"name": "Bệnh viện Đa khoa Đống Đa"},
        {"name": "Bệnh viện Tim Hà Nội"},
        {"name": "Bến xe Hà Đông"},
    )

    # "Hà" alone is part of a name: "Hà Đông" isn't "Đống Đa".
    assert _names(places.search("hà đông", 5)) == ["Bến xe Hà Đông"]
    assert _names(places.search("bệnh viện tim", 5)) == ["Bệnh viện Tim Hà Nội"]
    assert _names(places.search("Đống Đa Hà Nội", 5)) == ["Bệnh viện Đa khoa Đống Đa"]
    assert places.search("", 5) == []


def test_built_in_search_puts_the_closest_name_first() -> None:
    places = _builtin(
        {"name": "Bệnh viện Đại học Y"}, {"name": "Bệnh viện E"}, {"name": "Bệnh viện Tim"}
    )

    assert _names(places.search("bệnh viện", 5)) == [
        "Bệnh viện E",
        "Bệnh viện Tim",
        "Bệnh viện Đại học Y",
    ]
    assert _names(places.search("bệnh viện", 2)) == ["Bệnh viện E", "Bệnh viện Tim"]


def test_built_in_search_matches_aliases() -> None:
    places = _builtin({"name": "Hồ Hoàn Kiếm", "aliases": ["Hồ Gươm"]})

    assert _names(places.search("ho guom", 5)) == ["Hồ Hoàn Kiếm"]


# Photon


def _photon_search(handler: Handler, query: str = "bach mai", limit: int = 5) -> list[Place]:
    async def run() -> list[Place]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await PhotonGeocoder(client, "https://photon.test/", timeout=1).search(
                query, limit
            )

    return asyncio.run(run())


def _feature(lat: float, lng: float, **properties: str) -> dict[str, Any]:
    return {
        "type": "Feature",
        "properties": properties,
        "geometry": {"type": "Point", "coordinates": [lng, lat]},
    }


def test_photon_is_sent_only_the_query_and_the_area() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"type": "FeatureCollection", "features": []})

    assert _photon_search(handler, "Bệnh viện Bạch Mai", 15) == []
    [request] = seen
    assert (request.url.host, request.url.path) == ("photon.test", "/api")
    assert dict(request.url.params) == {
        "q": "Bệnh viện Bạch Mai",
        "limit": "15",
        "lat": "21.0285",
        "lon": "105.8542",
        "bbox": "105.55,20.8,106.05,21.25",
    }


def test_photon_results_nobody_can_be_driven_to_are_dropped() -> None:
    features = [
        _feature(
            21.00182,
            105.83967,
            name="Bệnh viện Bạch Mai",
            housenumber="78",
            street="Đường Giải Phóng",
            osm_key="amenity",
            osm_value="hospital",
        ),
        _feature(
            21.0014, 105.8411, name="Bạch Mai (cột trước)", osm_key="highway", osm_value="bus_stop"
        ),  # noqa: E501
        _feature(
            21.0036, 105.7767, name="Đại lộ Thăng Long", osm_key="highway", osm_value="motorway"
        ),  # noqa: E501
        _feature(
            21.0367, 105.7801, name="Đường sắt đô thị 3", osm_key="railway", osm_value="subway"
        ),  # noqa: E501
        _feature(
            21.0242, 105.8411, name="Ga Hà Nội", osm_key="building", osm_value="train_station"
        ),  # noqa: E501
        _feature(20.99359, 105.87168, name="Times City", osm_key="railway", osm_value="station"),
        _feature(21.06827, 105.82396, name="Quận Tây Hồ", osm_key="boundary", osm_value="historic"),  # noqa: E501
        _feature(HO_CHI_MINH_CITY.lat, HO_CHI_MINH_CITY.lng, name="Chợ Bến Thành"),
        _feature(21.0205, 105.8170, housenumber="12", street="Phố Láng Hạ", osm_key="building"),
        _feature(21.03, 105.85, osm_key="building", osm_value="yes"),
    ]

    places = _photon_search(lambda _: httpx.Response(200, json={"features": features}))

    assert [(place.name, place.address) for place in places] == [
        ("Bệnh viện Bạch Mai", "78 Đường Giải Phóng"),
        ("Ga Hà Nội", ""),
        ("Times City", ""),
        ("12 Phố Láng Hạ", ""),
    ]
    assert places[0].location == Point(21.00182, 105.83967)
    assert {place.source for place in places} == {"photon"}


def _raise(error: Exception) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        raise error

    return handler


@pytest.mark.parametrize(
    "handler",
    [
        lambda _: httpx.Response(503),
        lambda _: httpx.Response(200, text="<html>busy</html>"),
        lambda _: httpx.Response(200, json={"type": "FeatureCollection"}),
        lambda _: httpx.Response(200, json={"features": [{"properties": {}}]}),
        _raise(httpx.ConnectError("refused")),
        _raise(httpx.ReadTimeout("slow")),
    ],
    ids=["server-error", "not-json", "no-features", "no-geometry", "unreachable", "timeout"],
)
def test_photon_failures_raise_geocoding_error(handler: Handler) -> None:
    with pytest.raises(GeocodingError):
        _photon_search(handler)


# Built-in places, else the geocoder's


def _search_with(geocoder: FakeGeocoder | None) -> PlaceSearch:
    builtin = BuiltinPlaces(
        [
            {"name": "Bệnh viện Bạch Mai", "lat": 21.00182, "lng": 105.83967},
            {"name": "Chợ Hôm", "lat": 21.01717, "lng": 105.85197},
        ]
    )
    return PlaceSearch(builtin, geocoder)


def _run(search: PlaceSearch, query: str, limit: int = 5) -> list[Place]:
    return asyncio.run(search.search(query, limit))


def test_built_in_matches_answer_without_the_geocoder() -> None:
    geocoder = FakeGeocoder([photon_place("Phố Bạch Mai", Point(21.0010, 105.8510))])

    places = _run(_search_with(geocoder), "bạch mai")

    assert _names(places) == ["Bệnh viện Bạch Mai"]
    assert places[0].source == "builtin"
    assert geocoder.calls == []


def test_geocoder_answers_what_is_not_built_in_without_repeats() -> None:
    pharmacy = photon_place("Nhà thuốc Bạch Mai", Point(21.0400, 105.8000))
    same_pharmacy = photon_place("Nhà thuốc Bạch Mai", Point(21.0401, 105.8002))  # 23 m
    street = photon_place("Phố Bạch Mai", Point(21.0010, 105.8510))
    third = photon_place("Ngõ Bạch Mai", Point(21.0030, 105.8530))
    geocoder = FakeGeocoder([pharmacy, same_pharmacy, street, third])

    places = _run(_search_with(geocoder), "phố bạch mai", 2)

    assert _names(places) == ["Nhà thuốc Bạch Mai", "Phố Bạch Mai"]
    assert {place.source for place in places} == {"photon"}
    # More than needed: the same place often comes back several times.
    assert geocoder.calls == [("phố bạch mai", 6)]


def test_geocoder_answers_are_remembered() -> None:
    geocoder = FakeGeocoder([photon_place("Ngõ 12 Phố Láng Hạ", Point(21.0205, 105.8170))])
    search = _search_with(geocoder)

    first = _run(search, "12 Láng Hạ")
    again = _run(search, "  12  láng hạ ")
    _run(search, "12 Láng Hạ", 3)

    assert again == first
    assert geocoder.calls == [("12 Láng Hạ", 15), ("12 Láng Hạ", 9)]


def test_geocoder_failure_is_an_empty_answer_and_not_remembered() -> None:
    geocoder = FakeGeocoder([photon_place("Ngõ 12 Phố Láng Hạ", Point(21.0205, 105.8170))])
    geocoder.fail = True
    search = _search_with(geocoder)

    assert _run(search, "12 Láng Hạ") == []
    geocoder.fail = False
    assert _names(_run(search, "12 Láng Hạ")) == ["Ngõ 12 Phố Láng Hạ"]
    assert len(geocoder.calls) == 2


def test_without_a_geocoder_only_built_in_places_are_found() -> None:
    search = _search_with(None)

    assert _names(_run(search, "chợ hôm")) == ["Chợ Hôm"]
    assert _run(search, "12 Láng Hạ") == []
