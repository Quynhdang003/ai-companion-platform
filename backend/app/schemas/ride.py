"""Bodies of the Dograh ride tools. Places are named by option number (`ref`) only."""

from pydantic import BaseModel, Field, field_validator

from app.models import RideStatus, RideType
from app.schemas.dograh import SessionToolRequest
from app.services.ride.booking import BookStatus, QuoteStatus
from app.services.ride.places import SearchStatus
from app.services.ride.rides import CancelOutcome, StatusOutcome


class SearchLocationRequest(SessionToolRequest):
    # Written by the LLM: the place as the caller said it. Never logged or stored.
    query: str = Field(min_length=1, max_length=200)

    @field_validator("query")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query is blank")
        return value


class PlaceOptionOut(BaseModel):
    # What the agent passes to get_ride_quote for this place.
    ref: int
    name: str
    # Street address when known, else "".
    address: str


class SearchLocationOut(BaseModel):
    status: SearchStatus
    # Short, speakable Vietnamese; the agent says it as is.
    message: str
    options: list[PlaceOptionOut]


class RideQuoteRequest(SessionToolRequest):
    pickup_ref: int = Field(ge=1)
    destination_ref: int = Field(ge=1)
    ride_type: RideType


class RideQuoteOut(BaseModel):
    status: QuoteStatus
    message: str
    ride_type: RideType
    # Set when quoted.
    price_vnd: int | None = None
    pickup_minutes: int | None = None
    trip_minutes: int | None = None
    surge: bool | None = None


class BookRideRequest(SessionToolRequest):
    # The ride type the caller agreed to: the call's latest quote of it is booked.
    ride_type: RideType


class BookRideOut(BaseModel):
    status: BookStatus
    message: str
    ride_type: RideType
    # Set when the provider just booked it.
    pickup_minutes: int | None = None


class RideStatusOut(BaseModel):
    status: StatusOutcome
    message: str
    # The current ride's status (as stored when the provider didn't answer); null: no ride.
    ride_status: RideStatus | None = None
    # Live, when known.
    pickup_minutes: int | None = None
    dropoff_minutes: int | None = None


class CancelRideOut(BaseModel):
    status: CancelOutcome
    message: str
