"""The elder's earlier rides, for "same as last time".

The pre-call hook tells the agent the last ride (`last_ride`), and `search_location` offers
places of earlier rides before asking the provider (`matching`). Indexed reads, no LLM.
"""

import re
import uuid
from dataclasses import dataclass
from datetime import timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RideBooking, RideStatus
from app.services.rag.search import words
from app.services.ride.messages import RIDE_TYPE_LABELS
from app.services.ride.provider import GeoPoint, distance_m

# Earlier rides whose places are offered again.
RECENT_RIDES = 20
# Two places closer than this are the same place for a rider (a building and its gate).
SAME_PLACE_M = 150
# Vietnam has no daylight saving time.
_VIETNAM = timezone(timedelta(hours=7))
# "Hà Nội" can be added to any place, or left out: only as a phrase ("Hà Đông" is a name).
_CITY_PHRASE = re.compile(r"\bha noi\b")


@dataclass(frozen=True)
class KnownPlace:
    name: str
    address: str
    location: GeoPoint


def name_words(text: str) -> frozenset[str]:
    """Words a place is matched on: lower case, no diacritics, no "Hà Nội"."""
    return frozenset(words(_CITY_PHRASE.sub(" ", " ".join(words(text)))))


async def previous_places(db: AsyncSession, elder_id: uuid.UUID) -> list[KnownPlace]:
    """Pickups and destinations of the elder's recent rides, newest first, each place once."""
    bookings = await db.scalars(
        select(RideBooking)
        .where(RideBooking.elder_id == elder_id)
        .order_by(RideBooking.created_at.desc())
        .limit(RECENT_RIDES)
    )
    places: list[KnownPlace] = []
    for booking in bookings:
        for option in (booking.quote.pickup, booking.quote.destination):
            place = KnownPlace(option.name, option.address, GeoPoint(option.lat, option.lng))
            if all(distance_m(place.location, p.location) > SAME_PLACE_M for p in places):
                places.append(place)
    return places


def matching(places: list[KnownPlace], query: str) -> list[KnownPlace]:
    """The places whose name and address hold every word of the query (diacritics ignored)."""
    asked = name_words(query)
    if not asked:
        return []
    return [place for place in places if asked <= name_words(f"{place.name} {place.address}")]


async def last_ride(db: AsyncSession, elder_id: uuid.UUID) -> str | None:
    """The elder's latest ride not cancelled, said in one line, or None.

    E.g. "Từ Ngõ 12 Phố Láng Hạ đến Bệnh viện Bạch Mai, xe bốn chỗ, ngày 16/11".
    """
    booking = await db.scalar(
        select(RideBooking)
        .where(RideBooking.elder_id == elder_id, RideBooking.status != RideStatus.CANCELLED)
        .order_by(RideBooking.created_at.desc())
        .limit(1)
    )
    if booking is None:
        return None
    quote = booking.quote
    day = booking.created_at.astimezone(_VIETNAM).strftime("%d/%m")
    return (
        f"Từ {quote.pickup.name} đến {quote.destination.name},"
        f" {RIDE_TYPE_LABELS[quote.ride_type]}, ngày {day}"
    )
