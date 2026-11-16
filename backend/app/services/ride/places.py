"""`search_location`: find places for a ride and number them within the call."""

from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CallSession, PlaceSource, RidePlaceOption
from app.services.ride.history import KnownPlace, matching, previous_places
from app.services.ride.provider import RideProvider, RideProviderError

# Read out to the caller: more than three is too many to follow by ear.
MAX_OPTIONS = 3


class SearchStatus(StrEnum):
    FOUND = "found"
    NOT_FOUND = "not_found"
    UNAVAILABLE = "unavailable"  # the provider didn't answer


@dataclass(frozen=True)
class PlaceSearch:
    status: SearchStatus
    options: list[RidePlaceOption]


async def search(
    db: AsyncSession, provider: RideProvider, call: CallSession, query: str
) -> PlaceSearch:
    """Places for `query`, stored as the call's next options (not committed).

    Places of the elder's earlier rides that match answer alone, without asking the provider:
    "same as last time" is instant. Otherwise the provider's places.
    """
    assert call.elder_id is not None
    known = matching(await previous_places(db, call.elder_id), query)
    if known:
        found = [(place, PlaceSource.PREVIOUS) for place in known[:MAX_OPTIONS]]
    else:
        try:
            places = await provider.search_places(query, MAX_OPTIONS)
        except RideProviderError:
            return PlaceSearch(SearchStatus.UNAVAILABLE, [])
        found = [
            (KnownPlace(p.name, p.address, p.location), PlaceSource.PROVIDER)
            for p in places[:MAX_OPTIONS]
        ]
    if not found:
        return PlaceSearch(SearchStatus.NOT_FOUND, [])

    # One search at a time per call, so two can't hand out the same numbers.
    await db.execute(select(CallSession.id).where(CallSession.id == call.id).with_for_update())
    last_ref = await db.scalar(
        select(func.max(RidePlaceOption.ref)).where(RidePlaceOption.call_session_id == call.id)
    )
    options = [
        RidePlaceOption(
            call_session_id=call.id,
            ref=(last_ref or 0) + index,
            name=place.name,
            address=place.address,
            lat=place.location.lat,
            lng=place.location.lng,
            source=source,
        )
        for index, (place, source) in enumerate(found, start=1)
    ]
    db.add_all(options)
    await db.flush()
    return PlaceSearch(SearchStatus.FOUND, options)
