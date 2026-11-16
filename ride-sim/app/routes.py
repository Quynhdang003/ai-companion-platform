from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from app.schemas import BookingOut, BookingRequest, QuoteOut, QuoteRequest
from app.simulator import Simulator

router = APIRouter()


def get_simulator(request: Request) -> Simulator:
    return request.app.state.simulator


Sim = Annotated[Simulator, Depends(get_simulator)]


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
