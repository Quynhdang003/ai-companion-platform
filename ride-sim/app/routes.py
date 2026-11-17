from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.errors import AppError
from app.geocoding import PlaceSearch
from app.schemas import (
    BookingOut,
    BookingRequest,
    PlaceOut,
    QuoteOut,
    QuoteRequest,
    SimConfigOut,
    SimConfigPatch,
)
from app.simulator import SimConfig, Simulator


def get_simulator(request: Request) -> Simulator:
    return request.app.state.simulator


def get_place_search(request: Request) -> PlaceSearch:
    return request.app.state.places


Sim = Annotated[Simulator, Depends(get_simulator)]
Places = Annotated[PlaceSearch, Depends(get_place_search)]


async def _timeout_fault(sim: Sim) -> None:
    await sim.fail_if_timing_out()


# What a ride provider offers; the `timeout` fault hits every one of these routes.
router = APIRouter(dependencies=[Depends(_timeout_fault)])
# Controls of the simulation itself, never slowed down.
sim_router = APIRouter(prefix="/sim")


@router.get("/places/search", response_model=list[PlaceOut])
async def search_places(
    places: Places,
    q: Annotated[str, Query(min_length=1, max_length=200)],
    limit: Annotated[int, Query(ge=1, le=10)] = 5,
) -> list[PlaceOut]:
    """Places in Hanoi matching `q`, best first; an empty list when nothing matches."""
    if not q.strip():
        raise AppError(422, "validation_error", "Request body or parameters are invalid")
    return [PlaceOut.from_place(place) for place in await places.search(q, limit)]


@router.post("/quotes", status_code=status.HTTP_201_CREATED, response_model=QuoteOut)
async def create_quote(body: QuoteRequest, sim: Sim) -> QuoteOut:
    quote = await sim.create_quote(
        body.ride_type, body.pickup.to_point(), body.destination.to_point()
    )
    return QuoteOut.from_quote(quote)


@router.post(
    "/bookings",
    status_code=status.HTTP_201_CREATED,
    response_model=BookingOut,
    responses={status.HTTP_200_OK: {"model": BookingOut}},
)
async def create_booking(body: BookingRequest, sim: Sim, response: Response) -> BookingOut:
    """201 with the new booking, or 200 with the existing one when the quote was booked."""
    view, created = await sim.create_booking(body.quote_id)
    if not created:
        response.status_code = status.HTTP_200_OK
    return BookingOut.from_view(view)


@router.get("/bookings/{booking_id}", response_model=BookingOut)
async def get_booking(booking_id: str, sim: Sim) -> BookingOut:
    return BookingOut.from_view(await sim.get_booking(booking_id))


@router.post("/bookings/{booking_id}/cancel", response_model=BookingOut)
async def cancel_booking(booking_id: str, sim: Sim) -> BookingOut:
    return BookingOut.from_view(await sim.cancel_booking(booking_id))


@sim_router.get("/config", response_model=SimConfigOut)
async def get_config(sim: Sim) -> SimConfigOut:
    return SimConfigOut.from_config(sim.config)


@sim_router.patch("/config", response_model=SimConfigOut)
async def patch_config(body: SimConfigPatch, sim: Sim) -> SimConfigOut:
    current = sim.config
    sent = body.model_fields_set
    if "time_scale" in sent and body.time_scale is None:
        raise AppError(422, "validation_error", "Request body or parameters are invalid")
    sim.configure(
        SimConfig(
            time_scale=body.time_scale if "time_scale" in sent else current.time_scale,
            fault=body.fault if "fault" in sent else current.fault,
        )
    )
    return SimConfigOut.from_config(sim.config)
