import pytest
from fastapi.testclient import TestClient

from app.geo import Point
from tests.conftest import ClientFactory
from tests.helpers import FakeGeocoder, error_code, photon_place


def _search(client: TestClient, **params: object) -> list[dict]:
    response = client.get("/places/search", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_built_in_place_is_found_without_the_network(client: TestClient) -> None:
    assert _search(client, q="benh vien bach mai") == [
        {
            "name": "Bệnh viện Bạch Mai",
            "address": "78 Đường Giải Phóng",
            "lat": 21.00182,
            "lng": 105.83967,
            "source": "builtin",
        }
    ]


def test_well_known_places_do_not_wait_for_photon(make_client: ClientFactory) -> None:
    geocoder = FakeGeocoder([photon_place("Phố Bạch Mai", Point(21.0010, 105.8510))])
    client = make_client(geocoder=geocoder)

    assert [p["name"] for p in _search(client, q="Bạch Mai")] == ["Bệnh viện Bạch Mai"]
    assert geocoder.calls == []

    # A more precise request isn't a built-in place: Photon answers it.
    assert _search(client, q="phố Bạch Mai", limit=3)[0]["source"] == "photon"
    assert geocoder.calls == [("phố Bạch Mai", 9)]


def test_street_addresses_come_from_photon(make_client: ClientFactory) -> None:
    geocoder = FakeGeocoder([photon_place("Ngõ 12 Phố Láng Hạ", Point(21.0205, 105.8170))])

    assert _search(make_client(geocoder=geocoder), q="12 Láng Hạ") == [
        {
            "name": "Ngõ 12 Phố Láng Hạ",
            "address": "",
            "lat": 21.0205,
            "lng": 105.817,
            "source": "photon",
        }
    ]


def test_place_search_still_answers_when_photon_fails(make_client: ClientFactory) -> None:
    client = make_client(geocoder=FakeGeocoder(fail=True))

    assert [p["name"] for p in _search(client, q="chợ hôm")] == ["Chợ Hôm"]
    assert _search(client, q="12 Láng Hạ") == []


def test_nothing_found_is_an_empty_list(client: TestClient) -> None:
    assert _search(client, q="phố không có thật") == []


@pytest.mark.parametrize(
    "params",
    [{}, {"q": "   "}, {"q": "x" * 201}, {"q": "chợ", "limit": 0}, {"q": "chợ", "limit": 11}],
    ids=["no-query", "blank", "too-long", "limit-0", "limit-11"],
)
def test_invalid_search_is_rejected(client: TestClient, params: dict) -> None:
    response = client.get("/places/search", params=params)

    assert response.status_code == 422
    assert error_code(response) == "validation_error"
