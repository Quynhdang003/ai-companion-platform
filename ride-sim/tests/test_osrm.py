import asyncio
from collections.abc import Callable

import httpx
import pytest

from app.routing import OsrmRouter, Route, estimate_route
from tests.helpers import BACH_MAI, LANG_HA

Handler = Callable[[httpx.Request], httpx.Response]


def _route(handler: Handler) -> Route:
    async def run() -> Route:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await OsrmRouter(client, "https://osrm.test/", timeout=1).route(
                LANG_HA, BACH_MAI
            )

    return asyncio.run(run())


def _ok(distance: float, duration: float) -> httpx.Response:
    return httpx.Response(
        200,
        json={"code": "Ok", "routes": [{"distance": distance, "duration": duration}]},
    )


def test_road_route_with_hanoi_traffic() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _ok(4121.4, 374.7)

    route = _route(handler)

    # OSRM's empty-road duration x 1.8: 374.7 s -> 674 s.
    assert route == Route(distance_m=4121, duration_s=674, estimated=False)
    [request] = seen
    # Longitude first, as OSRM wants it.
    assert request.url.path == "/route/v1/driving/105.8136,21.0168;105.8411,21.0003"
    assert dict(request.url.params) == {"overview": "false"}


def _raise(error: Exception) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        raise error

    return handler


@pytest.mark.parametrize(
    "handler",
    [
        lambda _: httpx.Response(500),
        lambda _: httpx.Response(200, json={"code": "NoRoute", "message": "No route found"}),
        lambda _: httpx.Response(200, json={"code": "Ok", "routes": []}),
        lambda _: httpx.Response(200, text="<html>busy</html>"),
        _raise(httpx.ConnectError("refused")),
        _raise(httpx.ReadTimeout("slow")),
    ],
    ids=["server-error", "no-route", "no-routes", "not-json", "unreachable", "timeout"],
)
def test_any_failure_gives_the_straight_line_estimate(handler: Handler) -> None:
    route = _route(handler)

    assert route == estimate_route(LANG_HA, BACH_MAI)
    assert route.estimated is True


def test_failure_log_holds_no_coordinates(caplog: pytest.LogCaptureFixture) -> None:
    _route(_raise(httpx.ConnectError("refused")))

    assert "OSRM route failed" in caplog.text
    assert "21.0168" not in caplog.text
    assert "105.8136" not in caplog.text
